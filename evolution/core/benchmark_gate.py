"""Conservative benchmark/promotion gate for evolution run reports."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import click


@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_REQUIRED_FIELDS = [
    "target",
    "baseline.size_bytes",
    "optimized.size_bytes",
    "scores.holdout_delta",
    "constraints.all_passed",
]


def _get(data: dict, dotted: str):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted)
        current = current[part]
    return current


def evaluate_report(
    report_path: Path,
    *,
    min_holdout_delta: float = 0.0,
    max_artifact_growth: float = 0.5,
    max_cost_increase: float | None = None,
    require_constraints: bool = True,
    benchmark_commands: list[str] | None = None,
    benchmark_timeout_seconds: int = 300,
) -> GateResult:
    """Evaluate a run report. Missing required data fails closed."""
    report_path = Path(report_path)
    failures: list[str] = []
    warnings: list[str] = []
    observed: dict[str, Any] = {}
    thresholds = {
        "min_holdout_delta": min_holdout_delta,
        "max_artifact_growth": max_artifact_growth,
        "max_cost_increase": max_cost_increase,
        "require_constraints": require_constraints,
        "benchmark_commands": benchmark_commands or [],
        "benchmark_timeout_seconds": benchmark_timeout_seconds,
    }

    try:
        report = json.loads(report_path.read_text())
    except Exception as exc:
        return GateResult(False, [f"could not read report: {exc}"], [], thresholds, observed)

    for field_name in _REQUIRED_FIELDS:
        try:
            _get(report, field_name)
        except KeyError:
            failures.append(f"missing required field: {field_name}")
    if failures:
        return GateResult(False, failures, warnings, thresholds, observed)

    baseline_size = float(_get(report, "baseline.size_bytes"))
    optimized_size = float(_get(report, "optimized.size_bytes"))
    holdout_delta = float(_get(report, "scores.holdout_delta"))
    constraints_passed = bool(_get(report, "constraints.all_passed"))
    artifact_growth = (optimized_size - baseline_size) / max(1.0, baseline_size)

    observed.update({
        "holdout_delta": holdout_delta,
        "artifact_growth": artifact_growth,
        "constraints_passed": constraints_passed,
    })

    if require_constraints and not constraints_passed:
        failures.append("mandatory constraints did not pass")
    if holdout_delta < min_holdout_delta:
        failures.append(f"holdout delta {holdout_delta:+.6f} below minimum {min_holdout_delta:+.6f}")
    if artifact_growth > max_artifact_growth:
        failures.append(f"artifact growth {artifact_growth:+.2%} exceeds maximum {max_artifact_growth:+.2%}")

    if max_cost_increase is not None:
        cost = report.get("economics", {}).get("cost_estimate")
        if not cost or "baseline" not in cost or "optimized" not in cost:
            failures.append("missing required cost estimate for max cost increase gate")
        else:
            baseline_cost = float(cost["baseline"])
            optimized_cost = float(cost["optimized"])
            cost_increase = (optimized_cost - baseline_cost) / max(0.000001, baseline_cost)
            observed["cost_increase"] = cost_increase
            if cost_increase > max_cost_increase:
                failures.append(f"cost increase {cost_increase:+.2%} exceeds maximum {max_cost_increase:+.2%}")

    benchmark_results = []
    for command in benchmark_commands or []:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            failures.append(f"benchmark command could not be parsed safely: {exc}")
            continue
        if not argv:
            failures.append("benchmark command was empty")
            continue
        if argv[0] == "python":
            argv[0] = sys.executable
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=benchmark_timeout_seconds,
            )
        except FileNotFoundError as exc:
            benchmark_results.append({
                "command": command,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc)[-4000:],
            })
            failures.append(f"benchmark command failed to start: {command}: {exc}")
            continue
        except subprocess.TimeoutExpired as exc:
            benchmark_results.append({
                "command": command,
                "returncode": None,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                "timeout_seconds": benchmark_timeout_seconds,
            })
            failures.append(f"benchmark command timed out after {benchmark_timeout_seconds}s: {command}")
            continue
        result = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
        benchmark_results.append(result)
        if completed.returncode != 0:
            failures.append(f"benchmark command failed ({completed.returncode}): {command}")
    if benchmark_results:
        observed["benchmark_commands"] = benchmark_results

    return GateResult(not failures, failures, warnings, thresholds, observed)


@click.command()
@click.option("--report", "report_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--min-holdout-delta", default=0.0, type=float)
@click.option("--max-artifact-growth", default=0.5, type=float)
@click.option("--max-cost-increase", default=None, type=float)
@click.option("--benchmark-command", multiple=True, help="Optional benchmark command parsed with shlex; non-zero exit fails the gate")
@click.option("--benchmark-timeout-seconds", default=300, type=int, show_default=True, help="Per-command timeout for benchmark commands")
def main(report_path: Path, min_holdout_delta: float, max_artifact_growth: float, max_cost_increase: float | None, benchmark_command: tuple[str, ...], benchmark_timeout_seconds: int):
    """Evaluate a machine-readable evolution run report."""
    result = evaluate_report(
        report_path,
        min_holdout_delta=min_holdout_delta,
        max_artifact_growth=max_artifact_growth,
        max_cost_increase=max_cost_increase,
        benchmark_commands=list(benchmark_command),
        benchmark_timeout_seconds=benchmark_timeout_seconds,
    )
    click.echo(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
