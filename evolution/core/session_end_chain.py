"""Session-end full chain runner for exported Hermes traces.

This module composes the real session trace chain:

1. ``real_trace_ingestion.py`` reads an exported Hermes JSONL trace and detects
   known failure classes.
2. ``attention_router_bridge.py`` converts detected failures into Steve-style
   action items.
3. ``session_end_chain.py`` aggregates both verdicts plus action items into one
   ``chain_run.json``.

Safety invariants: local files only; no network calls, GitHub writes, or
production mutation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from evolution.core.attention_router_bridge import run_attention_router_bridge
from evolution.core.real_trace_ingestion import run_real_trace_ingestion

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _baseline_chain_output() -> dict[str, Any]:
    """Baseline: run nothing and return an empty chain report."""
    return {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "chain",
        "ingestion": {},
        "bridge": {},
        "action_items": [],
        "metrics": {
            "detected_failure_count": 0,
            "action_items_aggregated": 0,
            "steps_passed": 0,
            "steps_failed": 0,
        },
    }


def _candidate_payload_from_eval_examples(eval_examples_path: Path) -> dict[str, Any]:
    eval_examples = _load_json(eval_examples_path)
    examples = eval_examples.get("examples", [])
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        return examples[0]
    return {"detected_failure_classes": [], "failure_count": 0, "failures": {}}


def _load_action_items(queue_path: Path) -> list[dict[str, Any]]:
    if not queue_path.exists():
        return []
    queue = _load_json(queue_path)
    items = queue.get("items", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _summarize_ingestion(ingestion_dir: Path) -> dict[str, Any]:
    run_report_path = (ingestion_dir / "run_report.json").resolve()
    eval_examples_path = (ingestion_dir / "eval_examples.json").resolve()
    run_report = _load_json(run_report_path)
    payload = _candidate_payload_from_eval_examples(eval_examples_path)
    detected = payload.get("detected_failure_classes", [])
    if not isinstance(detected, list):
        detected = []
    failure_count = payload.get("failure_count", len(detected))
    return {
        "run_report": str(run_report_path),
        "eval_examples": str(eval_examples_path),
        "verdict": run_report.get("verdict"),
        "detected_failure_classes": [str(item) for item in detected],
        "failure_count": failure_count,
    }


def _summarize_bridge(bridge_dir: Path, action_items: list[dict[str, Any]]) -> dict[str, Any]:
    run_report_path = (bridge_dir / "run_report.json").resolve()
    action_queue_path = (bridge_dir / "action_queue.json").resolve()
    run_report = _load_json(run_report_path)
    return {
        "run_report": str(run_report_path),
        "action_queue": str(action_queue_path),
        "verdict": run_report.get("verdict"),
        "action_item_count": len(action_items),
    }


def evaluate_chain_run(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a session-end chain report with deterministic fail-closed checks."""
    failures: list[str] = []
    ingestion = report.get("ingestion")
    bridge = report.get("bridge")
    action_items = report.get("action_items")

    if not isinstance(ingestion, dict) or not ingestion:
        failures.append("missing ingestion summary")
        ingestion = {}
    if not isinstance(bridge, dict) or not bridge:
        failures.append("missing bridge summary")
        bridge = {}
    if not isinstance(action_items, list):
        failures.append("action_items must be a list")
        action_items = []

    if ingestion and ingestion.get("verdict") != "pass":
        failures.append("ingestion verdict must pass")
    if bridge and bridge.get("verdict") != "pass":
        failures.append("bridge verdict must pass")

    detected_classes = ingestion.get("detected_failure_classes", []) if ingestion else []
    if not isinstance(detected_classes, list):
        failures.append("detected_failure_classes must be a list")
        detected_classes = []
    failure_count = ingestion.get("failure_count") if ingestion else None
    if failure_count != len(detected_classes):
        failures.append("ingestion failure_count must match detected_failure_classes")

    if detected_classes and not action_items:
        failures.append("detected failures must produce at least one action item")
    if bridge and bridge.get("action_item_count") != len(action_items):
        failures.append("bridge action_item_count must match aggregated action_items")

    for section_name, section in [("ingestion", ingestion), ("bridge", bridge)]:
        run_report = section.get("run_report") if section else None
        if not run_report:
            failures.append(f"missing {section_name} run_report path")
            continue
        path = Path(str(run_report))
        if not path.is_absolute():
            failures.append(f"{section_name} run_report path is not absolute")
        elif not path.exists():
            failures.append(f"{section_name} run_report path does not exist")

    return {"passed": not failures, "failures": failures}


def _build_chain_report(
    *,
    out_dir: Path,
    trace_path: Path,
    ingestion: dict[str, Any],
    bridge: dict[str, Any],
    action_items: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline = _baseline_chain_output()
    baseline_eval = evaluate_chain_run(baseline)
    candidate_seed = {
        "ingestion": ingestion,
        "bridge": bridge,
        "action_items": action_items,
    }
    candidate_eval = evaluate_chain_run(candidate_seed)
    steps = [ingestion.get("verdict"), bridge.get("verdict")]
    steps_passed = sum(1 for verdict in steps if verdict == "pass")
    steps_failed = len(steps) - steps_passed

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "chain",
        "task_type": "session_end_chain",
        "source_trace": str(trace_path.resolve()),
        "external_writes_allowed": False,
        "network_allowed": False,
        "ingestion": ingestion,
        "bridge": bridge,
        "action_items": action_items,
        "metrics": {
            "detected_failure_count": ingestion.get("failure_count", 0),
            "action_items_aggregated": len(action_items),
            "steps_passed": steps_passed,
            "steps_failed": steps_failed,
        },
        "baseline": {
            "artifact_id": "session_end_chain_empty_v0",
            "artifact_type": "chain_report",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
        },
        "candidate": {
            "artifact_id": "session_end_chain_v1",
            "artifact_type": "chain_report",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
        },
        "verdict": "pass" if (not baseline_eval["passed"] and candidate_eval["passed"]) else "fail",
        "safety": {
            "mode": "chain",
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
        "artifacts": {
            "chain_run": str((out_dir / "chain_run.json").resolve()),
        },
    }
    return report


def run_session_end_chain(trace_path: Path, out_dir: Path) -> dict[str, Any]:
    """Run real-trace ingestion then attention-router bridge and aggregate results."""
    trace_path = Path(trace_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ingestion_dir = out_dir / "real_trace_ingestion"
    bridge_dir = out_dir / "attention_router_bridge"

    run_real_trace_ingestion(trace_path, ingestion_dir)
    run_attention_router_bridge(ingestion_dir, bridge_dir)

    action_items = _load_action_items(bridge_dir / "action_queue.json")
    ingestion = _summarize_ingestion(ingestion_dir)
    bridge = _summarize_bridge(bridge_dir, action_items)

    report = _build_chain_report(
        out_dir=out_dir,
        trace_path=trace_path,
        ingestion=ingestion,
        bridge=bridge,
        action_items=action_items,
    )
    _write_json(out_dir / "chain_run.json", report)
    return report


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--trace",
    "trace_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to an exported Hermes session JSONL trace.",
)
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--mode", required=True, type=click.Choice(["chain"]))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(
    trace_path: Path,
    out_dir: Path,
    mode: str,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Run the local session-end real-trace -> action-item chain."""
    if mode != "chain":
        raise click.ClickException("only chain mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_session_end_chain(trace_path, out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("session-end chain gate failed")


if __name__ == "__main__":
    main()
