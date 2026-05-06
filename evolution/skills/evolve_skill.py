"""Evolve a Hermes Agent skill using DSPy + GEPA.

Usage:
    python -m evolution.skills.evolve_skill --skill github-code-review --iterations 10
    python -m evolution.skills.evolve_skill --skill arxiv --eval-source golden --dataset datasets/skills/arxiv/
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.dataset_builder import SyntheticDatasetBuilder, EvalDataset, GoldenDatasetLoader
from evolution.core.external_importers import build_dataset_from_external
from evolution.core.fitness import skill_fitness_metric, fit_global_scorer, fit_embedding_scorer, LLMJudge, FitnessScore
from evolution.core.constraints import ConstraintValidator
from evolution.core.nous_auth import _get_lm_kwargs
from evolution.skills.skill_module import (
    load_skill,
    find_skill,
    reassemble_skill,
)
from evolution.skills.skill_module_v2 import (
    MultiComponentSkillModule,
    reconstruct_body as mcs_reconstruct,
    split_into_sections as mcs_split,
)

console = Console()


def multi_component_extract(optimized_module, original_body: str, sections) -> str:
    """Extract evolved skill body from a GEPA-optimized MultiComponentSkillModule.

    GEPA mutates each section predictor's instructions independently.
    evolved_sections() reads all 11 predictors' instructions and reconstructs
    the full body by joining evolved section texts.

    Returns the evolved body string, or original_body if no changes detected.
    """
    try:
        if hasattr(optimized_module, 'evolved_sections') and hasattr(optimized_module, 'sections'):
            evolved = optimized_module.evolved_sections()
            if evolved and any(
                evolved[s["name"]] != s["text"]
                for s in sections
                if s["name"] in evolved
            ):
                return mcs_reconstruct(sections, evolved)
    except Exception:
        pass
    return original_body


def evolve(
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
    override_breaker: bool = False,
):
    """Main evolution function — orchestrates the full optimization loop."""

    config = EvolutionConfig(
        iterations=iterations,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        judge_model=eval_model,  # Use same model for dataset generation
        run_pytest=run_tests,
    )
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    # ── 1. Find and load the skill ──────────────────────────────────────
    console.print(f"\n[bold cyan]🧬 Hermes Agent Self-Evolution[/bold cyan] — Evolving skill: [bold]{skill_name}[/bold]\n")

    skill_path = find_skill(skill_name, config.hermes_agent_path)
    if not skill_path:
        console.print(f"[red]✗ Skill '{skill_name}' not found in {config.hermes_agent_path / 'skills'}[/red]")
        sys.exit(1)

    skill = load_skill(skill_path)
    try:
        rel = skill_path.relative_to(config.hermes_agent_path)
    except ValueError:
        rel = skill_path
    console.print(f"  Loaded: {rel}")
    console.print(f"  Name: {skill['name']}")
    console.print(f"  Size: {len(skill['raw']):,} chars")
    console.print(f"  Description: {skill['description'][:80]}...")

    if dry_run:
        console.print(f"\n[bold green]DRY RUN — setup validated successfully.[/bold green]")
        console.print(f"  Would generate eval dataset (source: {eval_source})")
        console.print(f"  Would run GEPA optimization ({iterations} iterations)")
        console.print(f"  Would validate constraints and create PR")
        return

    # ── 2. Build or load evaluation dataset ─────────────────────────────
    console.print(f"\n[bold]Building evaluation dataset[/bold] (source: {eval_source})")

    if eval_source == "golden" and dataset_path:
        dataset = GoldenDatasetLoader.load(Path(dataset_path))
        console.print(f"  Loaded golden dataset: {len(dataset.all_examples)} examples")
    elif eval_source == "sessiondb":
        save_path = Path(dataset_path) if dataset_path else Path("datasets") / "skills" / skill_name
        dataset = build_dataset_from_external(
            skill_name=skill_name,
            skill_text=skill["raw"],
            sources=["claude-code", "copilot", "hermes"],
            output_path=save_path,
            model=eval_model,
        )
        if not dataset.all_examples:
            console.print("[red]✗ No relevant examples found from session history[/red]")
            sys.exit(1)
        console.print(f"  Mined {len(dataset.all_examples)} examples from session history")
    elif eval_source == "synthetic":
        builder = SyntheticDatasetBuilder(config)
        dataset = builder.generate(
            artifact_text=skill["raw"],
            artifact_type="skill",
        )
        # Save for reuse
        save_path = Path("datasets") / "skills" / skill_name
        dataset.save(save_path)
        console.print(f"  Generated {len(dataset.all_examples)} synthetic examples")
        console.print(f"  Saved to {save_path}/")
    elif dataset_path:
        dataset = EvalDataset.load(Path(dataset_path))
        console.print(f"  Loaded dataset: {len(dataset.all_examples)} examples")
    else:
        console.print("[red]✗ Specify --dataset-path or use --eval-source synthetic[/red]")
        sys.exit(1)

    console.print(f"  Split: {len(dataset.train)} train / {len(dataset.val)} val / {len(dataset.holdout)} holdout")

    # ── 3. Validate constraints on baseline ─────────────────────────────
    console.print(f"\n[bold]Validating baseline constraints[/bold]")
    validator = ConstraintValidator(config)
    baseline_constraints = validator.validate_all(skill["raw"], "skill")
    all_pass = True
    for c in baseline_constraints:
        icon = "✓" if c.passed else "✗"
        color = "green" if c.passed else "red"
        console.print(f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}")
        if not c.passed:
            all_pass = False

    if not all_pass:
        console.print("[yellow]⚠ Baseline skill has constraint violations — proceeding anyway[/yellow]")

    # ── 4. Set up DSPy + GEPA optimizer ─────────────────────────────────
    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Optimizer: GEPA ({iterations} iterations)")
    console.print(f"  Optimizer model: {optimizer_model}")
    console.print(f"  Eval model: {eval_model}")

    # Configure DSPy LM with retry handling for rate limits (PR #35)
    lm_kwargs, eval_model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 8
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    # Create the baseline skill module — multi-component with independently mutatable sections
    sections = mcs_split(skill["body"])
    baseline_module = MultiComponentSkillModule(skill["body"])

    # Prepare DSPy examples
    trainset = dataset.to_dspy_examples("train")
    valset = dataset.to_dspy_examples("val")

    # Fit the TF-IDF scorer for semantic similarity evaluation
    # This must run before GEPA optimization so the metric uses TF-IDF, not keyword overlap
    fit_global_scorer(trainset + valset)       # TF-IDF fallback
    fit_embedding_scorer(trainset + valset)    # primary: sentence embedding scorer
    console.print("  ✓ Sentence embedding scorer fitted on train+val expected behaviors (primary)")
    console.print("  ✓ TF-IDF scorer fitted as fallback")

    # ── 5. Run GEPA optimization ────────────────────────────────────────
    console.print(f"\n[bold cyan]Running GEPA optimization ({iterations} iterations)...[/bold cyan]\n")

    start_time = time.time()

    try:
        ref_lm_kwargs, optimizer_model_used = _get_lm_kwargs(optimizer_model)
        ref_lm_kwargs["num_retries"] = 8
        ref_lm = dspy.LM(optimizer_model_used, **ref_lm_kwargs)
        # PR #35: use max_metric_calls (not max_full_evals); do NOT mix with auto="light"
        optimizer = dspy.GEPA(
            metric=skill_fitness_metric,
            max_metric_calls=iterations * 20,  # metric calls budget (larger minibatch = more calls)
            reflection_minibatch_size=15,  # evaluate each candidate on 15 examples for signal
            reflection_lm=ref_lm,
        )

        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
            valset=valset,
        )
    except Exception as e:
        # Fall back to MIPROv2 if GEPA isn't available in this DSPy version
        console.print(f"[yellow]GEPA not available ({e}), falling back to MIPROv2[/yellow]")
        # PR #35: add num_threads=1 to serialize eval calls and avoid rate limits
        optimizer = dspy.MIPROv2(
            metric=skill_fitness_metric,
            auto="light",
            num_threads=1,
        )
        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
        )

    elapsed = time.time() - start_time
    optimizer_type = type(optimizer).__name__
    console.print(f"  Optimizer used: {optimizer_type}")
    console.print(f"  Completed in {elapsed:.1f}s")

    # ── 6. Extract evolved skill body ───────────────────────────────────
    evolved_body = multi_component_extract(optimized_module, skill["body"], sections)

    # Fallback only if extraction produced nothing meaningful (empty or null)
    if not evolved_body.strip():
        console.print("[yellow]  ⚠ Could not extract evolved body — using baseline[/yellow]")
        evolved_body = skill["body"]
    elif evolved_body == skill["body"]:
        # Extraction worked but GEPA found no better variant — this is normal
        console.print("[dim]  (baseline body retained — GEPA found no improved variant)[/dim]")

    evolved_full = reassemble_skill(skill["frontmatter"], evolved_body)

    # ── 6b. ROI Circuit Breaker: check BEFORE expensive holdout evaluation ─
    # (Phase 3) If 3 consecutive prior runs with improvement < 0.005, warn user
    from evolution.core.observatory.roi_circuit import ROICircuitBreaker
    breaker = ROICircuitBreaker()
    is_open, breaker_msg = breaker.check(skill_name)
    if is_open and not override_breaker:
        console.print(f"\n[bold red]⚠ ROI CIRCUIT BREAKER OPEN[/bold red] for {skill_name}")
        console.print(f"  {breaker_msg}")
        console.print("  Use --override-breaker to run anyway.")
        output_path = Path("output") / skill_name / "evolved_FAILED.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(evolved_full)
        console.print(f"  Saved to {output_path} for inspection.")
        # Skip the expensive holdout evaluation and return early
        return
    elif is_open and override_breaker:
        console.print(f"\n[yellow]⚠ ROI CIRCUIT BREAKER OPEN — overridden[/yellow]")
        console.print(f"  {breaker_msg}")
        breaker.override(skill_name, "CLI --override-breaker flag")

    # ── 7. Validate evolved skill ───────────────────────────────────────
    console.print(f"\n[bold]Validating evolved skill[/bold]")
    # PR #35: pass evolved_full (reassembled with frontmatter), not body-only
    evolved_constraints = validator.validate_all(evolved_full, "skill", baseline_text=skill["raw"])
    all_pass = True
    for c in evolved_constraints:
        icon = "✓" if c.passed else "✗"
        color = "green" if c.passed else "red"
        console.print(f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}")
        if not c.passed:
            all_pass = False

    if not all_pass:
        console.print("[red]✗ Evolved skill FAILED constraints — not deploying[/red]")
        # Still save for inspection
        output_path = Path("output") / skill_name / "evolved_FAILED.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(evolved_full)
        console.print(f"  Saved failed variant to {output_path}")
        return

    # ── 7b. Purpose Preservation Check ──────────────────────────────────
    # Block type-changing evolutions (documentation -> consultant-prompt)
    from evolution.core.constraints_v2 import PurposePreservationChecker, extract_body
    purpose_check = PurposePreservationChecker()
    baseline_body = extract_body(skill["raw"])
    purpose_ok, purpose_msg = purpose_check.check(evolved_body, baseline_body)
    if not purpose_ok:
        console.print(f"[red]✗ Purpose lost: {purpose_msg[:120]}[/red]")
        console.print("[red]✗ Not deploying type-changing evolution[/red]")
        output_path = Path("output") / skill_name / "evolved_FAILED.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(evolved_full)
        console.print(f"  Saved failed variant to {output_path}")
        return
    console.print(f"[green]✓ Purpose preserved[/green]")

    # ── 8. Evaluate on holdout set ───────────────────────────────────────
    console.print(f"\n[bold]Evaluating on holdout set ({len(dataset.holdout)} examples)[/bold]")

    holdout_examples = dataset.to_dspy_examples("holdout")

    baseline_scores = []
    evolved_scores = []
    for ex in holdout_examples:
        # Score baseline
        with dspy.context(lm=lm):
            baseline_pred = baseline_module(task_input=ex.task_input)
            baseline_score = skill_fitness_metric(ex, baseline_pred)
            baseline_scores.append(baseline_score)

            evolved_pred = optimized_module(task_input=ex.task_input)
            evolved_score = skill_fitness_metric(ex, evolved_pred)
            evolved_scores.append(evolved_score)

    avg_baseline = sum(baseline_scores) / max(1, len(baseline_scores))
    avg_evolved = sum(evolved_scores) / max(1, len(evolved_scores))
    improvement = avg_evolved - avg_baseline

    # ── 9. Report results ───────────────────────────────────────────────
    table = Table(title="Evolution Results")
    table.add_column("Metric", style="bold")
    table.add_column("Baseline", justify="right")
    table.add_column("Evolved", justify="right")
    table.add_column("Change", justify="right")

    change_color = "green" if improvement > 0 else "red"
    table.add_row(
        "Holdout Score",
        f"{avg_baseline:.3f}",
        f"{avg_evolved:.3f}",
        f"[{change_color}]{improvement:+.3f}[/{change_color}]",
    )
    table.add_row(
        "Skill Size",
        f"{len(skill['body']):,} chars",
        f"{len(evolved_body):,} chars",
        f"{len(evolved_body) - len(skill['body']):+,} chars",
    )
    table.add_row("Time", "", f"{elapsed:.1f}s", "")
    table.add_row("Iterations", "", str(iterations), "")

    console.print()
    console.print(table)

    # ── 10. Save output ─────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / skill_name / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save evolved skill
    (output_dir / "evolved_skill.md").write_text(evolved_full)

    # Save baseline for comparison
    (output_dir / "baseline_skill.md").write_text(skill["raw"])

    # Save metrics
    metrics = {
        "skill_name": skill_name,
        "timestamp": timestamp,
        "iterations": iterations,
        "optimizer_model": optimizer_model,
        "optimizer_type": optimizer_type,
        "eval_model": eval_model,
        "eval_source": eval_source,
        "baseline_score": avg_baseline,
        "evolved_score": avg_evolved,
        "improvement": improvement,
        "baseline_size": len(skill["body"]),
        "evolved_size": len(evolved_body),
        "train_examples": len(dataset.train),
        "val_examples": len(dataset.val),
        "holdout_examples": len(dataset.holdout),
        "elapsed_seconds": elapsed,
        "constraints_passed": all_pass,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    console.print(f"\n  Output saved to {output_dir}/")

    # ── 11. Append to stats CSV for analysis ─────────────────────────────────
    if stats_csv:
        import csv
        import os
        csv_path = Path(stats_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "skill_name", "provider", "eval_source", "optimizer_type",
                "iterations", "optimizer_model", "eval_model",
                "train_n", "val_n", "holdout_n",
                "baseline_holdout", "evolved_holdout",
                "improvement", "improvement_pct",
                "baseline_size", "evolved_size",
                "elapsed_seconds", "constraints_passed",
            ])
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp": timestamp,
                "skill_name": skill_name,
                "provider": os.environ.get("PROVIDER", "openrouter"),
                "eval_source": eval_source,
                "optimizer_type": optimizer_type,
                "iterations": iterations,
                "optimizer_model": optimizer_model,
                "eval_model": eval_model,
                "train_n": len(dataset.train),
                "val_n": len(dataset.val),
                "holdout_n": len(dataset.holdout),
                "baseline_holdout": round(avg_baseline, 6),
                "evolved_holdout": round(avg_evolved, 6),
                "improvement": round(improvement, 6),
                "improvement_pct": round((improvement / max(avg_baseline, 0.001)) * 100, 2),
                "baseline_size": len(skill["body"]),
                "evolved_size": len(evolved_body),
                "elapsed_seconds": round(elapsed, 1),
                "constraints_passed": all_pass,
            })
        console.print(f"  Stats appended to {csv_path}")

    if improvement > 0:
        console.print(f"\n[bold green]✓ Evolution improved skill by {improvement:+.3f} ({improvement/max(0.001, avg_baseline)*100:+.1f}%)[/bold green]")
        console.print(f"  Review the diff: diff {output_dir}/baseline_skill.md {output_dir}/evolved_skill.md")
    else:
        console.print(f"\n[yellow]⚠ Evolution did not improve skill (change: {improvement:+.3f})[/yellow]")
        console.print("  Try: more iterations, better eval dataset, or different optimizer model")

    # ── 12. Record ROI for the circuit breaker ──────────────────────────
    # (Phase 3) Persist (improvement, cost) so the breaker can halt repeated zero-ROI runs
    from evolution.core.observatory.roi_circuit import ROICircuitBreaker
    breaker = ROICircuitBreaker()
    total_cost = breaker.compute_run_cost(skill_name)
    breaker.record_run(
        skill_name=skill_name,
        improvement=round(improvement, 6),
        baseline_score=round(avg_baseline, 6),
        evolved_score=round(avg_evolved, 6),
        iterations=iterations,
        total_cost=round(total_cost, 6),
        notes=f"optimizer={optimizer_model} eval={eval_model}",
    )
    console.print(f"  ROI recorded: improvement={improvement:+.4f} cost=${total_cost:.4f}")


@click.command()
@click.option("--skill", required=True, help="Name of the skill to evolve")
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "golden", "sessiondb"]),
              help="Source for evaluation dataset")
@click.option("--dataset-path", default=None, help="Path to existing eval dataset (JSONL)")
@click.option("--optimizer-model", default="minimax/minimax-m2.7", help="Model for GEPA reflections")
@click.option("--eval-model", default="minimax/minimax-m2.7", help="Model for evaluations")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--run-tests", is_flag=True, help="Run full pytest suite as constraint gate")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--stats-csv", default=None, help="Append run stats to a CSV file for analysis")
@click.option("--v2", is_flag=True, help="Use GEPA v2.1 pipeline (Router + robustness gates + backtrack)")
@click.option("--mode", default="framing", type=click.Choice(["framing", "content", "both"]),
              help="Evolution mode: framing=GEPA only, content=ContentEvolver only, both=GEPA then ContentEvolver")
@click.option("--override-breaker", is_flag=True, help="Override ROI circuit breaker if it is open (Phase 3)")
def main(skill, iterations, eval_source, dataset_path, optimizer_model, eval_model, hermes_repo, run_tests, dry_run, stats_csv, v2, mode, override_breaker):
    """Evolve a Hermes Agent skill using DSPy + GEPA optimization."""
    if mode == "content":
        from evolution.skills.evolve_content import evolve_content
        evolve_content(
            skill_name=skill,
            eval_source=eval_source,
            dataset_path=dataset_path,
            evaluator_model=eval_model,
            rewrite_model=eval_model,
            hermes_repo=hermes_repo,
            dry_run=dry_run,
        )
    elif mode == "both":
        console.print("[bold cyan]Running BOTH modes: GEPA (framing) then ContentEvolver[/bold cyan]")
        if v2:
            from evolution.core.gepa_v2_dispatch import v2_dispatch
            v2_dispatch(
                skill_name=skill,
                iterations=iterations,
                eval_source=eval_source,
                dataset_path=dataset_path,
                optimizer_model=optimizer_model,
                eval_model=eval_model,
                hermes_repo=hermes_repo,
                run_tests=run_tests,
                dry_run=dry_run,
                stats_csv=stats_csv,
            )
        else:
            evolve(
                skill_name=skill,
                iterations=iterations,
                eval_source=eval_source,
                dataset_path=dataset_path,
                optimizer_model=optimizer_model,
                eval_model=eval_model,
                hermes_repo=hermes_repo,
                run_tests=run_tests,
                dry_run=dry_run,
                stats_csv=stats_csv,
                override_breaker=override_breaker,
            )
        from evolution.skills.evolve_content import evolve_content
        evolve_content(
            skill_name=skill,
            eval_source=eval_source,
            dataset_path=dataset_path,
            evaluator_model=eval_model,
            rewrite_model=eval_model,
            hermes_repo=hermes_repo,
            dry_run=dry_run,
        )
    elif v2:
        from evolution.core.gepa_v2_dispatch import v2_dispatch
        v2_dispatch(
            skill_name=skill,
            iterations=iterations,
            eval_source=eval_source,
            dataset_path=dataset_path,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
            hermes_repo=hermes_repo,
            run_tests=run_tests,
            dry_run=dry_run,
            stats_csv=stats_csv,
        )
    else:
        evolve(
            skill_name=skill,
            iterations=iterations,
            eval_source=eval_source,
            dataset_path=dataset_path,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
            hermes_repo=hermes_repo,
            run_tests=run_tests,
            dry_run=dry_run,
            stats_csv=stats_csv,
            override_breaker=override_breaker,
        )


if __name__ == "__main__":
    main()
