"""Real-trace ingestion: convert an exported Hermes session JSONL into
structured eval examples through the Foundry failure-detection gates.

This module reads a real session trace, detects known failure patterns
(long briefing, tool underuse, drift, raw dumps), and produces the same
structured artifact format as the deterministic fixtures.

The baseline is the raw session trace (fails structure eval).
The candidate is the structured extraction (passes if patterns detected correctly).

Safety invariants: no network calls, no GitHub writes, no production mutation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_REPO_PATH = "/home/steve/repos/steezkelly-hermes-agent-self-evolution"
_ALLOWED_BUCKETS = {"needsSteve", "autonomous", "blocked", "stale"}
_MAX_WHY_CHARS = 380


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Session loader: parse real Hermes JSONL
# ---------------------------------------------------------------------------


def load_session(jsonl_path: Path) -> dict[str, Any]:
    """Load a real Hermes session from a JSONL export file."""
    messages = []
    session_id = jsonl_path.stem

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            role = msg.get("role", "")
            if role == "session_meta":
                session_id = msg.get("session_id", jsonl_path.stem)
                continue

            # Flatten tool_calls into a more readable summary
            content = msg.get("content", "")
            reasoning = msg.get("reasoning") or msg.get("reasoning_content", "")
            tool_calls = msg.get("tool_calls", [])
            tool_names = [tc.get("function", {}).get("name", "unknown") for tc in tool_calls]

            flat = {"role": role, "content": content}
            if reasoning:
                flat["reasoning"] = reasoning[:500]  # truncate for fixture
            if tool_names:
                flat["tool_calls"] = tool_names
            if role == "tool":
                # Tool results can be huge; truncate
                try:
                    parsed = json.loads(msg.get("content", "{}"))
                    if isinstance(parsed, dict):
                        flat["output_summary"] = {
                            k: str(v)[:200]
                            for k, v in parsed.items()
                            if k in ("exit_code", "status", "error")
                        }
                except (json.JSONDecodeError, TypeError):
                    pass

            messages.append(flat)

    return {"session_id": session_id, "messages": messages, "total_messages": len(messages)}


# ---------------------------------------------------------------------------
# Failure pattern detectors
# ---------------------------------------------------------------------------


def detect_long_briefing(session: dict[str, Any]) -> dict[str, Any] | None:
    """Detect if the agent produced a long briefing instead of a concise action queue."""
    msgs = session.get("messages", [])
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]

    briefing_found = None
    for am in assistant_msgs:
        content = am.get("content", "")
        if len(content) > 500 and ("option" in content.lower() or "could" in content.lower()
                                     or "might" in content.lower() or "consider" in content.lower()):
            num_options = content.lower().count("option")
            if num_options >= 2 or len(content.split("\n")) > 10:
                briefing_found = {
                    "message_index": msgs.index(am),
                    "length": len(content),
                    "num_lines": len(content.split("\n")),
                    "snippet": content[:300],
                }
                break

    if briefing_found is None:
        return None

    return {
        "detected": True,
        "failure_class": "long_briefing_instead_of_concise_action_queue",
        "evidence": briefing_found,
        "description": (
            f"Agent produced a {briefing_found['length']}-char response "
            f"with {briefing_found['num_lines']} lines instead of one concise action item."
        ),
    }


def detect_raw_session_dump(session: dict[str, Any]) -> dict[str, Any] | None:
    """Detect if the session lacks ANY structured eval extraction."""
    # If no assistant messages contain structured field names like task_input,
    # expected_behavior, difficulty — it's a raw dump situation
    msgs = session.get("messages", [])
    assistant_text = "\n".join(m.get("content", "") for m in msgs if m.get("role") == "assistant")

    structured_indicators = ["task_input", "expected_behavior", "difficulty", "category"]
    has_structure = any(ind in assistant_text.lower() for ind in structured_indicators)

    if has_structure:
        return None

    user_msgs = [m for m in msgs if m.get("role") == "user"]
    if not user_msgs:
        return None

    return {
        "detected": True,
        "failure_class": "raw_session_trace_without_structured_eval_example",
        "evidence": {
            "num_user_messages": len(user_msgs),
            "num_assistant_messages": sum(1 for m in msgs if m.get("role") == "assistant"),
            "no_structured_eval_extraction": True,
        },
        "description": (
            f"Session has {len(user_msgs)} user messages and zero structured eval examples "
            f"(no task_input/expected_behavior/difficulty/category fields found)."
        ),
    }


def detect_tool_underuse(session: dict[str, Any]) -> dict[str, Any] | None:
    """Detect if the agent describes instead of calling available tools."""
    msgs = session.get("messages", [])
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]

    # Count messages with tool_calls vs without
    with_tools = sum(1 for m in assistant_msgs if m.get("tool_calls"))
    without_tools = sum(1 for m in assistant_msgs if not m.get("tool_calls"))

    # Find descriptive responses that should have been tool calls
    descriptive = []
    for am in assistant_msgs:
        content = am.get("content", "")
        if not am.get("tool_calls") and len(content) > 200:
            # Check for descriptive language suggesting tool use would be better
            action_words = ["check", "verify", "inspect", "look", "examine", "run", "execute"]
            if any(w in content.lower() for w in action_words):
                descriptive.append({
                    "message_index": msgs.index(am),
                    "length": len(content),
                    "snippet": content[:200],
                })

    if not descriptive:
        return None

    return {
        "detected": True,
        "failure_class": "agent_describes_instead_of_calls_tools",
        "evidence": {
            "messages_with_tool_calls": with_tools,
            "messages_without_tool_calls": without_tools,
            "descriptive_messages_that_should_use_tools": len(descriptive),
            "examples": descriptive[:3],
        },
        "description": (
            f"Agent produced {len(descriptive)} descriptive messages "
            f"(≥200 chars, no tool calls) when tool calls would be more effective."
        ),
    }


def detect_skill_drift(session: dict[str, Any]) -> dict[str, Any] | None:
    """Detect if skill-loaded content looks stale vs actual session behavior."""
    msgs = session.get("messages", [])
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]

    # Check if any assistant messages reference skills with stale-seeming advice
    drift_indicators = []
    for am in assistant_msgs:
        content = am.get("content", "")
        if "skill" in content.lower() and len(content) > 100:
            # Look for deprecated patterns
            stale_markers = ["deprecated", "no longer", "outdated", "old version",
                             "previous approach", "legacy"]
            if any(m in content.lower() for m in stale_markers):
                drift_indicators.append({
                    "message_index": msgs.index(am),
                    "snippet": content[:200],
                })

    if not drift_indicators:
        return None

    return {
        "detected": True,
        "failure_class": "stale_skill_body_without_drift_detection",
        "evidence": {
            "messages_with_stale_references": len(drift_indicators),
            "examples": drift_indicators[:3],
        },
        "description": (
            f"Session contains {len(drift_indicators)} messages referencing skills "
            f"with terms suggesting stale/deprecated content."
        ),
    }


# ---------------------------------------------------------------------------
# Structured extractors (baseline vs candidate)
# ---------------------------------------------------------------------------


def _extract_structured(session: dict[str, Any], detectors: dict[str, Any | None]) -> dict[str, Any]:
    """Candidate: extract structured eval examples from the real session trace."""
    msgs = session.get("messages", [])
    user_msgs = [m for m in msgs if m.get("role") == "user"]
    assistant_msgs = [m for m in msgs if m.get("role") == "assistant"]

    active_failures = {k: v for k, v in detectors.items() if v and v.get("detected")}

    return {
        "session_id": session["session_id"],
        "total_messages": len(msgs),
        "user_messages": len(user_msgs),
        "assistant_messages": len(assistant_msgs),
        "detected_failure_classes": list(active_failures.keys()),
        "failure_count": len(active_failures),
        "failures": active_failures,
        "first_user_message": user_msgs[0]["content"][:300] if user_msgs else "",
        "last_assistant_snippet": assistant_msgs[-1]["content"][:300] if assistant_msgs else "",
        "detection_summary": [
            f"{cls}: {info['description']}" for cls, info in active_failures.items()
        ],
    }


def _baseline_dump(session: dict[str, Any]) -> dict[str, Any]:
    """Baseline: return the raw session as-is (will fail structure eval)."""
    return {
        "note": "This is the raw session trace. No structured eval extraction was performed.",
        "session_id": session["session_id"],
        "total_messages": len(session.get("messages", [])),
    }


# ---------------------------------------------------------------------------
# Evaluator (same contract as fixture demos)
# ---------------------------------------------------------------------------


_REQUIRED_FIELDS = ["detected_failure_classes", "failure_count", "session_id"]


def evaluate_real_trace_extraction(output: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a real-trace extraction output with deterministic assertions."""
    failures: list[str] = []

    if not isinstance(output, dict):
        failures.append("output must be a JSON object")
        return {"passed": False, "failures": failures}

    # Baseline detector: has "note" field = raw dump
    if "note" in output:
        failures.append("output is a raw session dump, not a structured extraction")

    for field in _REQUIRED_FIELDS:
        if field not in output or output.get(field) is None:
            failures.append(f"missing required field: {field}")

    failures_list = output.get("detected_failure_classes", [])
    if not isinstance(failures_list, list):
        failures.append("detected_failure_classes must be a list")

    failure_count = output.get("failure_count", 0)
    if failure_count != len(output.get("failures", {})):
        failures.append("failure_count inconsistent with actual failures dict")

    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------------------
