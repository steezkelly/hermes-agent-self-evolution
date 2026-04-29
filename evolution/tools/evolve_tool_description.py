"""Evolve Hermes Agent tool descriptions using DSPy + GEPA.

Phase 2 of the self-evolution pipeline.  Tool descriptions are the
description field in tool schemas — they are what the model reads when
deciding which tool to call.  Evolving them improves tool-selection
accuracy.

Usage:
    python -m evolution.tools.evolve_tool_description --tool search_files --iterations 10
    python -m evolution.tools.evolve_tool_description --all-tools --iterations 5
    python -m evolution.tools.evolve_tool_description --tool read_file --eval-source sessiondb
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# GEPA v2 imports
from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.nous_auth import _get_lm_kwargs

from evolution.tools.tool_module import (
    ToolDescriptionStore,
    ToolDescriptionModule,
    UNCHANGED,
)
from evolution.tools.tool_dataset_builder import (
    build_dataset,
    ToolDescriptionDataset,
)
from evolution.tools.tool_description_v2 import (
    run_tool_description_v2,
    ToolDescriptionConstraintValidator,
    batch_tool_selection_accuracy,
)

console = Console()


# ------------------------------------------------------------------
# Evolution output helpers
# ------------------------------------------------------------------

def _compute_improvement(
    baseline_acc: float, evolved_acc: float
) -> dict:
    delta = evolved_acc - baseline_acc
    rel_improvement = (delta / baseline_acc * 100) if baseline_acc > 0 else 0.0
    return {
        "delta": delta,
        "relative_pct": rel_improvement,
        "significant": delta > 0.01,
    }


def _save_output(
    output_dir: Path,
    tool_name: str,
    baseline_store: ToolDescriptionStore,
    evolved_store: ToolDescriptionStore,
    baseline_acc: float,
    evolved_acc: float,
    train_acc: float,
    test_acc: float,
    elapsed_seconds: float,
    improvement: dict,
    recommendation: str,
) -> Path:
    """Save evolution run output to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Diff of descriptions
    diff = {}
    for name in evolved_store.tools:
        old = baseline_store.descriptions.get(name, "")
        new = evolved_store.descriptions.get(name, "")
        if old != new:
            diff[name] = {"before": old, "after": new}

    run_data = {
        "tool_name": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_accuracy": baseline_acc,
        "evolved_accuracy": evolved_acc,
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "elapsed_seconds": elapsed_seconds,
        "improvement": improvement,
        "recommendation": recommendation,
        "diff": diff,
        "total_tools": len(evolved_store.tools),
        "changed_tools": list(diff.keys()),
    }

    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(run_data, indent=2))

    # Save full evolved descriptions
    descriptions_path = output_dir / "descriptions.json"
    descriptions_path.write_text(evolved_store.to_json())

    # Save baseline
    baseline_path = output_dir / "baseline_descriptions.json"
    baseline_path.write_text(baseline_store.to_json())

    return report_path


# ------------------------------------------------------------------
# Main evolution function
# ------------------------------------------------------------------

