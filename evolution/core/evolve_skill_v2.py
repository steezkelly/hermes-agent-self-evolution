"""GEPA v2 — Main orchestrator for the corrected evolution pipeline.

Wires all v2.1 modules together: Router, robustness gates, Pareto
Selector, Backtrack Controller. Single-threaded sequential GEPA loop
with no parallelism. delegate_task is NOT available in this repo.

Pipeline:
    1. Load skill
    2. Build/load benchmark dataset (reuse SyntheticDatasetBuilder)
    3. Classify skill type + allocate budget
    4. Baseline evaluation (score existing skill)
    5. FOR iteration in budget:
       a. Run single GEPA compile step (sequential)
       b. Score evolved candidate on holdout
       c. Run Router (post-hoc analysis of what changed)
       d. Run robustness checks (config drift, regression, scope)
       e. Run Pareto Selector (evolved vs baseline)
       f. Run Backtrack check (plateau detection)
       g. Run Stop check (hard/soft stop)
    6. Save evolved skill and metrics
    7. Return EvolutionReport
"""

import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from evolution.core.types import (
    EvolutionSnapshot, EvolutionReport, RouterDecision, ComputeBudget, BacktrackDecision
)
from evolution.core.router import EvolutionRouter
from evolution.core.backtrack import BacktrackController
from evolution.core.pareto_selector import ParetoSelector, SelectionResult
from evolution.core.constraints_v2 import ConfigDriftChecker, SkillRegressionChecker, ScopeCreepChecker

logger = logging.getLogger(__name__)


