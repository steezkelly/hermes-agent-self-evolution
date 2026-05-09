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
from evolution.core.fitness import skill_fitness_metric, LLMJudge, FitnessScore
from evolution.core.constraints import ConstraintValidator, ConstraintResult
from evolution.skills.skill_module import (
    SkillModule,
    load_skill,
    find_skill,
    reassemble_skill,
)

console = Console()


def _create_gepa_optimizer(iterations: int, optimizer_model: str):
    """Create a DSPy 3.x GEPA optimizer.

    DSPy 3.x removed the old ``max_steps`` argument and requires a reflection
    LM for GEPA's proposal/reflection loop. Keep this construction isolated so
    it is easy to test against future DSPy API drift.
    """
    reflection_lm = dspy.LM(optimizer_model)
    return dspy.GEPA(
        metric=skill_fitness_metric,
        max_metric_calls=max(1, iterations * 20),
        reflection_lm=reflection_lm,
    )


def _run_pytest_gate_if_requested(
    validator: ConstraintValidator,
    config: EvolutionConfig,
) -> Optional[ConstraintResult]:
    """Run the pytest promotion gate when enabled.

    Returns the test-suite constraint result when ``config.run_pytest`` is true;
    otherwise returns ``None`` so callers can distinguish "skipped" from
    "passed".
    """
    if not config.run_pytest:
        return None
    return validator.run_test_suite(config.hermes_agent_path)


def _save_failed_variant(skill_name: str, evolved_full: str, suffix: str = "FAILED") -> Path:
    """Save a rejected evolved skill variant for inspection."""
    output_path = Path("output") / skill_name / f"evolved_{suffix}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(evolved_full)
    return output_path


def _require_non_empty_holdout(dataset: EvalDataset) -> None:
    """Fail fast when holdout scoring would be meaningless.

    Without holdout examples, the previous average-score calculation silently
    produced 0.000/0.000 scores via ``max(1, len(scores))`` denominators. That
    hides dataset construction mistakes and makes optimization reports look
    valid when no independent evaluation occurred.
    """
    if dataset.holdout:
        return

    total = len(dataset.all_examples)
    raise click.ClickException(
        "Evaluation dataset has 0 holdout examples; cannot compute an "
        f"independent holdout score from {total} total examples. Provide a "
        "larger dataset or adjust train/val/holdout ratios."
    )


def _require_constraints_pass(
    results: list[ConstraintResult],
    *,
    artifact_label: str,
) -> None:
    """Fail fast when a required constraint gate has failures."""
    failures = [result for result in results if not result.passed]
    if not failures:
        return

    details = "; ".join(
        f"{failure.constraint_name}: {failure.message}" for failure in failures
    )
    raise click.ClickException(f"{artifact_label} failed constraints: {details}")


def _validate_baseline_constraints(
    skill: dict,
    validator: ConstraintValidator,
) -> list[ConstraintResult]:
    """Validate the complete baseline skill file, including frontmatter."""
    return validator.validate_all(skill["raw"], "skill")


