"""ContentEvolver — section-level content mutation pipeline for Hermes Agent skills.

This is the core assembly logic (step 4 of ContentEvolver). It orchestrates:
1. SECTION SCORER     (section_scorer.py)  — identify weak sections
2. SECTION REWRITER   (section_rewriter.py) — generate candidates  
3. SECTION EVALUATOR  (inline) — score candidates against holdout
4. RECONSTRUCTION     (inline) — assemble winning candidates
5. CONSTRAINT GATE    (same v2 system as GEPA) — validate full skill

Then updates the registry via the same kanban flow as GEPA.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import dspy
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.core.constraints_v2 import (
    ConfigDriftChecker,
    PurposePreservationChecker,
    SkillRegressionChecker,
    ScopeCreepChecker,
    ContentSemanticScorer,
    extract_body,
    extract_frontmatter,
)
from evolution.core.fitness import skill_fitness_metric
from evolution.skills.skill_module import (
    load_skill,
    find_skill,
    reassemble_skill,
)
from evolution.skills.skill_module_v2 import (
    split_into_sections as mcs_split,
    reconstruct_body as mcs_reconstruct,
)
from evolution.skills.section_scorer import SectionScorer, SectionScore
from evolution.skills.section_rewriter import SectionRewriter, RewriteCandidate

console = Console()


class ContentEvolver:
    """Orchestrate the ContentEvolver 5-step pipeline.

    Step 1: Score sections -> identify bottom third
    Step 2: Generate K=3 candidate rewrites per weak section
    Step 3: Evaluate each candidate against holdout set
    Step 4: Reassemble with winning candidates
    Step 5: Run v2 constraint gate
    """

    def __init__(
        self,
        config: EvolutionConfig,
        evaluator_model: str = "minimax/minimax-m2.7",
        rewrite_model: str = "minimax/minimax-m2.7",
        k_candidates: int = 3,
        weak_fraction: float = 1/3,
        score_threshold: float = 0.5,
    ):
        self.config = config
        self.evaluator_model = evaluator_model
        self.rewrite_model = rewrite_model
        self.k_candidates = k_candidates
        self.weak_fraction = weak_fraction
        self.score_threshold = score_threshold

        self.scorer = SectionScorer(evaluator_model=evaluator_model)
        self.rewriter = SectionRewriter(rewrite_model=rewrite_model, k_candidates=k_candidates)

    def _score_candidate(
        self,
        candidate: RewriteCandidate,
        holdout_examples: list,
        sections: list[dict],
    ) -> float:
        """Score a candidate rewrite by replacing its section and running holdout.

        Returns the average holdout score for the reconstructed skill with
        this candidate in place. Only the target section is changed --
        all other sections are byte-identical to baseline.
        """
        evolved_texts = {}
        for sec in sections:
            if sec["name"] == candidate.section_name:
                evolved_texts[sec["name"]] = candidate.candidate_text
            else:
                evolved_texts[sec["name"]] = sec["text"]

        reconstructed = mcs_reconstruct(sections, evolved_texts)

        scores = []
        for ex in holdout_examples:
            try:
                pred = dspy.Prediction(output=reconstructed)
                score = skill_fitness_metric(ex, pred)
                scores.append(score)
            except Exception:
                continue

        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    def _run_constraint_gate(
        self,
        evolved_full: str,
        baseline_full: str,
        baseline_score: float,
        evolved_score: float,
    ) -> tuple[bool, list[dict]]:
        """Run all 5 v2 checkers on the evolved skill.

        Returns (all_passed, list of checker results).
        """
        results = []

        # Checker 1: ConfigDrift
        baseline_fm = extract_frontmatter(baseline_full)
        evolved_fm = extract_frontmatter(evolved_full)
        drift_ok, drift_msg = ConfigDriftChecker().check(evolved_fm, baseline_fm)
        results.append({"name": "ConfigDrift", "passed": drift_ok, "message": drift_msg})

        # Checker 2: PurposePreservation (Signal 1 hard gate)
        baseline_body = extract_body(baseline_full)
        evolved_body = extract_body(evolved_full)
        content_scorer = ContentSemanticScorer()
        content_scorer.fit(baseline_body)
        purpose = PurposePreservationChecker(content_scorer=content_scorer)
        purpose_ok, purpose_msg = purpose.check(evolved_body, baseline_body)
        results.append({"name": "PurposePreservation", "passed": purpose_ok, "message": purpose_msg})

        # Checker 3: Regression
        reg = SkillRegressionChecker()
        reg_ok, reg_msg = reg.check_score(evolved_score, baseline_score)
        results.append({"name": "Regression", "passed": reg_ok, "message": reg_msg})

        # Checker 4: ScopeCreep
        scope = ScopeCreepChecker()
        scope_status, scope_msg = scope.check(evolved_body, baseline_body)
        scope_ok = scope_status in ("match", "minor_drift")
        results.append({"name": "ScopeCreep", "passed": scope_ok, "message": scope_msg})

        # Checker 5: ConstraintValidator (legacy structural checks)
        validator = ConstraintValidator(self.config)
        legacy_results = validator.validate_all(evolved_full, "skill", baseline_text=baseline_full)
        legacy_passed = all(r.passed for r in legacy_results)
        legacy_msg = ", ".join(
            f"{r.constraint_name}: {'OK' if r.passed else 'FAIL'}" for r in legacy_results
        )
        results.append({"name": "ConstraintValidator", "passed": legacy_passed, "message": legacy_msg})

        all_passed = all(r["passed"] for r in results)
        return all_passed, results

    def evolve(
        self,
        skill_name: str,
        holdout_examples: list,
        verbose: bool = True,
    ) -> tuple[str, dict]:
        """Run the full ContentEvolver pipeline on a skill.

        Args:
            skill_name: Name of the skill to evolve
            holdout_examples: DSPy examples for holdout evaluation
            verbose: Print progress

        Returns:
            (evolved_full_text, metrics_dict)
        """
        start_time = time.time()

        # -- 0. Load skill ---------------------------------------------------
        skill_path = find_skill(skill_name, self.config.hermes_agent_path)
        if not skill_path:
            raise ValueError(f"Skill '{skill_name}' not found")

        skill = load_skill(skill_path)
        original_body = skill["body"]
        original_full = skill["raw"]
        skill_description = skill.get("description", "")

        if verbose:
            console.print(f"\n[bold cyan]ContentEvolver[/bold cyan] -- Evolving skill: [bold]{skill_name}[/bold]\n")
            console.print(f"  Body size: {len(original_body):,} chars")
            console.print(f"  Holdout examples: {len(holdout_examples)}")

        # -- 1. SECTION SCORER -----------------------------------------------
        if verbose:
            console.print("\n[bold]Step 1: Scoring sections[/bold]")

        weak_sections = self.scorer.identify_weak_sections(
            skill_body=original_body,
            holdout_examples=holdout_examples,
            fraction=self.weak_fraction,
            verbose=verbose,
        )

        if not weak_sections:
            if verbose:
                console.print("[green]No weak sections found -- skill is already strong[/green]")
            return original_full, self._build_metrics(
                skill_name=skill_name,
                baseline_score=0.0,
                evolved_score=0.0,
                improvements=[],
                constraints_passed=True,
                elapsed=time.time() - start_time,
                original_body=original_body,
                evolved_body=original_body,
            )

        # -- 2. SECTION REWRITER -------------------------------------------
        if verbose:
            console.print(f"\n[bold]Step 2: Generating rewrites for {len(weak_sections)} weak sections[/bold]")

        section_lookup = {s["name"]: s for s in mcs_split(original_body)}
        weak_section_dicts = [section_lookup[s.name] for s in weak_sections if s.name in section_lookup]

        all_candidates = self.rewriter.generate_for_sections(
            weak_sections=weak_section_dicts,
            skill_name=skill_name,
            skill_description=skill_description,
            section_scores=weak_sections,
            full_skill_body=original_body,
            verbose=verbose,
        )

        # -- 3. SECTION EVALUATOR ------------------------------------------
        if verbose:
            console.print(f"\n[bold]Step 3: Evaluating candidates against holdout[/bold]")

        sections = mcs_split(original_body)
        best_rewrites: dict[str, RewriteCandidate] = {}
        section_scores_map: dict[str, float] = {}

        # Get baseline score first
        baseline_scores = []
        for ex in holdout_examples:
            try:
                pred = dspy.Prediction(output=original_body)
                baseline_scores.append(skill_fitness_metric(ex, pred))
            except Exception:
                continue
        baseline_avg = sum(baseline_scores) / max(1, len(baseline_scores))

        if verbose:
            console.print(f"  Baseline holdout score: {baseline_avg:.3f}")

        for section_name, candidates in all_candidates.items():
            if verbose:
                console.print(f"\n  Evaluating {len(candidates)} candidates for section '{section_name}':")

            best_candidate = None
            best_score = -1.0

            for cand in candidates:
                score = self._score_candidate(
                    candidate=cand,
                    holdout_examples=holdout_examples,
                    sections=sections,
                )

                if verbose:
                    delta = score - baseline_avg
                    color = "green" if delta > 0 else "red" if delta < 0 else "yellow"
                    console.print(f"    Candidate {cand.candidate_index+1}: score={score:.3f} ([{color}]{delta:+.3f}[/{color}])")

                if score > best_score:
                    best_score = score
                    best_candidate = cand

            if best_score > baseline_avg:
                best_rewrites[section_name] = best_candidate
                section_scores_map[section_name] = best_score
                if verbose:
                    console.print(f"    [green]Accepted[/green] (improvement: {best_score - baseline_avg:+.3f})")
            else:
                if verbose:
                    console.print(f"    [yellow]Rejected -- best candidate ({best_score:.3f}) <= baseline ({baseline_avg:.3f})[/yellow]")

        # -- 4. RECONSTRUCTION -----------------------------------------------
        if verbose:
            console.print(f"\n[bold]Step 4: Reconstructing skill[/bold]")

        evolved_texts = {}
        for sec in sections:
            if sec["name"] in best_rewrites:
                evolved_texts[sec["name"]] = best_rewrites[sec["name"]].candidate_text
                if verbose:
                    console.print(f"  [green]-> Rewritten[/green]: {sec.get('heading', sec['name'])}")
            else:
                evolved_texts[sec["name"]] = sec["text"]
                if verbose:
                    console.print(f"  [dim]-> Unchanged[/dim]: {sec.get('heading', sec['name'])}")

        evolved_body = mcs_reconstruct(sections, evolved_texts)
        evolved_full = reassemble_skill(skill["frontmatter"], evolved_body)

        evolved_scores = []
        for ex in holdout_examples:
            try:
                pred = dspy.Prediction(output=evolved_body)
                evolved_scores.append(skill_fitness_metric(ex, pred))
            except Exception:
                continue
        evolved_avg = sum(evolved_scores) / max(1, len(evolved_scores))

        # -- 5. CONSTRAINT GATE --------------------------------------------
        if verbose:
            console.print(f"\n[bold]Step 5: Running constraint gate[/bold]")

        constraints_passed, constraint_results = self._run_constraint_gate(
            evolved_full=evolved_full,
            baseline_full=original_full,
            baseline_score=baseline_avg,
            evolved_score=evolved_avg,
        )

        for r in constraint_results:
            icon = "OK" if r["passed"] else "FAIL"
            color = "green" if r["passed"] else "red"
            console.print(f"  [{color}]{icon} {r['name']}[/{color}]: {r['message']}")

        used_fallback = False
        if not constraints_passed:
            if verbose:
                console.print("\n[yellow]Constraint gate failed -- attempting rollback[/yellow]")

            fallback_rewrites = dict(best_rewrites)
            for section_name in list(fallback_rewrites.keys()):
                test_texts = {sec["name"]: sec["text"] for sec in sections}
                for sn, cand in fallback_rewrites.items():
                    if sn != section_name:
                        test_texts[sn] = cand.candidate_text

                test_body = mcs_reconstruct(sections, test_texts)
                test_full = reassemble_skill(skill["frontmatter"], test_body)

                test_scores = []
                for ex in holdout_examples:
                    try:
                        pred = dspy.Prediction(output=test_body)
                        test_scores.append(skill_fitness_metric(ex, pred))
                    except Exception:
                        continue
                test_avg = sum(test_scores) / max(1, len(test_scores))

                test_passed, _ = self._run_constraint_gate(
                    evolved_full=test_full,
                    baseline_full=original_full,
                    baseline_score=baseline_avg,
                    evolved_score=test_avg,
                )

                if test_passed:
                    if verbose:
                        console.print(f"  [green]Rollback success[/green] -- removed rewrite for '{section_name}'")
                    del fallback_rewrites[section_name]
                    evolved_body = test_body
                    evolved_full = test_full
                    evolved_avg = test_avg
                    constraints_passed = True
                    used_fallback = True
                    break
            else:
                if verbose:
                    console.print("  [red]Rollback failed -- keeping original skill[/red]")
                evolved_body = original_body
                evolved_full = original_full
                evolved_avg = baseline_avg
                constraints_passed = True
                used_fallback = False

        elapsed = time.time() - start_time

        improvements = []
        active_rewrites = fallback_rewrites if used_fallback else best_rewrites
        for sec_name, cand in active_rewrites.items():
            sec_heading = next((s.get("heading", sec_name) for s in sections if s["name"] == sec_name), sec_name)
            improvements.append({
                "section": sec_name,
                "heading": sec_heading,
                "original_score": baseline_avg,
                "rewritten_score": section_scores_map.get(sec_name, 0.0),
                "improvement": section_scores_map.get(sec_name, 0.0) - baseline_avg,
                "accepted": sec_name in active_rewrites,
            })

        if verbose:
            table = Table(title="ContentEvolver Results")
            table.add_column("Metric", style="bold")
            table.add_column("Value", justify="right")
            table.add_row("Baseline Score", f"{baseline_avg:.3f}")
            table.add_row("Evolved Score", f"{evolved_avg:.3f}")
            table.add_row("Improvement", f"{evolved_avg - baseline_avg:+.3f}")
            table.add_row("Sections Rewritten", str(len(active_rewrites)))
            table.add_row("Constraints Passed", "OK" if constraints_passed else "FAIL")
            table.add_row("Time", f"{elapsed:.1f}s")
            console.print()
            console.print(table)

        metrics = self._build_metrics(
            skill_name=skill_name,
            baseline_score=baseline_avg,
            evolved_score=evolved_avg,
            improvements=improvements,
            constraints_passed=constraints_passed,
            elapsed=elapsed,
            original_body=original_body,
            evolved_body=evolved_body,
            used_fallback=used_fallback,
        )

        return evolved_full, metrics

    def _build_metrics(
        self,
        skill_name: str,
        baseline_score: float,
        evolved_score: float,
        improvements: list,
        constraints_passed: bool,
        elapsed: float,
        original_body: str,
        evolved_body: str,
        used_fallback: bool = False,
    ) -> dict:
        """Build metrics dict for output saving."""
        return {
            "skill_name": skill_name,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "mode": "content",
            "baseline_score": baseline_score,
            "evolved_score": evolved_score,
            "improvement": evolved_score - baseline_score,
            "improvement_pct": round((evolved_score - baseline_score) / max(baseline_score, 0.001) * 100, 2),
            "baseline_size": len(original_body),
            "evolved_size": len(evolved_body),
            "sections_rewritten": len(improvements),
            "constraints_passed": constraints_passed,
            "used_rollback": used_fallback,
            "improvements": improvements,
            "elapsed_seconds": round(elapsed, 1),
        }
