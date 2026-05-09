"""Conservative benchmark/promotion gate for evolution run reports.

The gate intentionally fails closed: required report fields must be present and
valid before an evolved artifact can be considered promotion-ready.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click


@dataclass
class BenchmarkThresholds:
    """Thresholds used to evaluate a run report."""

    min_holdout_improvement: float = 0.0
    max_artifact_growth: float = 0.20
    max_cost_increase: float | None = None


@dataclass
class GateResult:
    """Structured benchmark gate result."""

    passed: bool
    failures: list[str] = field(default_factory=list)
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_REQUIRED_FIELDS = (
    "baseline_score",
    "evolved_score",
    "improvement",
    "baseline_size",
    "evolved_size",
    "constraints_passed",
)


def _number(report: dict[str, Any], field_name: str) -> float:
    value = report[field_name]
    if not isinstance(value, int | float):
        raise TypeError(f"report field {field_name} must be numeric")
    return float(value)


def evaluate_report(
    report: dict[str, Any],
    thresholds: BenchmarkThresholds | None = None,
) -> GateResult:
    """Evaluate a run report against conservative promotion thresholds."""
    thresholds = thresholds or BenchmarkThresholds()
    failures: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    for field_name in _REQUIRED_FIELDS:
        if field_name not in report:
            failures.append(f"missing required report field: {field_name}")

    if failures:
        return GateResult(passed=False, failures=failures, checks=checks)

    try:
        baseline_score = _number(report, "baseline_score")
        evolved_score = _number(report, "evolved_score")
        improvement = _number(report, "improvement")
        baseline_size = _number(report, "baseline_size")
        evolved_size = _number(report, "evolved_size")
    except TypeError as exc:
        return GateResult(passed=False, failures=[str(exc)], checks=checks)

    constraints_passed = report["constraints_passed"] is True
    checks["constraints"] = {
        "passed": constraints_passed,
        "constraints_passed": report["constraints_passed"],
    }
    if not constraints_passed:
        failures.append("constraints_passed is not true")

    holdout_passed = improvement >= thresholds.min_holdout_improvement
    checks["holdout_improvement"] = {
        "passed": holdout_passed,
        "baseline_score": baseline_score,
        "evolved_score": evolved_score,
        "improvement": improvement,
        "minimum": thresholds.min_holdout_improvement,
    }
    if not holdout_passed:
        failures.append(
            f"holdout improvement {improvement:.4f} is below minimum "
            f"{thresholds.min_holdout_improvement:.4f}"
        )

    if baseline_size <= 0:
        artifact_growth = float("inf")
    else:
        artifact_growth = (evolved_size - baseline_size) / baseline_size
    growth_passed = artifact_growth <= thresholds.max_artifact_growth
    checks["artifact_growth"] = {
        "passed": growth_passed,
        "baseline_size": baseline_size,
        "evolved_size": evolved_size,
        "growth": artifact_growth,
        "maximum": thresholds.max_artifact_growth,
    }
    if not growth_passed:
        failures.append(
            f"artifact growth {artifact_growth:.4f} exceeds maximum "
            f"{thresholds.max_artifact_growth:.4f}"
        )

    if thresholds.max_cost_increase is not None:
        if "baseline_cost" not in report or "evolved_cost" not in report:
            failures.append(
                "missing required report fields for cost gate: baseline_cost, evolved_cost"
            )
            checks["cost_increase"] = {"passed": False}
        else:
            try:
                baseline_cost = _number(report, "baseline_cost")
                evolved_cost = _number(report, "evolved_cost")
            except TypeError as exc:
                return GateResult(passed=False, failures=[str(exc)], checks=checks)
            cost_growth = float("inf") if baseline_cost <= 0 else (evolved_cost - baseline_cost) / baseline_cost
            cost_passed = cost_growth <= thresholds.max_cost_increase
            checks["cost_increase"] = {
                "passed": cost_passed,
                "baseline_cost": baseline_cost,
                "evolved_cost": evolved_cost,
                "growth": cost_growth,
                "maximum": thresholds.max_cost_increase,
            }
            if not cost_passed:
                failures.append(
                    f"cost increase {cost_growth:.4f} exceeds maximum "
                    f"{thresholds.max_cost_increase:.4f}"
                )

    return GateResult(passed=not failures, failures=failures, checks=checks)


def _run_benchmark_command(command: str) -> tuple[bool, dict[str, Any]]:
    completed = subprocess.run(
        command,
        shell=True,
        text=True,
        capture_output=True,
        timeout=60 * 60,
    )
    return completed.returncode == 0, {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


@click.command()
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--min-holdout-improvement", default=0.0, show_default=True, type=float)
@click.option("--max-artifact-growth", default=0.20, show_default=True, type=float)
@click.option("--max-cost-increase", default=None, type=float)
@click.option("--benchmark-command", multiple=True, help="Optional command that must exit 0 for the gate to pass")
def main(
    report_path: Path,
    min_holdout_improvement: float,
    max_artifact_growth: float,
    max_cost_increase: float | None,
    benchmark_command: tuple[str, ...],
) -> None:
    """Evaluate a machine-readable evolution run report."""
    report = json.loads(report_path.read_text())
    thresholds = BenchmarkThresholds(
        min_holdout_improvement=min_holdout_improvement,
        max_artifact_growth=max_artifact_growth,
        max_cost_increase=max_cost_increase,
    )
    result = evaluate_report(report, thresholds)

    for command in benchmark_command:
        passed, details = _run_benchmark_command(command)
        result.checks.setdefault("benchmark_commands", []).append(details)
        if not passed:
            result.failures.append(f"benchmark command failed: {command}")
            result.passed = False

    click.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