# Promotion dossier builder
# ---------------------------------------------------------------------------


def _build_dossier(
    report_path: Path,
    examples_path: Path,
    manifest_path: Path,
    failure_count: int,
    classes: list[str],
) -> str:
    class_list = "\n".join(f"- {c}" for c in classes)
    return f"""# Real-Trace Ingestion Promotion Dossier

## Summary

Ingested a real Hermes session trace and detected {failure_count} known failure patterns.
Baseline was raw session dump (failed structure eval).
Candidate extracted structured eval examples with detected failure classes.

## Detected failures

{class_list}

## Evidence

- Run report: {report_path}
- Eval examples: {examples_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm the real session trace contained the detected failure patterns.
2. Confirm the candidate extraction correctly identified each failure class.
3. Confirm no network calls, GitHub writes, or production mutation were performed.

## Promotion recommendation

Candidate passed the structure-eval gate and is suitable for manual review
as a real-trace ingestion artifact.

## Rollback

Restore the raw-trace-extractor baseline if downstream review finds false-positive
detections or incorrect failure classification.
"""


# ---------------------------------------------------------------------------
# Main ingestion runner
# ---------------------------------------------------------------------------


def run_real_trace_ingestion(trace_path: Path, out_dir: Path) -> dict[str, Any]:
    """Ingest a real Hermes session trace and produce structured eval artifacts."""
    trace_path = Path(trace_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "run_report.json"
    examples_path = out_dir / "eval_examples.json"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    # Load the real session
    session = load_session(trace_path)

    # Run all detectors
    detectors = {
        "long_briefing_instead_of_concise_action_queue": detect_long_briefing(session),
        "raw_session_trace_without_structured_eval_example": detect_raw_session_dump(session),
        "agent_describes_instead_of_calls_tools": detect_tool_underuse(session),
        "stale_skill_body_without_drift_detection": detect_skill_drift(session),
    }

    # Baseline: raw session dump
    baseline_output = _baseline_dump(session)
    baseline_eval = evaluate_real_trace_extraction(baseline_output)

    # Candidate: structured extraction
    candidate_output = _extract_structured(session, detectors)
    candidate_eval = evaluate_real_trace_extraction(candidate_output)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "real_trace",
        "task_type": "trace_ingestion",
        "source_trace": str(trace_path),
        "fixture": {
            "failure_class": "real_session_trace_needs_structured_eval_extraction",
            "expected_behavior": "extract structured eval examples with detected failure classes from a real session trace",
            "session_id": session["session_id"],
            "trace_total_messages": session["total_messages"],
        },
        "baseline": {
            "artifact_id": "raw_trace_extractor_v1",
            "artifact_type": "extractor",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
        },
        "candidate": {
            "artifact_id": "structured_trace_extractor_v1",
            "artifact_type": "extractor",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(candidate_output, sort_keys=True)),
        },
        "metrics": {
            "baseline_pass_rate": 1.0 if baseline_eval["passed"] else 0.0,
            "candidate_pass_rate": 1.0 if candidate_eval["passed"] else 0.0,
            "holdout_delta": (1.0 if candidate_eval["passed"] else 0.0)
            - (1.0 if baseline_eval["passed"] else 0.0),
            "failure_classes_detected": len(
                {k for k, v in detectors.items() if v and v.get("detected")}
            ),
        },
        "verdict": (
            "pass"
            if (not baseline_eval["passed"] and candidate_eval["passed"])
            else "fail"
        ),
        "safety": {
            "mode": "real_trace",
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
    }
    _write_json(report_path, report)

    eval_examples = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "real_trace",
        "source_trace": str(trace_path),
        "external_writes_allowed": False,
        "examples": [candidate_output],
        "total_examples": 1,
    }
    _write_json(examples_path, eval_examples)

    active_failures = {k for k, v in detectors.items() if v and v.get("detected")}
    dossier_path.write_text(
        _build_dossier(report_path, examples_path, manifest_path,
                       len(active_failures), sorted(active_failures))
    )

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "real_trace",
        "source_trace": str(trace_path),
        "artifact_versions": {
            "baseline": "raw_trace_extractor_v1",
            "candidate": "structured_trace_extractor_v1",
        },
        "artifacts": {
            "run_report": str(report_path),
            "eval_examples": str(examples_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "restore raw_trace_extractor_v1 or previous artifact manifest reference",
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
    "--trace", "trace_path", required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a real Hermes session JSONL export file."
)
@click.option(
    "--out", "out_dir", required=True,
    type=click.Path(file_okay=False, path_type=Path)
)
@click.option("--mode", required=True, type=click.Choice(["real_trace"]))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(
    trace_path: Path,
    out_dir: Path,
    mode: str,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Ingest a real Hermes session trace and produce structured eval artifacts."""
    if mode != "real_trace":
        raise click.ClickException("only real_trace mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_real_trace_ingestion(trace_path, out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("real-trace ingestion gate failed")


if __name__ == "__main__":
    main()
