"""Bridge real-trace failure detection into attention-router action items.

This module consumes the local output from ``real_trace_ingestion.py`` and
turns detected failure classes into Steve-style action queue entries. The
baseline deliberately preserves the old behavior (raw JSON report dump), while
the candidate emits one concise action item per detected failure class and is
scored with the same action-item evaluator as ``action_routing_demo.py``.

Safety invariants: no network calls, no GitHub writes, no production mutation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

from evolution.core.action_routing_demo import evaluate_action_item

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_FIXED_EXPIRES_AT = "1970-01-08T00:00:00Z"
_REPO_PATH = "/home/steve/repos/steezkelly-hermes-agent-self-evolution"

_FAILURE_CLASS_DETAILS: dict[str, dict[str, str]] = {
    "long_briefing_instead_of_concise_action_queue": {
        "bucket": "autonomous",
        "owner": "attention-router",
        "title": "Convert long briefing trace into one action item",
        "why": "Real-trace ingestion detected briefing sprawl; route it into a concise queue item instead of another synthesis.",
        "prompt": "Review the long_briefing evidence and tighten the runtime/action-router behavior so future outputs become concise action items, not option briefings.",
    },
    "raw_session_trace_without_structured_eval_example": {
        "bucket": "autonomous",
        "owner": "foundry",
        "title": "Promote raw session trace into structured eval evidence",
        "why": "The trace still behaved like raw session data; Foundry needs structured eval evidence before it can drive repair work.",
        "prompt": "Use the raw_session_dump evidence to add or refine structured eval extraction, preserving local-only Foundry artifacts.",
    },
    "agent_describes_instead_of_calls_tools": {
        "bucket": "autonomous",
        "owner": "hermes-runtime",
        "title": "Patch tool-underuse behavior from trace evidence",
        "why": "The trace shows the agent describing checks instead of using available tools; convert that into a local runtime repair prompt.",
        "prompt": "Use the tool_underuse evidence to reproduce the tool-call miss, then add a focused regression or skill/runtime fix that forces action over description.",
    },
    "stale_skill_body_without_drift_detection": {
        "bucket": "autonomous",
        "owner": "skill-maintainer",
        "title": "Refresh stale skill guidance from drift evidence",
        "why": "Real-trace ingestion found stale or deprecated skill guidance; route a bounded skill refresh instead of leaving drift as a report note.",
        "prompt": "Use the skill_drift evidence to identify the stale skill text, patch the skill, and verify the updated workflow against the trace.",
    },
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _resolve_input_paths(input_path: Path) -> tuple[Path, Path | None]:
    """Resolve an ingestion output directory or run_report.json path."""
    input_path = Path(input_path).resolve()
    if input_path.is_dir():
        report_path = input_path / "run_report.json"
        eval_examples_path = input_path / "eval_examples.json"
    else:
        report_path = input_path
        eval_examples_path = input_path.parent / "eval_examples.json"

    if not report_path.exists():
        raise FileNotFoundError(f"run_report.json not found: {report_path}")
    if eval_examples_path and not eval_examples_path.exists():
        eval_examples_path = None
    return report_path, eval_examples_path


def _baseline_attention_router_output(report: dict[str, Any]) -> dict[str, Any]:
    """Baseline: dump the raw report as-is, which fails action-item eval."""
    return dict(report)


def _candidate_payload_from_report_or_examples(
    report: dict[str, Any], eval_examples: dict[str, Any] | None
) -> dict[str, Any]:
    """Extract the structured candidate output from supported ingestion shapes."""
    candidate = report.get("candidate")
    if isinstance(candidate, dict):
        output = candidate.get("output") or candidate.get("candidate_output")
        if isinstance(output, dict) and "detected_failure_classes" in output:
            return output

    for key in ("candidate_output", "output"):
        output = report.get(key)
        if isinstance(output, dict) and "detected_failure_classes" in output:
            return output

    if "detected_failure_classes" in report:
        return report

    if eval_examples:
        examples = eval_examples.get("examples", [])
        if examples and isinstance(examples[0], dict):
            return examples[0]

    return {"detected_failure_classes": [], "failures": {}}


def _evidence_paths(report_path: Path, eval_examples_path: Path | None, report: dict[str, Any]) -> list[str]:
    paths = [report_path]
    if eval_examples_path is not None:
        paths.append(eval_examples_path)
    source_trace = report.get("source_trace")
    if source_trace:
        source_path = Path(str(source_trace)).expanduser().resolve()
        if source_path.exists():
            paths.append(source_path)
    return [str(path.resolve()) for path in paths if path.exists()]


def _failure_description(failure_class: str, failures: dict[str, Any]) -> str:
    failure = failures.get(failure_class)
    if isinstance(failure, dict) and failure.get("description"):
        return str(failure["description"])
    return failure_class.replace("_", " ")


def _candidate_attention_router_output(
    report: dict[str, Any],
    report_path: Path,
    eval_examples_path: Path | None,
) -> list[dict[str, Any]]:
    """Candidate: one concise action item per detected failure class."""
    payload = _candidate_payload_from_report_or_examples(
        report,
        _load_json(eval_examples_path) if eval_examples_path else None,
    )
    detected_classes = payload.get("detected_failure_classes", [])
    if not isinstance(detected_classes, list):
        detected_classes = []
    failures = payload.get("failures", {})
    if not isinstance(failures, dict):
        failures = {}

    evidence_paths = _evidence_paths(report_path, eval_examples_path, report)
    items: list[dict[str, Any]] = []
    for failure_class in detected_classes:
        detail = _FAILURE_CLASS_DETAILS.get(
            str(failure_class),
            {
                "bucket": "autonomous",
                "owner": "foundry",
                "title": f"Route detected failure: {str(failure_class).replace('_', ' ')}",
                "why": "Real-trace ingestion detected a failure class that needs a bounded local repair prompt.",
                "prompt": "Review the detected failure evidence and create the smallest local repair or eval follow-up.",
            },
        )
        description = _failure_description(str(failure_class), failures)
        why = f"{detail['why']} Evidence: {description}"
        if len(why) > 380:
            why = why[:377].rstrip() + "..."

        next_prompt = (
            f"Work in `{_REPO_PATH}`. {detail['prompt']} "
            f"Evidence paths: {', '.join(evidence_paths)}. "
            "Safety: local files only; no network, GitHub writes, or production mutation."
        )
        items.append(
            {
                "bucket": detail["bucket"],
                "owner": detail["owner"],
                "title": detail["title"],
                "why": why,
                "evidence_paths": evidence_paths,
                "next_prompt": next_prompt,
                "expires_at": _FIXED_EXPIRES_AT,
                "failure_class": str(failure_class),
                "dedupe_key": f"foundry:attention-router-bridge:{failure_class}",
            }
        )
    return items


def evaluate_action_items(items: list[dict[str, Any]], expected_count: int) -> dict[str, Any]:
    """Evaluate bridge output by applying the action-item contract to each item."""
    failures: list[str] = []
    if expected_count < 1:
        failures.append("candidate must emit at least one action item from detected failures")
    if len(items) != expected_count:
        failures.append(
            f"candidate emitted {len(items)} action items for {expected_count} detected failures"
        )

    for index, item in enumerate(items):
        item_eval = evaluate_action_item(item)
        for failure in item_eval["failures"]:
            failures.append(f"item {index}: {failure}")

    return {"passed": not failures, "failures": failures}


def _build_promotion_dossier(
    report_path: Path,
    queue_path: Path,
    manifest_path: Path,
    source_report_path: Path,
    action_item_count: int,
    detected_classes: list[str],
) -> str:
    class_list = "\n".join(f"- {failure_class}" for failure_class in detected_classes) or "- none"
    plural = "item" if action_item_count == 1 else "items"
    return f"""# Attention Router Bridge Promotion Dossier

