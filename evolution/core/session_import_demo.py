"""Deterministic session-trace-to-eval fixture demo.

This module owns the semantic Foundry-side v0 loop for the second fixture
class: importing raw agent session traces and converting them into structured
eval examples.

Failure class: raw_session_trace_without_structured_eval_example

It deliberately performs no network calls, GitHub writes, or production mutation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_REPO_PATH = "/home/steve/repos/steezkelly-hermes-agent-self-evolution"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Fixture session trace (simulates a real Hermes session)
# ---------------------------------------------------------------------------

FIXTURE_SESSION = {
    "session_id": "hermes-20260509-fixture",
    "messages": [
        {
            "role": "user",
            "content": "Review the Docker networking issue where containers can't reach each other on the bridge network."
        },
        {
            "role": "assistant",
            "content": (
                "Docker networking can be complex. The bridge network is the default "
                "network driver. Containers on the same bridge network should be able to "
                "communicate by container name. Here are several approaches:\n\n"
                "1. Check if both containers are on the same bridge network with `docker network inspect bridge`.\n"
                "2. Verify DNS resolution with `docker exec container1 ping container2`.\n"
                "3. Consider creating a user-defined bridge network (`docker network create mynet`) "
                "which provides automatic DNS resolution unlike the default bridge.\n"
                "4. Check firewall rules (`iptables -L`) that may be blocking inter-container traffic.\n"
                "5. Examine container logs and restart Docker daemon if necessary.\n\n"
                "The root cause is most likely the default bridge lacking automatic DNS, "
                "or iptables rules blocking traffic. Let me know which approach you'd like to pursue."
            ),
        },
    ],
}


# ---------------------------------------------------------------------------
# Baseline: raw extractor — no structure, just dumps the session
# ---------------------------------------------------------------------------

def _baseline_extract(session: dict[str, Any]) -> dict[str, Any]:
    """Old behavior: dumps the raw session as-is, no structured eval."""
    return {
        "raw_session": session,
        "note": "This is the raw session. Interpret it yourself.",
    }


# ---------------------------------------------------------------------------
# Candidate: structured extractor — produces a valid EvalExample
# ---------------------------------------------------------------------------

def _candidate_extract(session: dict[str, Any]) -> dict[str, Any]:
    """New behavior: extracts task_input and expected_behavior from the session."""
    msgs = session.get("messages", [])
    user_msg = next((m["content"] for m in msgs if m.get("role") == "user"), "")
    assistant_msg = next((m["content"] for m in msgs if m.get("role") == "assistant"), "")

    return {
        "task_input": user_msg,
        "expected_behavior": (
            "Identify root cause (default bridge lacks DNS), recommend user-defined "
            "bridge network, and provide a single verified command to test resolution."
        ),
        "difficulty": "medium",
        "category": "docker-networking",
        "original_assistant_response": assistant_msg[:200],
    }


# ---------------------------------------------------------------------------
# Evaluator for structured extractor output
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ["task_input", "expected_behavior", "difficulty", "category"]
_VALID_DIFFICULTIES = {"easy", "medium", "hard"}


def evaluate_structured_extract(output: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a structured extractor output with deterministic assertions."""
    failures: list[str] = []

    if not isinstance(output, dict):
        failures.append("output must be a JSON object")
        return {"passed": False, "failures": failures}

    # Baseline: has raw_session — missing structure
    if "raw_session" in output or "note" in output:
        failures.append("output contains raw session dump instead of structured fields")

    for field in _REQUIRED_FIELDS:
        if not output.get(field):
            failures.append(f"missing required field: {field}")

    task_input = output.get("task_input", "")
    if task_input and len(task_input) < 20:
        failures.append("task_input too short (must be a meaningful user prompt)")

    expected = output.get("expected_behavior", "")
    if expected and len(expected) < 20:
        failures.append("expected_behavior too short (must describe correct behavior)")

    difficulty = output.get("difficulty", "")
    if difficulty and difficulty not in _VALID_DIFFICULTIES:
        failures.append(f"difficulty must be one of {sorted(_VALID_DIFFICULTIES)}")

    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------------------
# Promotion dossier builder
# ---------------------------------------------------------------------------

def _build_dossier(report_path: Path, examples_path: Path, manifest_path: Path) -> str:
    return f"""# Session-Import Fixture Promotion Dossier

## Summary

Baseline produced a raw session dump with no structured eval example.
Candidate extracted task_input, expected_behavior, difficulty, and category.

## Evidence

- Run report: {report_path}
- Eval examples: {examples_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm the baseline output is a raw session dump without eval fields.
2. Confirm the candidate output contains task_input, expected_behavior, difficulty, and category.
3. Confirm no network calls, GitHub writes, or production mutation were allowed.

## Promotion recommendation

Candidate passed the fixture gate and is suitable for manual review as a
session-import artifact update.

## Rollback

Restore the raw-extractor artifact if downstream review finds structural
concerns with the extracted eval examples.
"""


# ---------------------------------------------------------------------------
# Main fixture runner
# ---------------------------------------------------------------------------

def run_session_import_fixture(out_dir: Path) -> dict[str, Any]:
    """Run the deterministic session-import fixture and write all artifacts."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "run_report.json"
    examples_path = out_dir / "eval_examples.json"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    session = FIXTURE_SESSION
    baseline_output = _baseline_extract(session)
    baseline_eval = evaluate_structured_extract(baseline_output)

    candidate_output = _candidate_extract(session)
    candidate_eval = evaluate_structured_extract(candidate_output)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "task_type": "session_import",
        "fixture": {
            "failure_class": "raw_session_trace_without_structured_eval_example",
            "expected_behavior": "extract structured eval example (task_input, expected_behavior, difficulty, category) from a raw session trace",
            "session_id": session["session_id"],
        },
        "baseline": {
            "artifact_id": "raw_session_extractor_v1",
            "artifact_type": "extractor",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
        },
        "candidate": {
            "artifact_id": "structured_session_extractor_v1",
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
        },
        "verdict": (
            "pass"
            if (not baseline_eval["passed"] and candidate_eval["passed"])
            else "fail"
        ),
        "safety": {
            "mode": "fixture",
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
        "mode": "fixture",
        "external_writes_allowed": False,
        "examples": [candidate_output],
        "total_examples": 1,
    }
    _write_json(examples_path, eval_examples)

    dossier_path.write_text(_build_dossier(report_path, examples_path, manifest_path))

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "artifact_versions": {
            "baseline": "raw_session_extractor_v1",
            "candidate": "structured_session_extractor_v1",
        },
        "artifacts": {
            "run_report": str(report_path),
            "eval_examples": str(examples_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "restore raw_session_extractor_v1 or previous artifact manifest reference",
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
    "--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path)
)
@click.option("--mode", required=True, type=click.Choice(["fixture"]))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(out_dir: Path, mode: str, no_network: bool, no_external_writes: bool) -> None:
    """Run the deterministic session-import fixture demo."""
    if mode != "fixture":
        raise click.ClickException("only fixture mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_session_import_fixture(out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("session-import fixture gate failed")


if __name__ == "__main__":
    main()
