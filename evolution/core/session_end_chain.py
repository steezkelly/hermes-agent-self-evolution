"""Session-end full chain runner for exported Hermes traces.

This module composes the real session trace chain:

1. ``real_trace_ingestion.py`` reads an exported Hermes JSONL trace and detects
   known failure classes.
2. ``attention_router_bridge.py`` converts detected failures into Steve-style
   action items.
3. ``trace_optimizer.py`` converts detected failures into improvement templates.
4. ``gepa_trace_bridge.py`` converts templates into GEPA-ready datasets.
5. Optional ``observatory/health.py`` reads a local judge audit DB and appends
   a health report (``chain_observe`` mode).

Safety invariants: local files only; no network calls, GitHub writes, external
writes, or production mutation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from evolution.core.attention_router_bridge import run_attention_router_bridge
from evolution.core.real_trace_ingestion import run_real_trace_ingestion

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_SUPPORTED_MODES = ["chain", "chain_optimize", "chain_gepa", "chain_observe"]


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _summarize_optimizer(optimizer_dir: Path) -> dict[str, Any]:
    run_report_path = (optimizer_dir / "run_report.json").resolve()
    if not run_report_path.is_file():
        return {"verdict": "not_run", "improvement_count": 0}
    run_report = _load_json(run_report_path)
    return {
        "run_report": str(run_report_path),
        "verdict": run_report.get("verdict", "not_run"),
        "improvement_count": len(run_report.get("improvements", [])),
    }


def _summarize_gepa_bridge(gepa_dir: Path) -> dict[str, Any]:
    run_report_path = (gepa_dir / "run_report.json").resolve()
    if not run_report_path.is_file():
        return {"verdict": "not_run", "datasets_built": 0}
    run_report = _load_json(run_report_path)
    manifest_path = (gepa_dir / "gepa_manifest.json").resolve()
    return {
        "run_report": str(run_report_path),
        "manifest": str(manifest_path) if manifest_path.is_file() else "",
        "verdict": run_report.get("verdict", "not_run"),
        "datasets_built": run_report.get("datasets_built", 0),
        "total_examples": run_report.get("total_examples", 0),
    }


def _run_optimizer_stage(ingestion_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Run the trace optimizer as an optional chain stage."""
    from evolution.core.trace_optimizer import run_optimizer

    return run_optimizer(
        eval_examples_path=ingestion_dir / "eval_examples.json",
        output_dir=output_dir,
        mode="optimizer",
    )


def _run_observatory_health_stage(db_path: Path, output_dir: Path) -> dict[str, Any]:
    """Run observatory/health.py against a local judge audit DB."""
    from evolution.core.observatory.health import JudgeHealthMonitor
    from evolution.core.observatory.logger import JudgeAuditLogger

    db_path = Path(db_path).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = JudgeAuditLogger(db_path=db_path)
    health = JudgeHealthMonitor(logger).health_report(generations_since=0).as_dict()
    alerts = health.get("alerts", [])
    if not isinstance(alerts, list):
        alerts = []
    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "observatory_health",
        "module": "evolution.core.observatory.health",
        "verdict": "pass" if not alerts else "fail",
        "db_path": str(db_path),
        "health": health,
        "alert_count": len(alerts),
        "alerts": alerts,
        "safety": {
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
    }
    _write_json(output_dir / "health_report.json", report)
    return report


def _summarize_observatory_health(observatory_dir: Path, db_path: Path) -> dict[str, Any]:
    health_report_path = (observatory_dir / "health_report.json").resolve()
    if not health_report_path.is_file():
        return {"verdict": "not_run", "alert_count": 0}
    run_report = _load_json(health_report_path)
    health = run_report.get("health", {})
    if not isinstance(health, dict):
        health = {}
    alerts = run_report.get("alerts", health.get("alerts", []))
    if not isinstance(alerts, list):
        alerts = []
    return {
        "health_report": str(health_report_path),
        "verdict": run_report.get("verdict", "not_run"),
        "module": run_report.get("module", "evolution.core.observatory.health"),
        "db_path": str(Path(db_path).resolve()),
        "health": health,
        "generations": health.get("generations", []),
        "total_calls": health.get("total_calls", 0),
        "error_calls": health.get("error_calls", 0),
        "error_rate": health.get("error_rate", 0.0),
        "mean_score": health.get("mean_score"),
        "std_score": health.get("std_score"),
        "dead_zone_fraction": health.get("dead_zone_fraction", 0.0),
        "total_cost": health.get("total_cost", 0.0),
        "alert_count": len(alerts),
        "alerts": alerts,
    }