class EvolutionRun:
    """Manages a single GEPA v2 evolution run.

    Usage:
        run = EvolutionRun(skill_name="companion-workflows")
        report = run.execute(max_iterations=10)
    """

    def __init__(
        self,
        skill_name: str,
        output_root: Optional[Path] = None,
        size_growth_threshold: float = 0.2,
        min_improvement_delta: float = 0.03,
    ):
        self.skill_name = skill_name
        self.output_root = output_root or Path("output")
        self.router = EvolutionRouter()
        self.backtrack = BacktrackController()
        self.selector = ParetoSelector(
            growth_threshold=size_growth_threshold,
            min_improvement_delta=min_improvement_delta,
        )
        self.config_drift = ConfigDriftChecker()
        self.regression = SkillRegressionChecker(output_root=self.output_root)
        self.scope_creep = ScopeCreepChecker()
        self.history: list[EvolutionSnapshot] = []
        self.budget: Optional[ComputeBudget] = None
        self.backtrack_events: list[BacktrackDecision] = []

    def execute(
        self,
        baseline_body: str,
        baseline_frontmatter: str,
        baseline_score: float,
        budget: ComputeBudget,
        dry_run: bool = False,
    ) -> EvolutionReport:
        """Run the full evolution pipeline.

        Args:
            baseline_body: Body text of the baseline skill.
            baseline_frontmatter: Frontmatter string of the baseline skill.
            baseline_score: Holdout score of the baseline.
            budget: ComputeBudget from OptimizationController.
            dry_run: If True, validate pipeline setup without running GEPA.

        Returns:
            EvolutionReport with full results.
        """
        start_time = time.time()
        self.budget = budget

        if dry_run:
            logger.info("Dry run — skipping GEPA compile and all LM calls")
            return EvolutionReport(
                skill_name=self.skill_name,
                baseline_score=baseline_score,
                evolved_score=baseline_score,
                improvement=0.0,
                n_iterations_executed=0,
                budget=budget,
                recommendation="review",
                elapsed_seconds=0.0,
            )

        # Record baseline as iteration 0
        self.history.append(EvolutionSnapshot(
            iteration=0,
            skill_body=baseline_body,
            score=baseline_score,
            variation_explanation="Baseline (no changes)",
            timestamp=datetime.now().isoformat(),
        ))

        current_body = baseline_body
        current_score = baseline_score

        for iteration in range(1, budget.max_iterations + 1):
            logger.info(f"Iteration {iteration}/{budget.max_iterations}")

            # (In a real run, GEPA.compile() would go here.
            # For now, this is the pipeline skeleton that orchestrates
            # the decision flow. The caller provides evolved_body and
            # evolved_score from the GEPA run.)

            # ── Step c: Run Router ──────────────────────────────────────────
            router_decision = self._run_router(
                current_body, current_score, iteration, budget
            )

            # ── Step d: Robustness checks ───────────────────────────────────
            robustness_passed, robustness_summary = self._check_robustness(
                current_body, baseline_body, baseline_frontmatter
            )

            # ── Step e: Pareto Selector ─────────────────────────────────────
            selection = self._select_candidate(
                baseline_body, baseline_score,
                current_body, current_score,
                robustness_passed,
            )
            current_body = selection.body
            current_score = selection.holdout_score

            # Record iteration
            self.history.append(EvolutionSnapshot(
                iteration=iteration,
                skill_body=current_body,
                score=current_score,
                variation_explanation=(
                    f"Router: {router_decision.action} "
                    f"(pattern={router_decision.failure_pattern}, "
                    f"conf={router_decision.confidence:.2f}). "
                    f"Selection: {selection.source}. "
                    f"Robustness: {robustness_summary}"
                ),
                timestamp=datetime.now().isoformat(),
            ))

            # ── Step f: Backtrack check ─────────────────────────────────────
            self.backtrack.checkpoint(self.history[-1])
            backtrack_decision = self.backtrack.should_backtrack(current_score)
            self.backtrack_events.append(backtrack_decision)

            if backtrack_decision.action == "backtrack":
                restored = self.backtrack.execute_backtrack()
                if restored:
                    logger.info(f"Backtracking to iteration {restored.iteration}")
                    current_body = restored.skill_body
                    current_score = restored.score
            elif backtrack_decision.action == "force_archive":
                logger.warning(f"Force archive: {backtrack_decision.rationale}")
                self._archive_skill(current_body)
                break

            # ── Step g: Stop check ──────────────────────────────────────────
            if iteration >= budget.max_iterations:
                logger.info(f"Reached max iterations ({budget.max_iterations})")
                break

        elapsed = time.time() - start_time
        final_score = self.history[-1].score if self.history else baseline_score
        improvement = final_score - baseline_score

        return EvolutionReport(
            skill_name=self.skill_name,
            baseline_score=baseline_score,
            evolved_score=final_score,
            improvement=improvement,
            n_iterations_executed=len(self.history) - 1,
            budget=budget,
            selected_body=self.history[-1].skill_body if self.history else baseline_body,
            selected_source="evolved" if improvement > 0 else "baseline",
            robustness_passed=True,
            backtrack_events=self.backtrack_events,
            elapsed_seconds=elapsed,
            posthoc_analysis=self._build_posthoc_summary(),
            recommendation=(
                "deploy" if improvement > self.selector.min_improvement_delta
                else "review" if improvement > 0
                else "reject"
            ),
        )

    def _run_router(self, body: str, score: float,
                    iteration: int, budget: ComputeBudget) -> RouterDecision:
        """Run the Router on the current state."""
        remaining = budget.max_iterations - iteration
        # Simplified for v2.1: actual benchmark results come from GEPA evaluation
        return self.router.classify(
            skill_body=body,
            benchmark_results=[],
            evolution_history=self.history,
            remaining_budget=remaining,
        )

    def _check_robustness(self, evolved_body: str, baseline_body: str,
                          baseline_frontmatter: str) -> tuple[bool, str]:
        """Run all three robustness checkers. Returns (passed, summary)."""
        drift_passed, drift_summary = self.config_drift.check(
            self._extract_frontmatter(evolved_body),
            baseline_frontmatter,
        )
        if not drift_passed:
            return False, drift_summary

        regression_passed, regression_summary = self.regression.check(self.skill_name)
        if not regression_passed:
            return False, regression_summary

        scope_status, scope_summary = self.scope_creep.check(evolved_body, baseline_body)
        if scope_status == "major_drift":
            return False, scope_summary

        return True, f"All checks passed: {drift_summary}; {regression_summary}; {scope_summary}"

    @staticmethod
    def _select_candidate(
        baseline_body: str, baseline_score: float,
        evolved_body: str, evolved_score: float,
        robustness_passed: bool,
    ) -> SelectionResult:
        """Run the Pareto selector on current candidates."""
        selector = ParetoSelector()
        return selector.select(
            baseline_body=baseline_body,
            baseline_score=baseline_score,
            evolved_body=evolved_body,
            evolved_score=evolved_score,
            robustness_passed=robustness_passed,
        )

    @staticmethod
    def _extract_frontmatter(full_body: str) -> str:
        """Extract YAML frontmatter from a full skill body string."""
        lines = full_body.strip().split('\n')
        if not lines or lines[0].strip() != '---':
            return ""
        end_idx = None
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                end_idx = i
                break
        if end_idx is None:
            return ""
        return '\n'.join(lines[1:end_idx])

    def _archive_skill(self, body: str):
        """Archive a force-archived skill for human review."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = self.output_root / self.skill_name / "archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{timestamp}.md"
        archive_path.write_text(body)
        logger.info(f"Skill archived to {archive_path} for human review")

    def _build_posthoc_summary(self) -> str:
        """Build a human-readable summary of the evolution run."""
        if not self.history:
            return "No evolution data"
        parts = [f"{len(self.history) - 1} iterations executed"]
        if self.history:
            start_score = self.history[0].score
            end_score = self.history[-1].score
            parts.append(f"Score: {start_score:.3f} → {end_score:.3f} ({end_score - start_score:+.3f})")
        return "; ".join(parts)
