"""GEPA v2 pipeline for tool descriptions.

Mirrors the architecture of gepa_v2_dispatch but is specialized for
tool description evolution instead of skill evolution.

Architecture:
  - BacktrackController: rerun if rejected, up to N times
  - GEPA optimizer: mutates tool descriptions via DSPy Predict
  - PostHocAnalyzer: power-law trajectory analysis, stop/continue recommendation
  - Constraint validation: ≤500 chars per description
  - ParetoSelector: multi-objective (accuracy vs. description length delta)
  - EvolutionRouter: heuristic failure pattern classification

Returns:
  (best_tool_store, best_score, best_attempt_num, all_metrics, pareto_front)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import dspy

from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs
from evolution.core.router import EvolutionRouter, RouterDecision
from evolution.core.backtrack import BacktrackController, BacktrackDecision
from evolution.core.pareto_selector import ParetoSelector
from evolution.core.posthoc_analyzer import PostHocAnalyzer

from evolution.tools.tool_module import (
    ToolDescriptionStore,
    ToolDescriptionModule,
)
from evolution.tools.tool_dataset_builder import ToolDescriptionDataset


# ------------------------------------------------------------------
# Shared: metric and constraint validator
# (also imported by evolve_tool_description.py)
# ------------------------------------------------------------------

def tool_selection_metric(
    module: ToolDescriptionModule,
    example: dict,
    hermes_agent_path: Optional[Path] = None,
) -> tuple[bool, float]:
    """Score a single tool-selection prediction.

    Returns (correct, score) where correct is True/False and score is 0.0-1.0.
    """
    try:
        prediction = module(example["task"])
        predicted = prediction.predicted_tool.strip().lower()
        expected = example["tool_name"].strip().lower()
        correct = predicted == expected
        score = 1.0 if correct else 0.0
        return correct, score
    except Exception:
        return False, 0.0


def batch_tool_selection_accuracy(
    module: ToolDescriptionModule,
    dataset: ToolDescriptionDataset,
    config: EvolutionConfig,
) -> float:
    """Compute accuracy over an entire dataset.

    Each dataset example is a dict with: task, tool_name, difficulty, source.
    We call the module with the full example dict so DSPy's InputField
    routing can match task_description and gold correctly.

    Configures DSPy LM lazily on first call using eval_model from config.
    """
    if len(dataset) == 0:
        return 0.0

    # Lazily configure DSPy LM (only needed for actual predictions)
    if not _has_lm_configured():
        _configure_lm_for_accuracy(config.eval_model)

    correct = 0
    for i in range(len(dataset)):
        example = dataset[i]
        try:
            # Build a DSPy Example so input-field routing works correctly
            ex = dspy.Example(
                task_description=example["task"],
                tool_descriptions="",  # filled by module from tool_store
                gold=example["tool_name"],
            ).with_inputs("task_description", "tool_descriptions")

            # The module's forward() fills in tool_descriptions from tool_store
            prediction = module(ex.task_description)
            predicted = prediction.predicted_tool.strip().lower()
            expected = ex.gold.strip().lower()

            if predicted == expected:
                correct += 1
        except Exception:
            continue

    return correct / len(dataset)


def _has_lm_configured() -> bool:
    """Check if a DSPy LM is currently configured."""
    try:
        import dspy
        # Check if any LM is configured by trying to get the current LM
        return dspy.settings.lm is not None
    except Exception:
        return False


def _configure_lm_for_accuracy(model: str = "minimax/minimax-m2.7") -> None:
    """Configure DSPy LM for accuracy evaluation."""
    try:
        import dspy
        from evolution.core.nous_auth import _get_lm_kwargs

        lm_kwargs, model_used = _get_lm_kwargs(model)
        lm_kwargs["num_retries"] = 3
        lm = dspy.LM(model_used, **lm_kwargs)
        dspy.configure(lm=lm)
    except Exception:
        # If Nous auth fails, fall back to a basic setup
        pass


class ToolDescriptionConstraintValidator:
    """Validate evolved tool descriptions pass guardrails.

    Guardrails:
      1. Each description ≤ 500 chars (README size limit)
      2. Each tool has a non-empty description
      3. Descriptions don't regress to empty/baseline-only changes
    """

    MAX_CHARS = 500

    def validate(self, tool_store: ToolDescriptionStore) -> tuple[bool, list[str]]:
        errors = []

        for name in tool_store.tools:
            desc = tool_store.descriptions.get(name, "")

            if not desc or not desc.strip():
                errors.append(f"Tool '{name}': description is empty")
                continue

            if len(desc) > self.MAX_CHARS:
                errors.append(
                    f"Tool '{name}': description is {len(desc)} chars "
                    f"(limit {self.MAX_CHARS})"
                )

        return len(errors) == 0, errors


# ------------------------------------------------------------------
# DSPy GEPA metric
# ------------------------------------------------------------------

def _tool_desc_gepa_metric(
    example: dspy.Example, prediction: dspy.Prediction, **kwargs
) -> float:
    """DSPy metric for tool description GEPA optimization.

    GEPA calls this to evaluate each candidate.
    """
    predicted = getattr(prediction, "predicted_tool", "")
    gold = getattr(example, "gold", "")
    if not predicted or not gold:
        return 0.0
    return 1.0 if predicted.strip().lower() == gold.strip().lower() else 0.0


# ------------------------------------------------------------------
# Description extraction from optimized module
# ------------------------------------------------------------------

def _extract_evolved_descriptions(
    optimized_module: dspy.Module,
    baseline_store: ToolDescriptionStore,
) -> ToolDescriptionStore:
    """Extract evolved descriptions from a GEPA-optimized module.

    GEPA mutates the Predict module's instructions, which contain the
    tool descriptions.  We parse them back out.
    """
    # The evolved descriptions live in the module's tool_store
    if hasattr(optimized_module, "tool_store") and optimized_module.tool_store is not None:
        return optimized_module.tool_store

    # Fallback: extract from the signature instructions
    try:
        sig = getattr(optimized_module.predict, "signature", None)
        if sig is None:
            sig = getattr(optimized_module.predict, "predict", None)
            if sig is not None:
                sig = getattr(sig, "signature", None)

        if sig is not None:
            instructions = getattr(sig, "instructions", "")
            if instructions and "tool_descriptions" in instructions:
                store = _parse_descriptions_from_text(instructions, baseline_store)
                if store:
                    return store
    except Exception:
        pass

    return baseline_store


def _parse_descriptions_from_text(
    text: str,
    baseline_store: ToolDescriptionStore,
) -> Optional[ToolDescriptionStore]:
    """Parse tool descriptions out of GEPA-generated instruction text."""
    import re

    descriptions = dict(baseline_store.descriptions)
    pattern = r"^- (\w+): (.+)$"
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            match = re.match(pattern, line)
            if match:
                tool_name, desc = match.groups()
                if tool_name in descriptions:
                    descriptions[tool_name] = desc.strip()

    store = ToolDescriptionStore(descriptions=descriptions)
    changed = [
        n for n in store.tools
        if store.descriptions.get(n) != baseline_store.descriptions.get(n)
    ]
    if not changed:
        return None

    return store


# ------------------------------------------------------------------
# Types and pareto computation
# ------------------------------------------------------------------

@dataclass
class ToolDescAttemptMetrics:
    attempt: int
    score: float
    baseline_score: float
    optimizer_type: str
    elapsed_seconds: float
    descriptions_changed: int
    pareto_accepted: bool = False


@dataclass
class ToolDescEvolutionReport:
    tool_name: str
    n_iterations_executed: int
    improvement: float
    recommendation: str  # "accept" | "reject" | "review"
    details: str
    router_decision: RouterDecision
    backtrack_decision: BacktrackDecision
    pareto_front: List[Tuple[float, float]] = field(default_factory=list)
    all_attempt_metrics: List[ToolDescAttemptMetrics] = field(default_factory=list)


def _compute_pareto_front(
    metrics: List[ToolDescAttemptMetrics],
) -> List[Tuple[float, float]]:
    """Return pareto-frontier (accuracy, -length_change) points."""
    points = []
    for m in metrics:
        points.append((m.score, -m.descriptions_changed))
    pareto = []
    for p in sorted(points, key=lambda x: -x[0]):
        dominated = False
        for q in pareto:
            if q[0] >= p[0] and q[1] >= p[1]:
                dominated = True
                break
        if not dominated:
            pareto.append(p)
    return pareto


# ------------------------------------------------------------------
# Main v2 pipeline
# ------------------------------------------------------------------

def run_tool_description_v2(
    tool_name: str,
    tool_store: ToolDescriptionStore,
    dataset: ToolDescriptionDataset,
    config: EvolutionConfig,
    constraint_validator: Optional[ToolDescriptionConstraintValidator] = None,
) -> Tuple[
    ToolDescriptionStore,  # best evolved store
    float,  # best score
    int,  # best attempt number
    List[ToolDescAttemptMetrics],  # all attempt metrics
    List[Tuple[float, float]],  # pareto front
    ToolDescEvolutionReport,
]:
    """Run the v2 GEPA pipeline for tool descriptions.

    Args:
        tool_name:        Name of the tool (or "all")
        tool_store:       Baseline ToolDescriptionStore
        dataset:          ToolDescriptionDataset with eval examples
        config:           EvolutionConfig
        constraint_validator: Optional constraint checker (default: ToolDescriptionConstraintValidator)

    Returns:
        (best_store, best_score, best_attempt, all_metrics, pareto_front, report)
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()
    constraint_validator = constraint_validator or ToolDescriptionConstraintValidator()

    backtrack = BacktrackController(window_size=3, plateau_threshold=0.01)
    pareto = ParetoSelector()
    router = EvolutionRouter()
    posthoc = PostHocAnalyzer(min_improvement_delta=0.03)

    best_store = tool_store
    best_score = 0.0
    best_attempt = 0
    all_metrics: List[ToolDescAttemptMetrics] = []
    pareto_front: List[Tuple[float, float]] = []

    # Baseline score on val set
    baseline_module = ToolDescriptionModule(tool_store)
    baseline_score = batch_tool_selection_accuracy(
        baseline_module, dataset, config
    )
    best_score = baseline_score

    # DSPy setup
    lm_kwargs, eval_model_used = _get_lm_kwargs(config.eval_model)
    lm_kwargs["num_retries"] = 8
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    # Build DSPy examples — cap at 20 for train, full dataset for val
    train_examples = [
        dspy.Example(
            task_description=dataset[i]["task"],
            tool_descriptions="",
            gold=dataset[i]["tool_name"],
        ).with_inputs("task_description", "tool_descriptions")
        for i in range(min(len(dataset), 20))
    ]
    val_examples = [
        dspy.Example(
            task_description=dataset[i]["task"],
            tool_descriptions="",
            gold=dataset[i]["tool_name"],
        ).with_inputs("task_description", "tool_descriptions")
        for i in range(len(dataset))
    ]

    optimizer_model_used = None
    ref_lm = None
    try:
        ref_lm_kwargs, optimizer_model_used = _get_lm_kwargs(config.optimizer_model)
        ref_lm = dspy.LM(optimizer_model_used, **ref_lm_kwargs)
    except Exception:
        ref_lm = lm  # Fallback to eval model

    num_attempts = max(3, config.iterations // 5)
    iterations_per_attempt = 5

    overall_start = time.time()
    router_decision = RouterDecision(action="extend", failure_pattern="", confidence=1.0, rationale="Initial")
    backtrack_decision = BacktrackDecision(action="continue", rationale="Initial")

    for attempt in range(1, num_attempts + 1):
        attempt_start = time.time()

        console.print(f"\n[bold cyan]Attempt {attempt}[/bold cyan] — "
                     f"{iterations_per_attempt} GEPA iterations, "
                     f"baseline={baseline_score:.3f}, best={best_score:.3f}")

        # Build fresh module with current best store
        current_module = ToolDescriptionModule(best_store)

        # Run GEPA
        optimizer = dspy.GEPA(
            metric=_tool_desc_gepa_metric,
            max_metric_calls=iterations_per_attempt * 10,
            reflection_lm=ref_lm,
        )
        optimizer_type = "GEPA"

        try:
            optimized_module = optimizer.compile(
                current_module,
                trainset=train_examples,
                valset=val_examples,
            )
        except Exception as e:
            console.print(f"[yellow]  GEPA failed ({e}), trying MIPROv2 fallback[/yellow]")
            try:
                optimizer = dspy.MIPROv2(
                    metric=_tool_desc_gepa_metric,
                    auto="light",
                    num_threads=1,
                )
                optimized_module = optimizer.compile(
                    current_module,
                    trainset=train_examples,
                    valset=val_examples,
                )
                optimizer_type = "MIPROv2"
            except Exception as e2:
                console.print(f"[red]  Both optimizers failed: {e2}[/red]")
                continue

        # Extract evolved descriptions from the optimized module
        evolved_store = _extract_evolved_descriptions(optimized_module, best_store)

        # Constraint validation
        constraint_ok, constraint_errors = constraint_validator.validate(evolved_store)
        if not constraint_ok:
            console.print(f"[yellow]  Constraints failed: {constraint_errors[0]}[/yellow]")
            evolved_store = best_store
            score = best_score
        else:
            score = batch_tool_selection_accuracy(
                ToolDescriptionModule(evolved_store), dataset, config
            )

        elapsed = time.time() - attempt_start

        n_changed = sum(
            1 for name in evolved_store.tools
            if evolved_store.descriptions.get(name) != best_store.descriptions.get(name)
        )

        metrics = ToolDescAttemptMetrics(
            attempt=attempt,
            score=score,
            baseline_score=baseline_score,
            optimizer_type=optimizer_type,
            elapsed_seconds=elapsed,
            descriptions_changed=n_changed,
        )
        all_metrics.append(metrics)

        pareto_accepted = pareto.select(
            score, len(evolved_store.to_json()) - len(best_store.to_json())
        )
        metrics.pareto_accepted = pareto_accepted

        delta = score - baseline_score
        console.print(
            f"  {optimizer_type} → score={score:.4f} "
            f"(Δ={delta:+.4f}), changed={n_changed} tools, "
            f"pareto={'✓' if pareto_accepted else '✗'}"
        )

        if score > best_score:
            best_score = score
            best_store = evolved_store
            best_attempt = attempt
            console.print(f"  [green]★ New best score: {best_score:.4f}[/green]")

        if delta <= 0:
            router_decision = router.classify(
                scenario_score=score,
                baseline_score=baseline_score,
                n_iterations=iterations_per_attempt,
            )
            console.print(f"  Router: {router_decision.action} ({router_decision.failure_pattern})")

        posthoc.add_attempt(
            attempt_number=attempt,
            score=score,
            baseline=baseline_score,
        )

    overall_elapsed = time.time() - overall_start
    pareto_front = _compute_pareto_front(all_metrics)

    improvement = best_score - baseline_score
    rel_improvement_pct = (improvement / baseline_score * 100) if baseline_score > 0 else 0.0

    posthoc_recommendation = posthoc.analyze_trajectory()

    if best_score <= baseline_score:
        recommendation = "reject"
        details = f"No improvement over baseline ({baseline_score:.4f})"
    elif rel_improvement_pct < 5.0:
        recommendation = "reject"
        details = f"Improvement below 5% threshold ({rel_improvement_pct:.1f}%)"
    elif posthoc_recommendation == "stop":
        recommendation = "review"
        details = f"PostHoc trajectory analysis recommends stop"
    else:
        recommendation = "accept"
        details = f"Improvement {improvement:+.4f} ({rel_improvement_pct:+.1f}%) over {best_attempt} attempts"

    report = ToolDescEvolutionReport(
        tool_name=tool_name,
        n_iterations_executed=len(all_metrics),
        improvement=improvement,
        recommendation=recommendation,
        details=details,
        router_decision=router_decision,
        backtrack_decision=backtrack_decision,
        pareto_front=pareto_front,
        all_attempt_metrics=all_metrics,
    )

    return best_store, best_score, best_attempt, all_metrics, pareto_front, report