def evaluate_chain_run(report: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a session-end chain report with deterministic fail-closed checks."""
    failures: list[str] = []
    ingestion = report.get("ingestion")
    bridge = report.get("bridge")
    action_items = report.get("action_items")
    observatory_health = report.get("observatory_health")

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

    if observatory_health is not None:
        if not isinstance(observatory_health, dict) or not observatory_health:
            failures.append("missing observatory health summary")
            observatory_health = {}
        elif observatory_health.get("verdict") != "pass":
            failures.append("observatory health verdict must pass")
        if observatory_health:
            alerts = observatory_health.get("alerts", [])
            if not isinstance(alerts, list):
                failures.append("observatory health alerts must be a list")
                alerts = []
            if observatory_health.get("alert_count") != len(alerts):
                failures.append("observatory health alert_count must match alerts")
            health_report = observatory_health.get("health_report")
            if not health_report:
                failures.append("missing observatory health report path")
            else:
                path = Path(str(health_report))
                if not path.is_absolute():
                    failures.append("observatory health report path is not absolute")
                elif not path.exists():
                    failures.append("observatory health report path does not exist")

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
    optimizer: dict[str, Any] | None = None,
    gepa: dict[str, Any] | None = None,
    observatory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = _baseline_chain_output()
    baseline_eval = evaluate_chain_run(baseline)
    active_optimizer = optimizer if optimizer and optimizer.get("verdict") != "not_run" else None
    active_gepa = gepa if gepa and gepa.get("verdict") != "not_run" else None
    active_observatory = observatory if observatory and observatory.get("verdict") != "not_run" else None
    candidate_seed = {
        "ingestion": ingestion,
        "bridge": bridge,
        "action_items": action_items,
        "observatory_health": active_observatory,
    }
    candidate_eval = evaluate_chain_run(candidate_seed)

    steps = [ingestion.get("verdict"), bridge.get("verdict")]
    if active_optimizer:
        steps.append(active_optimizer.get("verdict"))
    if active_gepa:
        steps.append(active_gepa.get("verdict"))
    if active_observatory:
        steps.append(active_observatory.get("verdict"))
    steps_passed = sum(1 for verdict in steps if verdict == "pass")
    steps_failed = len(steps) - steps_passed

    mode = "chain"
    if active_observatory:
        mode = "chain_observe"
    elif active_gepa:
        mode = "chain_gepa"
    elif active_optimizer:
        mode = "chain_optimize"

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": mode,
        "task_type": "session_end_chain",
        "source_trace": str(trace_path.resolve()),
        "external_writes_allowed": False,
        "network_allowed": False,
        "ingestion": ingestion,
        "bridge": bridge,
        "action_items": action_items,
        "optimizer": active_optimizer,
        "gepa_bridge": active_gepa,
        "observatory_health": active_observatory,
        "metrics": {
            "detected_failure_count": ingestion.get("failure_count", 0),
            "action_items_aggregated": len(action_items),
            "improvements_generated": active_optimizer.get("improvement_count", 0) if active_optimizer else 0,
            "gepa_datasets_built": active_gepa.get("datasets_built", 0) if active_gepa else 0,
            "observatory_alert_count": active_observatory.get("alert_count", 0) if active_observatory else 0,
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
            "mode": mode,
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
        "artifacts": {
            "chain_run": str((out_dir / "chain_run.json").resolve()),
            "observatory_health": active_observatory.get("health_report", "") if active_observatory else "",
        },
    }
    return report


def run_session_end_chain(
    trace_path: Path,
    out_dir: Path,
    *,
    optimize: bool = False,
    gepa_bridge: bool = False,
    observe: bool = False,
    observatory_db_path: Path | None = None,
    optimizer_model: str = "minimax/minimax-m2.7",
    eval_model: str = "minimax/minimax-m2.7",
) -> dict[str, Any]:
    """Run real-trace ingestion, bridge, and optional downstream stages.

    Args:
        trace_path: Path to exported Hermes JSONL session trace.
        out_dir: Output directory for all artifacts.
        optimize: If True, also run trace_optimizer stage after bridge.
        gepa_bridge: If True, run optimizer + GEPA bridge stage.
        observe: If True, run observatory health report against judge audit DB.
        observatory_db_path: Path to local judge_audit_log.db for observe mode.
        optimizer_model: Model name embedded in GEPA manifest.
        eval_model: Model name embedded in GEPA manifest.
    """
    trace_path = Path(trace_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if observe and observatory_db_path is None:
        raise ValueError("observatory_db_path is required when observe=True")
    if observe:
        gepa_bridge = True
        optimize = True

    ingestion_dir = out_dir / "real_trace_ingestion"
    bridge_dir = out_dir / "attention_router_bridge"

    run_real_trace_ingestion(trace_path, ingestion_dir)
    run_attention_router_bridge(ingestion_dir, bridge_dir)

    action_items = _load_action_items(bridge_dir / "action_queue.json")
    ingestion = _summarize_ingestion(ingestion_dir)
    bridge = _summarize_bridge(bridge_dir, action_items)

    optimizer = None
    gepa = None
    if optimize or gepa_bridge:
        optimizer_dir = out_dir / "trace_optimizer"
        _run_optimizer_stage(ingestion_dir, optimizer_dir)
        optimizer = _summarize_optimizer(optimizer_dir)

    if gepa_bridge:
        gepa_dir = out_dir / "gepa_bridge"
        from evolution.core.gepa_trace_bridge import run_gepa_bridge as run_gepa

        run_gepa(
            candidate_artifacts_path=optimizer_dir / "candidate_artifacts.json",
            output_dir=gepa_dir,
            optimizer_model=optimizer_model,
            eval_model=eval_model,
        )
        gepa = _summarize_gepa_bridge(gepa_dir)

    observatory = None
    if observe:
        assert observatory_db_path is not None
        observatory_dir = out_dir / "observatory_health"
        _run_observatory_health_stage(observatory_db_path, observatory_dir)
        observatory = _summarize_observatory_health(observatory_dir, observatory_db_path)

    report = _build_chain_report(
        out_dir=out_dir,
        trace_path=trace_path,
        ingestion=ingestion,
        bridge=bridge,
        action_items=action_items,
        optimizer=optimizer,
        gepa=gepa,
        observatory=observatory,
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
@click.option("--mode", required=True, type=click.Choice(_SUPPORTED_MODES))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
@click.option("--optimize", is_flag=True, default=False, help="Run trace_optimizer stage after bridge.")
@click.option("--gepa", is_flag=True, default=False, help="Run optimizer + GEPA bridge stage after bridge.")
@click.option("--observe", "observe", is_flag=True, default=False, help="Run observatory health stage after GEPA bridge.")
@click.option("--observatory", "observe", is_flag=True, help="Alias for --observe.")
@click.option(
    "--observatory-db",
    "observatory_db_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to local judge_audit_log.db for chain_observe mode.",
)
@click.option("--optimizer-model", type=str, default="minimax/minimax-m2.7")
@click.option("--eval-model", type=str, default="minimax/minimax-m2.7")
def main(
    trace_path: Path,
    out_dir: Path,
    mode: str,
    no_network: bool,
    no_external_writes: bool,
    optimize: bool,
    gepa: bool,
    observe: bool,
    observatory_db_path: Path | None,
    optimizer_model: str,
    eval_model: str,
) -> None:
    """Run the local session-end real-trace -> action-item chain."""
    if mode not in _SUPPORTED_MODES:
        raise click.ClickException(f"unsupported mode: {mode!r}")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    do_observe = observe or (mode == "chain_observe")
    if do_observe and observatory_db_path is None:
        raise click.ClickException("--observatory-db is required for chain_observe")
    do_gepa = gepa or (mode == "chain_gepa") or do_observe
    do_optimize = optimize or (mode == "chain_optimize") or do_gepa

    result = run_session_end_chain(
        trace_path,
        out_dir,
        optimize=do_optimize,
        gepa_bridge=do_gepa,
        observe=do_observe,
        observatory_db_path=observatory_db_path,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
    )
    if result["verdict"] != "pass":
        raise click.ClickException("session-end chain gate failed")


if __name__ == "__main__":
    main()
