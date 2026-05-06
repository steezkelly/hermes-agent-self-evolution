"""Evolve a Hermes Agent skill using ContentEvolver (section-level rewriting).

Usage:
    # Content evolution only
    python -m evolution.skills.evolve_content \
        --skill companion-roundtable \
        --eval-source sessiondb \
        --rewrite-budget 3

    # Framing + content in sequence
    python -m evolution.skills.evolve_skill \
        --skill companion-roundtable \
        --mode both \
        --eval-source sessiondb
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
import dspy
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.dataset_builder import SyntheticDatasetBuilder, EvalDataset, GoldenDatasetLoader
from evolution.core.external_importers import build_dataset_from_external
from evolution.core.fitness import skill_fitness_metric, fit_global_scorer, fit_embedding_scorer
from evolution.core.nous_auth import _get_lm_kwargs
from evolution.skills.skill_module import (
    load_skill,
    find_skill,
    reassemble_skill,
)
from evolution.skills.content_evolver import ContentEvolver

console = Console()


def evolve_content(
    skill_name: str,
    eval_source: str = "synthetic",
    dataset_path: Optional[str] = None,
    evaluator_model: str = "minimax/minimax-m2.7",
    rewrite_model: str = "minimax/minimax-m2.7",
    rewrite_budget: int = 3,
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
    weak_fraction: float = 1/3,
    verbose: bool = True,
) -> tuple[str, dict]:
    """Run ContentEvolver on a skill.

    Returns:
        (evolved_full_text, metrics_dict)
    """
    config = EvolutionConfig(
        optimizer_model=evaluator_model,
        eval_model=evaluator_model,
        judge_model=evaluator_model,
    )
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    if verbose:
        console.print(f"\n[bold cyan]ContentEvolver[/bold cyan] -- Evolving skill: [bold]{skill_name}[/bold]\n")

    skill_path = find_skill(skill_name, config.hermes_agent_path)
    if not skill_path:
        console.print(f"[red]Skill '{skill_name}' not found[/red]")
        sys.exit(1)

    skill = load_skill(skill_path)
    if dry_run:
        console.print("[bold green]DRY RUN -- setup validated[/bold green]")
        return skill["raw"], {}

    # Build or load evaluation dataset (same logic as GEPA)
    if verbose:
        console.print(f"Building evaluation dataset (source: {eval_source})")

    if eval_source == "golden" and dataset_path:
        dataset = GoldenDatasetLoader.load(Path(dataset_path))
    elif eval_source == "sessiondb":
        save_path = Path(dataset_path) if dataset_path else Path("datasets") / "skills" / skill_name
        dataset = build_dataset_from_external(
            skill_name=skill_name,
            skill_text=skill["raw"],
            sources=["claude-code", "copilot", "hermes"],
            output_path=save_path,
            model=evaluator_model,
        )
        if not dataset.all_examples:
            console.print("[red]No relevant examples found from session history[/red]")
            sys.exit(1)
    elif eval_source == "synthetic":
        builder = SyntheticDatasetBuilder(config)
        dataset = builder.generate(
            artifact_text=skill["raw"],
            artifact_type="skill",
        )
        save_path = Path("datasets") / "skills" / skill_name
        dataset.save(save_path)
    elif dataset_path:
        dataset = EvalDataset.load(Path(dataset_path))
    else:
        console.print("[red]Specify --dataset-path or use --eval-source synthetic[/red]")
        sys.exit(1)

    # Fit scorers
    trainset = dataset.to_dspy_examples("train")
    valset = dataset.to_dspy_examples("val")
    fit_global_scorer(trainset + valset)
    fit_embedding_scorer(trainset + valset)

    # Configure evaluator LM
    lm_kwargs, eval_model_used = _get_lm_kwargs(evaluator_model)
    lm_kwargs["num_retries"] = 8
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    holdout_examples = dataset.to_dspy_examples("holdout")

    # Run ContentEvolver
    evolver = ContentEvolver(
        config=config,
        evaluator_model=evaluator_model,
        rewrite_model=rewrite_model,
        k_candidates=rewrite_budget,
        weak_fraction=weak_fraction,
    )

    evolved_full, metrics = evolver.evolve(
        skill_name=skill_name,
        holdout_examples=holdout_examples,
        verbose=verbose,
    )

    # Save output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / skill_name / f"content_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "evolved_skill.md").write_text(evolved_full)
    (output_dir / "baseline_skill.md").write_text(skill["raw"])
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    if verbose:
        console.print(f"\nOutput saved to {output_dir}/")
        improvement = metrics.get("improvement", 0)
        if improvement > 0:
            console.print(f"[bold green]ContentEvolver improved skill by {improvement:+.3f}[/bold green]")
        else:
            console.print(f"[yellow]ContentEvolver did not improve skill[/yellow]")

    return evolved_full, metrics


@click.command()
@click.option("--skill", required=True, help="Name of the skill to evolve")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "golden", "sessiondb"]),
              help="Source for evaluation dataset")
@click.option("--dataset-path", default=None, help="Path to existing eval dataset (JSONL)")
@click.option("--evaluator-model", default="minimax/minimax-m2.7", help="Model for section scoring")
@click.option("--rewrite-model", default="minimax/minimax-m2.7", help="Model for section rewriting")
@click.option("--rewrite-budget", default=3, help="Number of candidate rewrites per weak section")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--weak-fraction", default=1/3, type=float, help="Fraction of sections to rewrite")
@click.option("--dry-run", is_flag=True, help="Validate setup without running evolution")
def main(skill, eval_source, dataset_path, evaluator_model, rewrite_model, rewrite_budget, hermes_repo, weak_fraction, dry_run):
    """Evolve a Hermes Agent skill's content using section-level rewriting."""
    evolve_content(
        skill_name=skill,
        eval_source=eval_source,
        dataset_path=dataset_path,
        evaluator_model=evaluator_model,
        rewrite_model=rewrite_model,
        rewrite_budget=rewrite_budget,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        weak_fraction=weak_fraction,
    )


if __name__ == "__main__":
    main()
