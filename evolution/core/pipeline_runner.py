"""Foundry pipeline runner for fixture and real-trace evidence loops.

The runner composes the local Foundry modules that produce ``run_report.json``
artifacts, then aggregates their verdicts into one ``pipeline_run.json``. It is
intentionally local-only: no network calls, GitHub writes, or production
mutation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import click

from evolution.core.action_routing_demo import run_action_routing_fixture
from evolution.core.attention_router_bridge import run_attention_router_bridge
from evolution.core.real_trace_ingestion import run_real_trace_ingestion
from evolution.core.session_import_demo import run_session_import_fixture
from evolution.core.skill_drift_demo import run_skill_drift_fixture
from evolution.core.tool_underuse_demo import run_tool_underuse_fixture

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"

FixtureRunner = Callable[[Path], dict[str, Any]]

_FIXTURE_RUNNERS: list[tuple[str, FixtureRunner]] = [
    ("action_routing_demo", run_action_routing_fixture),
    ("session_import_demo", run_session_import_fixture),
    ("tool_underuse_demo", run_tool_underuse_fixture),
    ("skill_drift_demo", run_skill_drift_fixture),
]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _baseline_pipeline_output() -> dict[str, Any]:
    """Baseline: run nothing and return an empty aggregation report."""
    return {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "baseline",
        "reports": [],
        "action_items": [],
        "metrics": {
            "reports_collected": 0,
            "passed_reports": 0,
            "failed_reports": 0,
            "action_items_aggregated": 0,
        },
    }


def _report_summary(name: str, report_path: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    return {
        "name": name,
        "run_report": str(report_path.resolve()),
        "mode": report.get("mode"),
        "task_type": report.get("task_type"),
        "verdict": report.get("verdict"),
        "baseline_passed": report.get("baseline", {}).get("passed"),
        "candidate_passed": report.get("candidate", {}).get("passed"),
    }


def _load_action_items(queue_path: Path) -> list[dict[str, Any]]:
    if not queue_path.exists():
        return []
    queue = _load_json(queue_path)
    items = queue.get("items", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def evaluate_pipeline_run(report: dict[str, Any], *, expected_run_count: int) -> dict[str, Any]:
    """Evaluate a pipeline aggregation with deterministic fail-closed checks."""
    failures: list[str] = []
    reports = report.get("reports", [])
    if not isinstance(reports, list):
        failures.append("reports must be a list")
        reports = []

    if not reports:
        failures.append("no reports were collected")
    if len(reports) != expected_run_count:
        failures.append(f"expected {expected_run_count} reports, collected {len(reports)}")

    for child in reports:
        if not isinstance(child, dict):
            failures.append("child report summary must be an object")
            continue
        name = child.get("name", "unknown")
        if child.get("verdict") != "pass":
            failures.append(f"failed child report: {name}")
        run_report = child.get("run_report")
        if not run_report:
            failures.append(f"missing run_report path: {name}")
        else:
            path = Path(str(run_report))
            if not path.is_absolute():
                failures.append(f"run_report path is not absolute: {name}")
            elif not path.exists():
                failures.append(f"run_report path does not exist: {name}")

    action_items = report.get("action_items", [])
    if not isinstance(action_items, list):
        failures.append("action_items must be a list")

    return {"passed": not failures, "failures": failures}


def _build_pipeline_report(
    *,
    out_dir: Path,
    mode: str,
    reports: list[dict[str, Any]],
    action_items: list[dict[str, Any]],
    expected_run_count: int,
    preflight_failures: list[str] | None = None,
) -> dict[str, Any]:
    passed_reports = sum(1 for report in reports if report.get("verdict") == "pass")
    failed_reports = len(reports) - passed_reports
    candidate_seed = {
        "reports": reports,
        "action_items": action_items,
    }
    candidate_eval = evaluate_pipeline_run(candidate_seed, expected_run_count=expected_run_count)
    if preflight_failures:
        candidate_eval = {
            "passed": False,
            "failures": [*preflight_failures, *candidate_eval["failures"]],
        }

    baseline_output = _baseline_pipeline_output()
    baseline_eval = evaluate_pipeline_run(baseline_output, expected_run_count=expected_run_count)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": mode,
        "task_type": "pipeline_runner",
        "external_writes_allowed": False,
        "network_allowed": False,
        "reports": reports,
        "action_items": action_items,
        "metrics": {
            "reports_collected": len(reports),
            "passed_reports": passed_reports,
            "failed_reports": failed_reports,
            "action_items_aggregated": len(action_items),
        },
        "baseline": {
            "artifact_id": "pipeline_runner_empty_v0",
            "artifact_type": "pipeline_report",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
        },
        "candidate": {
            "artifact_id": "pipeline_runner_v1",
            "artifact_type": "pipeline_report",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
        },
        "verdict": "pass" if (not baseline_eval["passed"] and candidate_eval["passed"]) else "fail",
        "safety": {
            "mode": mode,
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
        "artifacts": {
            "pipeline_run": str((out_dir / "pipeline_run.json").resolve()),
        },
    }
    return report


def run_pipeline(out_dir: Path, *, mode: str, trace_path: Path | None = None) -> dict[str, Any]:
    """Run the Foundry pipeline and write ``pipeline_run.json``."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    preflight_failures: list[str] = []

    if mode == "fixture":
        for name, runner in _FIXTURE_RUNNERS:
            child_dir = out_dir / name
            runner(child_dir)
            reports.append(_report_summary(name, child_dir / "run_report.json"))
        expected_run_count = len(_FIXTURE_RUNNERS)
    elif mode == "real_trace":
        expected_run_count = 2
        if trace_path is None:
            preflight_failures.append("--trace is required in real_trace mode")
        else:
            trace_path = Path(trace_path).resolve()
            ingestion_dir = out_dir / "real_trace_ingestion"
            bridge_dir = out_dir / "attention_router_bridge"
            run_real_trace_ingestion(trace_path, ingestion_dir)
            reports.append(_report_summary("real_trace_ingestion", ingestion_dir / "run_report.json"))
            run_attention_router_bridge(ingestion_dir, bridge_dir)
            reports.append(_report_summary("attention_router_bridge", bridge_dir / "run_report.json"))
            action_items.extend(_load_action_items(bridge_dir / "action_queue.json"))
    else:
        raise ValueError(f"unsupported mode: {mode}")

    report = _build_pipeline_report(
        out_dir=out_dir,
        mode=mode,
        reports=reports,
        action_items=action_items,
        expected_run_count=expected_run_count,
        preflight_failures=preflight_failures,
    )
    _write_json(out_dir / "pipeline_run.json", report)
    return report


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--mode", required=True, type=click.Choice(["fixture", "real_trace"]))
@click.option(
    "--trace",
    "trace_path",
    required=False,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Hermes session JSONL export for real_trace mode.",
)
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(
    out_dir: Path,
    mode: str,
    trace_path: Path | None,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Run the local Foundry fixture or real-trace pipeline."""
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")
    if mode == "real_trace" and trace_path is None:
        raise click.ClickException("--trace is required in real_trace mode")

    result = run_pipeline(out_dir, mode=mode, trace_path=trace_path)
    if result["verdict"] != "pass":
        raise click.ClickException("pipeline runner gate failed")


if __name__ == "__main__":
    main()