def evolve(
    skill_name: str,
    iterations: int = 10,
    eval_source: str = "synthetic",
    dataset_path: Optional[str] = None,
    optimizer_model: str = "openai/gpt-4.1",
    eval_model: str = "openai/gpt-4.1-mini",
    hermes_repo: Optional[str] = None,
    run_tests: bool = False,
    dry_run: bool = False,
    write_report: bool = True,
    report_dir: str = "reports/runs",
    run_benchmark_gate: bool = False,
    prepare_pr: bool = False,
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
    console.print(f"  Loaded: {skill_path.relative_to(config.hermes_agent_path)}")
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
    _require_non_empty_holdout(dataset)

    # ── 3. Validate constraints on baseline ─────────────────────────────
    console.print(f"\n[bold]Validating baseline constraints[/bold]")
    validator = ConstraintValidator(config)
    baseline_constraints = _validate_baseline_constraints(skill, validator)
    for c in baseline_constraints:
        icon = "✓" if c.passed else "✗"
        color = "green" if c.passed else "red"
        console.print(f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}")

    _require_constraints_pass(baseline_constraints, artifact_label="Baseline skill")

    # ── 4. Set up DSPy + GEPA optimizer ─────────────────────────────────
    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Optimizer: GEPA ({iterations} iterations)")
    console.print(f"  Optimizer model: {optimizer_model}")
    console.print(f"  Eval model: {eval_model}")

    # Configure DSPy
    lm = dspy.LM(eval_model)
    dspy.configure(lm=lm)

    # Create the baseline skill module
    baseline_module = SkillModule(skill["body"])

    # Prepare DSPy examples
    trainset = dataset.to_dspy_examples("train")
    valset = dataset.to_dspy_examples("val")

    # ── 5. Run GEPA optimization ────────────────────────────────────────
    console.print(f"\n[bold cyan]Running GEPA optimization ({iterations} iterations)...[/bold cyan]\n")

    start_time = time.time()

    try:
        optimizer = _create_gepa_optimizer(iterations, optimizer_model)

        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
            valset=valset,
        )
    except Exception as e:
        # Fall back to MIPROv2 if GEPA isn't available in this DSPy version
        console.print(f"[yellow]GEPA not available ({e}), falling back to MIPROv2[/yellow]")
        optimizer = dspy.MIPROv2(
            metric=skill_fitness_metric,
            auto="light",
        )
        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
        )

    elapsed = time.time() - start_time
    console.print(f"\n  Optimization completed in {elapsed:.1f}s")

    # ── 6. Extract evolved skill text ───────────────────────────────────
    # The optimized module's instructions contain the evolved skill text
    evolved_body = optimized_module.skill_text
    evolved_full = reassemble_skill(skill["frontmatter"], evolved_body)

    # ── 7. Validate evolved skill ───────────────────────────────────────
    console.print(f"\n[bold]Validating evolved skill[/bold]")
    evolved_constraints = validator.validate_all(evolved_body, "skill", baseline_text=skill["body"])
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
        output_path = _save_failed_variant(skill_name, evolved_full)
        console.print(f"  Saved failed variant to {output_path}")
        return

    # ── 8. Optional pytest promotion gate ────────────────────────────────
    pytest_result = _run_pytest_gate_if_requested(validator, config)
    if pytest_result is not None:
        icon = "✓" if pytest_result.passed else "✗"
        color = "green" if pytest_result.passed else "red"
        console.print(f"  [{color}]{icon} {pytest_result.constraint_name}[/{color}]: {pytest_result.message}")
        if pytest_result.details:
            console.print(f"    {pytest_result.details}")
        if not pytest_result.passed:
            console.print("[red]✗ Evolved skill FAILED pytest gate — not deploying[/red]")
            output_path = _save_failed_variant(skill_name, evolved_full, "FAILED_TESTS")
            console.print(f"  Saved failed variant to {output_path}")
            return

    # ── 9. Evaluate on holdout set ──────────────────────────────────────
    console.print(f"\n[bold]Evaluating on holdout set ({len(dataset.holdout)} examples)[/bold]")

    holdout_examples = dataset.to_dspy_examples("holdout")

    baseline_scores = []
    evolved_scores = []
    for ex in holdout_examples:
        # Score baseline
        with dspy.context(lm=lm):
            baseline_pred = baseline_module(task_input=ex.task_input)
            baseline_score = skill_fitness_metric(ex, baseline_pred)
            baseline_scores.append(float(baseline_score))

            evolved_pred = optimized_module(task_input=ex.task_input)
            evolved_score = skill_fitness_metric(ex, evolved_pred)
            evolved_scores.append(float(evolved_score))

    avg_baseline = sum(baseline_scores) / max(1, len(baseline_scores))
    avg_evolved = sum(evolved_scores) / max(1, len(evolved_scores))
    improvement = avg_evolved - avg_baseline

    # ── 10. Report results ──────────────────────────────────────────────
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

    # ── 11. Save output ─────────────────────────────────────────────────
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
        "eval_model": eval_model,
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

    if write_report:
        from evolution.core.benchmark_gate import evaluate_report
        from evolution.core.pr_builder import build_pr_text
        from evolution.core.run_report import write_run_report

        report_path = write_run_report(
            target_name=skill_name,
            target_type="skill",
            baseline_path=output_dir / "baseline_skill.md",
            optimized_path=output_dir / "evolved_skill.md",
            dataset=dataset,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
            optimizer_type=type(optimizer).__name__,
            constraints=evolved_constraints,
            baseline_score=avg_baseline,
            optimized_score=avg_evolved,
            elapsed_seconds=elapsed,
            report_dir=Path(report_dir),
        )
        console.print(f"  Run report: {report_path}")

        if run_benchmark_gate:
            gate_result = evaluate_report(report_path)
            report = json.loads(report_path.read_text())
            report["benchmark_gate"] = gate_result.to_dict()
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
            gate_label = "PASS" if gate_result.passed else "FAIL"
            console.print(f"  Benchmark gate: {gate_label}")
            if not gate_result.passed:
                console.print("[red]✗ Benchmark gate failed — not preparing PR[/red]")
                prepare_pr = False

        if prepare_pr:
            title, body = build_pr_text(report_path)
            pr_body_path = output_dir / "PR_BODY.md"
            pr_body_path.write_text(f"# {title}\n\n{body}\n")
            console.print(f"  PR body: {pr_body_path}")

    console.print(f"\n  Output saved to {output_dir}/")

    if improvement > 0:
        console.print(f"\n[bold green]✓ Evolution improved skill by {improvement:+.3f} ({improvement/max(0.001, avg_baseline)*100:+.1f}%)[/bold green]")
        console.print(f"  Review the diff: diff {output_dir}/baseline_skill.md {output_dir}/evolved_skill.md")
    else:
        console.print(f"\n[yellow]⚠ Evolution did not improve skill (change: {improvement:+.3f})[/yellow]")
        console.print("  Try: more iterations, better eval dataset, or different optimizer model")


@click.command()
@click.option("--skill", required=True, help="Name of the skill to evolve")
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "golden", "sessiondb"]),
              help="Source for evaluation dataset")
@click.option("--dataset-path", default=None, help="Path to existing eval dataset (JSONL)")
@click.option("--optimizer-model", default="openai/gpt-4.1", help="Model for GEPA reflections")
@click.option("--eval-model", default="openai/gpt-4.1-mini", help="Model for evaluations")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--run-tests", is_flag=True, help="Run full pytest suite as constraint gate")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--write-report/--no-write-report", default=True, help="Write a machine-readable run report")
@click.option("--report-dir", default="reports/runs", help="Directory for run reports")
@click.option("--run-benchmark-gate", is_flag=True, help="Evaluate the run report with benchmark gates")
@click.option("--prepare-pr", is_flag=True, help="Write a local PR body artifact from the run report")
def main(skill, iterations, eval_source, dataset_path, optimizer_model, eval_model, hermes_repo, run_tests, dry_run, write_report, report_dir, run_benchmark_gate, prepare_pr):
    """Evolve a Hermes Agent skill using DSPy + GEPA optimization."""
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
        write_report=write_report,
        report_dir=report_dir,
        run_benchmark_gate=run_benchmark_gate,
        prepare_pr=prepare_pr,
    )


if __name__ == "__main__":
    main()