## Summary

Baseline dumped the raw report as-is and failed the action-item contract.
Candidate emitted {action_item_count} attention-router action {plural} from real-trace detected failure classes.

## Detected failures

{class_list}

## Evidence

- Source real-trace report: {source_report_path}
- Bridge run report: {report_path}
- Action queue: {queue_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm each detected failure class has exactly one action item.
2. Confirm each item has bucket, owner, title, why, evidence_paths, next_prompt, and expires_at.
3. Confirm no network calls, GitHub writes, or production mutation were allowed.

## Promotion recommendation

Candidate passed the local attention-router gate if the run report verdict is `pass`.
Use the action queue as Steve-facing follow-up, not the raw JSON report.

## Rollback

Keep consuming the original real-trace ingestion report directly if downstream review finds action item routing too lossy.
"""


def run_attention_router_bridge(input_path: Path, out_dir: Path) -> dict[str, Any]:
    """Convert real-trace detected failures into action-router artifacts."""
    report_path, eval_examples_path = _resolve_input_paths(Path(input_path))
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    bridge_report_path = out_dir / "run_report.json"
    queue_path = out_dir / "action_queue.json"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    source_report = _load_json(report_path)
    eval_examples = _load_json(eval_examples_path) if eval_examples_path else None
    candidate_payload = _candidate_payload_from_report_or_examples(source_report, eval_examples)
    detected_classes = candidate_payload.get("detected_failure_classes", [])
    if not isinstance(detected_classes, list):
        detected_classes = []

    baseline_output = _baseline_attention_router_output(source_report)
    baseline_eval = evaluate_action_item(baseline_output)
    candidate_items = _candidate_attention_router_output(source_report, report_path, eval_examples_path)
    candidate_eval = evaluate_action_items(candidate_items, len(detected_classes))

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "attention_router_bridge",
        "task_type": "attention_router_bridge",
        "source_report": str(report_path),
        "fixture": {
            "failure_class": "real_trace_detection_needs_attention_router_action_items",
            "expected_behavior": "emit one Steve-style action item per detected failure class",
        },
        "baseline": {
            "artifact_id": "raw_real_trace_report_dump_v1",
            "artifact_type": "report",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
        },
        "candidate": {
            "artifact_id": "attention_router_bridge_v1",
            "artifact_type": "action_queue",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(candidate_items, sort_keys=True)),
        },
        "metrics": {
            "baseline_pass_rate": 1.0 if baseline_eval["passed"] else 0.0,
            "candidate_pass_rate": 1.0 if candidate_eval["passed"] else 0.0,
            "holdout_delta": (1.0 if candidate_eval["passed"] else 0.0)
            - (1.0 if baseline_eval["passed"] else 0.0),
            "failure_classes_detected": len(detected_classes),
            "action_items_emitted": len(candidate_items),
        },
        "verdict": (
            "pass"
            if (not baseline_eval["passed"] and candidate_eval["passed"])
            else "fail"
        ),
        "safety": {
            "mode": "attention_router_bridge",
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
    }
    _write_json(bridge_report_path, report)

    action_queue = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "attention_router_bridge",
        "source_report": str(report_path),
        "external_writes_allowed": False,
        "items": candidate_items,
    }
    _write_json(queue_path, action_queue)

    dossier_path.write_text(
        _build_promotion_dossier(
            bridge_report_path,
            queue_path,
            manifest_path,
            report_path,
            len(candidate_items),
            [str(cls) for cls in detected_classes],
        )
    )

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "attention_router_bridge",
        "source_report": str(report_path),
        "artifact_versions": {
            "baseline": "raw_real_trace_report_dump_v1",
            "candidate": "attention_router_bridge_v1",
        },
        "artifacts": {
            "run_report": str(bridge_report_path),
            "action_queue": str(queue_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "consume the original real-trace report directly",
    }
    _write_json(manifest_path, manifest)

    return {
        "schema_version": report["schema_version"],
        "mode": report["mode"],
        "external_writes_allowed": False,
        "network_allowed": False,
        "verdict": report["verdict"],
        "metrics": report["metrics"],
        "baseline": report["baseline"],
        "candidate": report["candidate"],
        "artifacts": manifest["artifacts"],
    }


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Real-trace ingestion output directory or run_report.json path.",
)
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--mode", required=True, type=click.Choice(["fixture", "attention_router_bridge"]))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(
    input_path: Path,
    out_dir: Path,
    mode: str,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Run the real-trace attention-router bridge gate."""
    if mode not in {"fixture", "attention_router_bridge"}:
        raise click.ClickException("only fixture or attention_router_bridge mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_attention_router_bridge(input_path, out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("attention-router bridge gate failed")


if __name__ == "__main__":
    main()
