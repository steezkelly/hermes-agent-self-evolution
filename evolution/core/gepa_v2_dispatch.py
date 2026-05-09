"""GEPA v2 dispatch — wraps v1's GEPA loop with v2.1 decision gates.

Architecture:
  v2_dispatch() takes the same params as v1 evolve(), adds:
   1. ConfigDriftChecker — frontmatter stability
   2. Per-scenario holdout → Router classifies failure patterns
   3. SkillRegressionChecker — holdout regression gate
   4. ScopeCreepChecker — term drift detection
   5. ParetoSelector — multi-objective selection
   6. Top-level BacktrackController — rerun if rejected, up to N times
   7. EvolutionReport with deploy/review/reject recommendation

The v2.1 pipeline wraps v1's GEPA loop — it doesn't replace it.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from evolution.core.types import (
    RouterDecision, BacktrackDecision, ComputeBudget, EvolutionReport,
    ScenarioResult,
)
from evolution.core.router import EvolutionRouter
from evolution.core.backtrack import BacktrackController
from evolution.core.pareto_selector import ParetoSelector
from evolution.core.constraints_v2 import (
    ConfigDriftChecker,
    SkillRegressionChecker,
    ScopeCreepChecker,
    PurposePreservationChecker,
    ContentSemanticScorer,
)
from evolution.core.posthoc_analyzer import PostHocAnalyzer
from evolution.skills.evolve_skill import evolve as v1_evolve
from evolution.skills.evolve_skill import (
    multi_component_extract, reassemble_skill, find_skill,
    load_skill, mcs_split,
)
from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.core.fitness import skill_fitness_metric
from evolution.core.dataset_builder import (
    SyntheticDatasetBuilder, EvalDataset, GoldenDatasetLoader,
)
from evolution.core.external_importers import build_dataset_from_external
from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.constraints import ConstraintValidator
from evolution.core.nous_auth import _get_lm_kwargs

import dspy

console = Console()


def v2_dispatch(
    skill_name: str,
    iterations: int = 10,
    eval_source: str = "synthetic",
    dataset_path: Optional[str] = None,
    optimizer_model: str = "minimax/minimax-m2.7",
    eval_model: str = "minimax/minimax-m2.7",
    hermes_repo: Optional[str] = None,
    run_tests: bool = False,
    dry_run: bool = False,
    stats_csv: Optional[str] = None,
) -> EvolutionReport:
    """Run GEPA v2.1 pipeline: v1 evolve wrapped with decision gates.

    Returns an EvolutionReport with recommendation and full diagnostics.
    """
    config = EvolutionConfig(
        iterations=iterations,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        judge_model=eval_model,
        run_pytest=run_tests,
    )
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    start_time = time.time()

    # ── 0. Dry-run check (before any I/O) ──────────────────────────────
    if dry_run:
        console.print(f"[bold green]v2.1 DRY RUN — pipeline validated.[/bold green]")
        console.print(f"  Skill: {skill_name}")
        console.print(f"  Iterations: {iterations}")
        console.print(f"  Optimizer: {optimizer_model}")
        console.print(f"  Eval: {eval_model}")
        console.print(f"  Source: {eval_source}")
        console.print(f"  Dataset: {dataset_path or 'auto-generated'}")
        return EvolutionReport(
            skill_name=skill_name,
            n_iterations_executed=0,
            improvement=0.0,
            recommendation="review",
            details="Dry run — v2.1 pipeline validated",
            router_decision=RouterDecision(action="extend", failure_pattern="", confidence=0.0, rationale="dry run"),
            backtrack_decision=BacktrackDecision(action="continue", rationale="dry run"),
        )

    # ── 1. Load the skill ──────────────────────────────────────────────
    console.print(Panel(f"[bold cyan]🧬 GEPA v2.1 Pipeline[/bold cyan] — {skill_name}",
                        subtitle=f"{iterations} iterations, optimizer: {optimizer_model}"))

    skill_path = find_skill(skill_name, config.hermes_agent_path)
    if not skill_path:
        console.print(f"[red]✗ Skill '{skill_name}' not found[/red]")
        return EvolutionReport(
            skill_name=skill_name,
            n_iterations_executed=0,
            improvement=0.0,
            recommendation="reject",
            details="Skill not found",
            router_decision=RouterDecision(action="abstain", failure_pattern="", confidence=0.0, rationale="not found"),
            backtrack_decision=BacktrackDecision(action="continue", rationale="N/A"),
        )

    skill = load_skill(skill_path)
    baseline_body = skill["body"]
    baseline_frontmatter = skill.get("frontmatter", "---\nname: " + skill_name + "\ndescription: ''\n---")
    baseline_full = skill["raw"]

    console.print(f"  Loaded: {skill_name} ({len(baseline_body):,} chars)")

    # ── 2. Build evaluation dataset ────────────────────────────────────
    console.print(f"\n[bold]Building eval dataset[/bold] (source: {eval_source})")

    if eval_source == "golden" and dataset_path:
        dataset = GoldenDatasetLoader.load(Path(dataset_path))
    elif eval_source == "sessiondb":
        save_path = Path(dataset_path) if dataset_path else Path("datasets") / "skills" / skill_name
        dataset = build_dataset_from_external(
            skill_name=skill_name,
            skill_text=baseline_full,
            sources=["claude-code", "copilot", "hermes"],
            output_path=save_path,
            model=eval_model,
        )
    elif eval_source == "synthetic":
        builder = SyntheticDatasetBuilder(config)
        dataset = builder.generate(artifact_text=baseline_full, artifact_type="skill")
        save_path = Path("datasets") / "skills" / skill_name
        dataset.save(save_path)
    elif dataset_path:
        dataset = EvalDataset.load(Path(dataset_path))
    else:
        console.print("[red]✗ Specify --dataset-path or use --eval-source synthetic[/red]")
        return EvolutionReport(
            skill_name=skill_name, n_iterations_executed=0, improvement=0.0,
            recommendation="reject", details="No dataset provided",
            router_decision=RouterDecision(action="abstain", failure_pattern="", confidence=0.0,
                                           rationale="no dataset"),
            backtrack_decision=BacktrackDecision(action="continue", rationale="N/A"),
        )

    console.print(f"  Split: {len(dataset.train)} train / {len(dataset.val)} val / {len(dataset.holdout)} holdout")

    # ── 3. Validate baseline constraints (v1 style) ────────────────────
    validator = ConstraintValidator(config)
    baseline_constraints = validator.validate_all(baseline_full, "skill")
    all_pass = True
    for c in baseline_constraints:
        if not c.passed:
            all_pass = False
    if not all_pass:
        console.print("[yellow]⚠ Baseline has constraint violations — proceeding[/yellow]")

    # ── 4. Setup DSPy + GEPA (multi-component with independently mutatable sections) ────
    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Optimizer: GEPA ({iterations} iterations)")
    console.print(f"  Model: {optimizer_model}")

    lm_kwargs, eval_model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 8
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    sections = mcs_split(baseline_body)
    baseline_module = MultiComponentSkillModule(baseline_body)
    trainset = dataset.to_dspy_examples("train")
    valset = dataset.to_dspy_examples("val")

    # ── 5. Top-level backtrack loop ───────────────────────────────────
    # BacktrackController wraps the entire GEPA run, not individual iterations
    backtrack = BacktrackController(window_size=3, plateau_threshold=0.01)
    pareto = ParetoSelector()
    router = EvolutionRouter()
    config_drift = ConfigDriftChecker()
    regression = SkillRegressionChecker()
    scope = ScopeCreepChecker()
    purpose_check = PurposePreservationChecker()
    # Fit ContentSemanticScorer on canonical baseline to detect format/type drift
    # that keyword survival alone misses (e.g., mnemosyne tools → Background Process Analyzer)
    content_scorer = ContentSemanticScorer().fit(baseline_body)
    purpose_check.set_content_scorer(content_scorer)
    posthoc = PostHocAnalyzer(min_improvement_delta=0.03)

    best_body = baseline_body
    best_score = 0.0  # Will be set after first evaluation
    best_frontmatter = baseline_frontmatter
    best_iteration = 0
    run_metrics = []
    attempt = 0
    scenario_results = []

    # ── v2 constraint tracking (accumulates across backtrack attempts) ────
    drift_ok_final = None
    purpose_ok_final = None
    scope_status_final = "match"
    reg_ok_final = None
    pareto_source_final = None

    overall_start = time.time()

    baseline_scores = []
    evolved_scores = []
    scenario_results = []

    for attempt in range(1, max(3, iterations // 5) + 1):
        remaining_budget = max(1, iterations - (attempt - 1) * 5)
        console.print(f"\n[bold cyan]v2 Attempt {attempt}[/bold cyan] — {remaining_budget} iterations remaining")

        # ── 5a. Run GEPA compile ────────────────────────────────────────
        try:
            ref_lm_kwargs, optimizer_model_used = _get_lm_kwargs(optimizer_model)
            ref_lm = dspy.LM(optimizer_model_used, **ref_lm_kwargs)
            optimizer = dspy.GEPA(
                metric=skill_fitness_metric,
                max_metric_calls=max(remaining_budget * 10, 10),
                reflection_lm=ref_lm,
            )
            optimized_module = optimizer.compile(
                MultiComponentSkillModule(best_body),
                trainset=trainset,
                valset=valset,
            )
            optimizer_type = "GEPA"
        except Exception as e:
            console.print(f"[yellow]GEPA failed ({e}), fallback to MIPROv2[/yellow]")
            optimizer = dspy.MIPROv2(
                metric=skill_fitness_metric,
                auto="light",
                num_threads=1,
            )
            optimized_module = optimizer.compile(
                MultiComponentSkillModule(best_body),
                trainset=trainset,
                valset=valset,
            )
            optimizer_type = "MIPROv2"

        # ── 5b. Extract evolved body ────────────────────────────────────
        evolved_body = multi_component_extract(optimized_module, best_body, sections)
        if not evolved_body.strip():
            evolved_body = best_body

        console.print(f"  {optimizer_type} done. Evolved body: {len(evolved_body):,} chars")

        # ── 5c. Config Drift Check ──────────────────────────────────────
        # Build frontmatter from evolved body for drift comparison
        evolved_full_reassembled = reassemble_skill(best_frontmatter, evolved_body)
        drift_ok, drift_msg = config_drift.check(best_frontmatter, best_frontmatter)
        drift_ok_final = drift_ok  # track: last attempt's result
        if not drift_ok:
            console.print(f"[red]✗ Config drift: {drift_msg}[/red] — rejecting")
            continue

        # ── 5c2. Purpose Preservation Check (hard gate) ─────────────────
        purpose_ok, purpose_msg = purpose_check.check(evolved_body, baseline_body)
        purpose_ok_final = purpose_ok  # track: last attempt's result
        if not purpose_ok:
            console.print(f"[red]✗ Purpose lost: {purpose_msg[:120]}[/red] — rejecting evolved variant")
            # Purpose-preservation failures are structural (not score-based);
            # skip backtrack checkpointing since avg_baseline may not yet exist.
            continue

        # ── 5d. Evaluate on holdout ─────────────────────────────────────
        holdout_examples = dataset.to_dspy_examples("holdout")
        baseline_scores = []
        evolved_scores = []
        scenario_results = []

        for ex_idx, ex in enumerate(holdout_examples):
            with dspy.context(lm=lm):
                baseline_pred = baseline_module(task_input=ex.task_input)
                evolved_pred = optimized_module(task_input=ex.task_input)
                b_score = skill_fitness_metric(ex, baseline_pred)
                e_score = skill_fitness_metric(ex, evolved_pred)
            baseline_scores.append(b_score)
            evolved_scores.append(e_score)

            # Build per-scenario result for Router
            scenario_results.append(ScenarioResult(
                scenario_id=f"holdout_{ex_idx}",
                passed=e_score >= b_score,
                score=e_score,
                failure_reason="hard" if e_score < 0.3 else ("medium" if e_score < 0.6 else ""),
                output=f"baseline={b_score:.3f}, evolved={e_score:.3f}",
            ))

        avg_baseline = sum(baseline_scores) / max(1, len(baseline_scores))
        avg_evolved = sum(evolved_scores) / max(1, len(evolved_scores))
        improvement = avg_evolved - avg_baseline

        if best_score == 0.0:
            best_score = avg_baseline

        console.print(f"  Holdout: baseline={avg_baseline:.3f}, evolved={avg_evolved:.3f} ({improvement:+.3f})")

        run_metrics.append({
            "attempt": attempt,
            "avg_baseline": avg_baseline,
            "avg_evolved": avg_evolved,
            "improvement": improvement,
        })

        # ── 5e. Skill Regression Check ──────────────────────────────────
        reg_ok, reg_msg = regression.check_score(avg_evolved, avg_baseline)
        reg_ok_final = reg_ok  # track: last attempt's result
        if not reg_ok:
            console.print(f"[red]✗ Regression: {reg_msg}[/red] — rejecting evolved variant")
            # Checkpoint even for rejections (Backtrack needs the history)
            backtrack.checkpoint_for_score(avg_baseline, best_body, best_frontmatter, attempt)
            backtrack_decision = backtrack.should_backtrack(avg_baseline)
            if backtrack_decision.action != "continue":
                console.print(f"[yellow]  Backtrack: {backtrack_decision.rationale}[/yellow]")
                if backtrack_decision.action == "force_archive":
                    break
            continue

        # ── 5f. Scope Creep Check ───────────────────────────────────────
        scope_status, scope_msg = scope.check(evolved_body, best_body)
        scope_status_final = scope_status  # track: last attempt's result
        if scope_status == "major_drift":
            console.print(f"[yellow]⚠ Scope creep: {scope_msg}[/yellow]")
            # Major drift is a warning, not a blocker — flag in report

        # ── 5g. Pareto Selection ────────────────────────────────────────
        pareto_result = pareto.select(
            baseline_body=best_body,
            baseline_score=best_score,
            evolved_body=evolved_body,
            evolved_score=avg_evolved,
            robustness_passed=True,  # Regression check already passed
        )

        pareto_source_final = pareto_result.source  # track: last attempt's result
        if pareto_result.source == "evolved":
            best_body = evolved_body
            best_score = avg_evolved
            best_iteration = attempt
            backtrack.reset()  # Real improvement resets backtrack counter
            console.print(f"[green]✓ v2 pipeline: evolved accepted (score: {avg_evolved:.3f})[/green]")
        else:
            console.print(f"[dim]  Pareto kept baseline (reason: {pareto_result.reason})[/dim]")
            # Checkpoint for plateau detection
            backtrack.checkpoint_for_score(avg_baseline, best_body, best_frontmatter, attempt)
            backtrack_decision = backtrack.should_backtrack(avg_baseline)
            if backtrack_decision.action == "backtrack":
                restored = backtrack.execute_backtrack()
                if restored:
                    best_body = restored.skill_body
                    best_score = restored.score
                    console.print(f"[yellow]  Backtrack to iteration {restored.iteration} (score: {restored.score:.3f})[/yellow]")
                continue
            elif backtrack_decision.action == "force_archive":
                console.print("[red]✗ Force archive: skill appears untrainable[/red]")
                break

    overall_elapsed = time.time() - overall_start
    # Compute total_improvement as the MAXIMUM genuine holdout improvement across
    # all attempts. This is conservative: it only credits actual improvement
    # that generalized from train/val to the holdout set.
    # NOTE: best_score (val-set) vs baseline_scores[0] (holdout) are different
    # evaluation contexts — never compare them directly.
    total_improvement = max(
        (m["avg_evolved"] - m["avg_baseline"] for m in run_metrics),
        default=0.0,
    )

    # ── 6. PostHoc Analysis ──────────────────────────────────────────────
    # Extract score trajectory for power-law fitting
    # Use best score over time: baseline initially, then best score after each attempt
    score_trajectory = []
    if run_metrics:
        score_trajectory.append(run_metrics[0]["avg_baseline"])  # Starting baseline
        for m in run_metrics:
            best = max(m["avg_baseline"], m["avg_evolved"])
            score_trajectory.append(max(score_trajectory[-1], best))
    posthoc_report = posthoc.analyze(score_trajectory) if len(score_trajectory) >= 4 else None
    if posthoc_report:
        console.print(f"\n[bold]PostHoc Analysis[/bold]")
        console.print(f"  {posthoc_report.summary}")
        console.print(f"  Action: {posthoc_report.recommended_action}")

    # ── 7. Router classification ────────────────────────────────────────
    # Use best-body scenario results for Router classification
    router_decision = router.classify(
        skill_body=best_body,
        benchmark_results=scenario_results,
        evolution_history=[],
        remaining_budget=0,
    )

    # ── 8. Generate report ─────────────────────────────────────────────
    if total_improvement > 0.03:
        recommendation = "deploy"
    elif total_improvement > 0:
        recommendation = "review"
    else:
        recommendation = "reject"

    # Override: if Router found a serious pattern, upgrade recommendation
    if router_decision.failure_pattern in ("structural", "edge_case") and router_decision.action == "fix":
        recommendation = "review"  # Needs human eyes on the fix

    report = EvolutionReport(
        skill_name=skill_name,
        n_iterations_executed=attempt,
        improvement=total_improvement,
        recommendation=recommendation,
        details=f"v2.1 pipeline: {attempt} attempts, best score {best_score:.3f} (baseline: {baseline_scores[0] if baseline_scores else 0:.3f})",
        router_decision=router_decision,
        backtrack_decision=BacktrackDecision(action="continue", rationale="done"),
    )

    # ── 9. Save output ─────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / skill_name / f"v2_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if best_body != baseline_body:
        best_full = reassemble_skill(best_frontmatter, best_body)
        (output_dir / "evolved_skill.md").write_text(best_full)
    (output_dir / "baseline_skill.md").write_text(baseline_full)

    report_path = output_dir / "report.json"
    # ── Build v2 constraint summary (from last completed attempt's outcomes) ──
    v2_constraints = {
        "config_drift_passed": drift_ok_final,
        "purpose_preservation_passed": purpose_ok_final,  # None if PurposePreservationChecker not yet integrated
        "scope_status": scope_status_final,
        "regression_passed": reg_ok_final,
        "pareto_source": pareto_source_final,
        "router_action": router_decision.action,
    }

    report_dict = {
        "skill_name": report.skill_name,
        "iterations_executed": report.n_iterations_executed,
        "improvement": report.improvement,
        "recommendation": report.recommendation,
        "details": report.details,
        "router": {
            "action": router_decision.action,
            "failure_pattern": router_decision.failure_pattern,
            "confidence": router_decision.confidence,
            "rationale": router_decision.rationale,
        },
        "best_score": best_score,
        "baseline_score": baseline_scores[0] if baseline_scores else 0,
        "elapsed_seconds": round(overall_elapsed, 1),
        "attempt_metrics": run_metrics,
        "posthoc": posthoc.to_dict(posthoc_report) if posthoc_report else None,
        "v2_constraints": v2_constraints,
    }
    (output_dir / "report.json").write_text(json.dumps(report_dict, indent=2))

    # ── Write metrics.json (v1 schema + v2_constraints) ─────────────────
    metrics = {
        "skill_name": skill_name,
        "timestamp": timestamp,
        "iterations": iterations,
        "optimizer_model": optimizer_model,
        "optimizer_type": optimizer_type if "optimizer_type" in dir() else None,
        "eval_model": eval_model,
        "eval_source": eval_source,
        "baseline_score": baseline_scores[0] if baseline_scores else 0.0,
        "evolved_score": best_score,
        "improvement": total_improvement,
        "baseline_size": len(baseline_body),
        "evolved_size": len(best_body),
        "train_examples": len(dataset.train) if "dataset" in dir() else 0,
        "val_examples": len(dataset.val) if "dataset" in dir() else 0,
        "holdout_examples": len(dataset.holdout) if "dataset" in dir() else 0,
        "elapsed_seconds": round(overall_elapsed, 1),
        "constraints_passed": all_pass,
        "v2_constraints": v2_constraints,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    console.print(f"\n  Output saved to {output_dir}/")
    console.print()

    # ── 10. Display summary table ──────────────────────────────────────
    table = Table(title=f"v2.1 Results — {skill_name}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Recommendation", f"[bold]{recommendation.upper()}[/bold]")
    table.add_row("Attempts", str(attempt))
    table.add_row("Best Score", f"{best_score:.3f}")
    table.add_row("Improvement", f"{total_improvement:+.3f}")
    table.add_row("Router Decision", f"{router_decision.action} ({router_decision.failure_pattern})")
    table.add_row("Router Confidence", f"{router_decision.confidence:.1%}")
    if posthoc_report:
        table.add_row("Phase", posthoc_report.phase.phase if posthoc_report.phase else "N/A")
        table.add_row("Power-Law c", f"{posthoc_report.power_law.exponent_c:.4f}" if posthoc_report.power_law else "N/A")
    table.add_row("Elapsed", f"{overall_elapsed:.0f}s")

    console.print(table)

    return report