def evolve(
    tool_name: str,
    iterations: int = 10,
    eval_source: str = "synthetic",
    optimizer_model: str = "minimax/minimax-m2.7",
    eval_model: str = "minimax/minimax-m2.7",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
    num_synthetic: int = 5,
) -> dict:
    """Evolve one or more tool descriptions.

    Args:
        tool_name:       Tool name to evolve, or "all" for all tools
        iterations:      GEPA iterations
        eval_source:     "synthetic" (default), "sessiondb", or "both"
        optimizer_model: Model for GEPA optimizer
        eval_model:      Model for evaluation
        hermes_repo:     Path to hermes-agent repo
        dry_run:         Don't run evolution, just show what would happen
        num_synthetic:   Synthetic examples per tool

    Returns:
        dict with accuracy metrics, recommendation, output path
    """
    config = EvolutionConfig(
        iterations=iterations,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        judge_model=eval_model,
        run_pytest=False,  # Not applicable for tool descriptions
    )
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    # ── 1. Load tool descriptions from registry ─────────────────────
    console.print(
        f"\n[bold cyan]🧬 Tool Description Evolution[/bold cyan]"
        f" — Target: [bold]{tool_name}[/bold]\n"
    )

    try:
        baseline_store = ToolDescriptionStore.from_hermes_registry(
            config.hermes_agent_path
        )
    except Exception as e:
        console.print(f"[red]✗ Failed to load tool registry: {e}[/red]")
        sys.exit(1)

    # Filter to target tool(s)
    if tool_name != "all":
        if tool_name not in baseline_store.descriptions:
            console.print(
                f"[red]✗ Tool '{tool_name}' not found in registry. "
                f"Available: {', '.join(sorted(baseline_store.tools)[:10])}...[/red]"
            )
            sys.exit(1)
        tool_filter = {tool_name}
    else:
        tool_filter = None

    console.print(
        f"[dim]Loaded {len(baseline_store)} tools from registry "
        f"({'single tool' if tool_filter else 'all tools'})[/dim]"
    )

    # ── 2. Build evaluation dataset ──────────────────────────────────
    console.print(f"[dim]Building eval dataset (source={eval_source})...[/dim]")

    dataset = build_dataset(
        tool_store=baseline_store,
        config=config,
        eval_source=eval_source,
        num_synthetic=num_synthetic,
        tool_filter=tool_filter,
    )

    if len(dataset) == 0:
        console.print("[red]✗ No eval examples generated[/red]")
        sys.exit(1)

    train_set, val_set, test_set = dataset.split()
    console.print(
        f"[dim]Dataset: {len(dataset)} total "
        f"({len(train_set)} train / {len(val_set)} val / {len(test_set)} test)[/dim]"
    )

    # ── 3. Baseline accuracy ─────────────────────────────────────────
    baseline_module = ToolDescriptionModule(baseline_store)
    baseline_acc = batch_tool_selection_accuracy(
        baseline_module, val_set, config
    )
    baseline_acc_train = batch_tool_selection_accuracy(
        baseline_module, train_set, config
    )
    console.print(
        f"[dim]Baseline accuracy: {baseline_acc:.3f} (val, n={len(val_set)}) / "
        f"{baseline_acc_train:.3f} (train, n={len(train_set)})[/dim]"
    )

    if dry_run:
        # Show per-example breakdown for debugging
        from evolution.tools.tool_module import _format_tool_descriptions
        module = ToolDescriptionModule(baseline_store)
        console.print("[dim]Per-example predictions:[/dim]")
        for i in range(len(val_set)):
            e = val_set[i]
            try:
                pred = module(e["task"])
                match = pred.predicted_tool.strip().lower() == e["tool_name"].strip().lower()
                console.print(
                    f"  [{i}] task={e['task'][:50]} expected={e['tool_name']} "
                    f"predicted={pred.predicted_tool.strip()!r} match={match}"
                )
            except Exception as ex:
                console.print(f"  [{i}] ERROR: {type(ex).__name__}: {ex}")
        console.print("[yellow]Dry run — exiting before evolution[/yellow]")
        return {
            "tool_name": tool_name,
            "baseline_accuracy": baseline_acc,
            "baseline_accuracy_train": baseline_acc_train,
            "recommendation": "dry_run",
        }

    # ── 4. Run v2 GEPA evolution ───────────────────────────────────────
    console.print(f"\n[bold cyan]Running GEPA v2 evolution ({iterations} iters)...[/bold cyan]")

    start_time = time.time()

    (
        evolved_store,
        best_score,
        best_attempt,
        all_attempt_metrics,
        pareto_front,
        report,
    ) = run_tool_description_v2(
        tool_name=tool_name,
        tool_store=baseline_store,
        dataset=val_set,
        config=config,
        constraint_validator=ToolDescriptionConstraintValidator(),
    )

    elapsed = time.time() - start_time

    # ── 5. Compute final test accuracy ───────────────────────────────
    evolved_test_acc = batch_tool_selection_accuracy(
        ToolDescriptionModule(evolved_store), test_set, config
    )
    evolved_train_acc = batch_tool_selection_accuracy(
        ToolDescriptionModule(evolved_store), train_set, config
    )

    improvement = _compute_improvement(baseline_acc, best_score)

    # Determine recommendation
    if best_score <= baseline_acc:
        recommendation = "reject"
    elif improvement["relative_pct"] < 5.0:
        recommendation = "reject"
    else:
        recommendation = "accept"

    # ── 6. Save output ────────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tool_slug = tool_name.replace("/", "_")
    output_dir = (
        Path(__file__).parent.parent.parent
        / "output"
        / "tool_descriptions"
        / f"{tool_slug}_{timestamp}"
    )

    report_path = _save_output(
        output_dir=output_dir,
        tool_name=tool_name,
        baseline_store=baseline_store,
        evolved_store=evolved_store,
        baseline_acc=baseline_acc,
        evolved_acc=best_score,
        train_acc=evolved_train_acc,
        test_acc=evolved_test_acc,
        elapsed_seconds=elapsed,
        improvement=improvement,
        recommendation=recommendation,
    )

    # ── 7. Print summary ──────────────────────────────────────────────
    console.print(f"\n[bold]Results[/bold]")
    table = Table(show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Tool", tool_name)
    table.add_row("Baseline accuracy (val)", f"{baseline_acc:.4f}")
    table.add_row("Evolved accuracy (val)", f"{best_score:.4f}")
    table.add_row("Test accuracy", f"{evolved_test_acc:.4f}")
    table.add_row("Improvement", f"{improvement['delta']:+.4f} ({improvement['relative_pct']:+.1f}%)")
    table.add_row("Recommendation", f"[bold {'green' if recommendation == 'accept' else 'red'}]{recommendation.upper()}[/]")
    table.add_row("Elapsed", f"{elapsed:.1f}s")
    table.add_row("Output", str(report_path))
    console.print(table)

    # Show changed descriptions
    changed = [
        name for name in evolved_store.tools
        if evolved_store.descriptions.get(name) != baseline_store.descriptions.get(name)
    ]
    if changed:
        console.print(f"\n[bold]Changed descriptions ({len(changed)}):[/bold]")
        for name in changed[:10]:
            old = baseline_store.descriptions.get(name, "")[:80]
            new = evolved_store.descriptions.get(name, "")[:80]
            console.print(f"  {name}:")
            console.print(f"    Before: {old}")
            console.print(f"    After:  {new}")

    return {
        "tool_name": tool_name,
        "baseline_accuracy": baseline_acc,
        "evolved_accuracy": best_score,
        "test_accuracy": evolved_test_acc,
        "train_accuracy": evolved_train_acc,
        "improvement": improvement,
        "recommendation": recommendation,
        "output_dir": str(output_dir),
        "elapsed_seconds": elapsed,
        "all_attempt_metrics": all_attempt_metrics,
    }


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

@click.command()
@click.option(
    "--tool",
    "tool_name",
    default="search_files",
    help="Tool name to evolve (or 'all' for every tool)",
)
@click.option(
    "--iterations",
    "-n",
    default=10,
    help="Number of GEPA iterations",
)
@click.option(
    "--eval-source",
    default="synthetic",
    type=click.Choice(["synthetic", "sessiondb", "both"]),
    help="Source for evaluation dataset",
)
@click.option(
    "--optimizer-model",
    default="minimax/minimax-m2.7",
    help="Model for GEPA optimizer (provider/model format)",
)
@click.option(
    "--eval-model",
    default="minimax/minimax-m2.7",
    help="Model for evaluation",
)
@click.option(
    "--hermes-repo",
    default=None,
    help="Path to hermes-agent repo (default: auto-detect)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show baseline accuracy without evolving",
)
@click.option(
    "--num-synthetic",
    default=5,
    help="Synthetic examples per tool",
)
def cli(
    tool_name: str,
    iterations: int,
    eval_source: str,
    optimizer_model: str,
    eval_model: str,
    hermes_repo: Optional[str],
    dry_run: bool,
    num_synthetic: int,
):
    """Evolve Hermes Agent tool descriptions.

    Examples:

      # Evolve a single tool's description
      python -m evolution.tools.evolve_tool_description --tool search_files

      # Evolve all tool descriptions
      python -m evolution.tools.evolve_tool_description --tool all --iterations 5

      # Use session history as eval data
      python -m evolution.tools.evolve_tool_description --tool read_file \\
          --eval-source sessiondb

      # Quick dry run (no evolution, just baseline accuracy)
      python -m evolution.tools.evolve_tool_description --tool patch --dry-run
    """
    evolve(
        tool_name=tool_name,
        iterations=iterations,
        eval_source=eval_source,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        num_synthetic=num_synthetic,
    )


if __name__ == "__main__":
    cli()
