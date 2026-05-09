"""Deterministic action-router fixture demo.

This module owns the semantic Foundry-side v0 loop for issue #10:
one repeated failure -> one eval -> one better artifact -> one measured win ->
one manual promotion recommendation.

It deliberately performs no network calls, GitHub writes, or production mutation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

_ALLOWED_BUCKETS = {"needsSteve", "autonomous", "blocked", "stale"}
_MAX_WHY_CHARS = 380
_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_FIXED_EXPIRES_AT = "1970-01-08T00:00:00Z"
_REPO_PATH = "/home/steve/repos/steezkelly-hermes-agent-self-evolution"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _baseline_action_router_output() -> dict[str, Any]:
    """Old behavior: long briefing/options, missing action-item contract fields."""
    return {
        "body": (
            "The architecture review suggests several paths. We could revise the "
            "bootstrap plan, create a Foundry-side demo, wait for more research, "
            "or prepare another long synthesis. The safest option may be to keep "
            "thinking through the implications before choosing which repository "
            "should own the next piece of work."
        ),
        "options": [
            "revise bootstrap roadmap",
            "create Foundry demo",
            "write another synthesis",
        ],
    }


def _candidate_action_router_output(report_path: Path, dossier_path: Path) -> dict[str, Any]:
    """New behavior: exactly one concise, copyable action item."""
    return {
        "bucket": "needsSteve",
        "priority": 1,
        "owner": "steve",
        "title": "Approve Foundry action-router fixture promotion",
        "why": "Baseline produced a long briefing; candidate passed the concise action-item contract with local evidence and no external writes.",
        "evidence_paths": [str(report_path), str(dossier_path)],
        "next_prompt": (
            f"Work in `{_REPO_PATH}`. Review the action-router fixture evidence, "
            "then promote the candidate action-router artifact only if the local "
            "gate result and dossier are acceptable."
        ),
        "expires_at": _FIXED_EXPIRES_AT,
        "dedupe_key": "foundry:action-router-fixture:v0",
    }


def evaluate_action_item(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an action-router output with deterministic assertions."""
    failures: list[str] = []

    if not isinstance(candidate, dict):
        failures.append("output must be a JSON object")
        return {"passed": False, "failures": failures}

    if "options" in candidate:
        failures.append("output must contain exactly one action item, not multiple options")

    for field in ["bucket", "owner", "title", "why", "evidence_paths", "next_prompt", "expires_at"]:
        if not candidate.get(field):
            failures.append(f"missing required field: {field}")

    bucket = candidate.get("bucket")
    if bucket and bucket not in _ALLOWED_BUCKETS:
        failures.append(f"bucket must be one of {sorted(_ALLOWED_BUCKETS)}")

    evidence_paths = candidate.get("evidence_paths")
    if evidence_paths:
        if not isinstance(evidence_paths, list):
            failures.append("evidence_paths must be a list")
        else:
            for path in evidence_paths:
                p = Path(path)
                if not p.is_absolute():
                    failures.append(f"evidence path is not absolute: {path}")
                elif not p.exists():
                    failures.append(f"evidence path does not exist: {path}")

    why = candidate.get("why")
    if why and len(why) > _MAX_WHY_CHARS:
        failures.append(f"why exceeds {_MAX_WHY_CHARS} characters")

    next_prompt = candidate.get("next_prompt")
    if next_prompt and "Work in" not in next_prompt:
        failures.append("next_prompt must be ready to paste into Hermes and include a working directory")

    return {"passed": not failures, "failures": failures}


def _build_promotion_dossier(report_path: Path, queue_path: Path, manifest_path: Path) -> str:
    return f"""# Action Router Fixture Promotion Dossier

## Summary

Baseline failed the concise action-item contract. Candidate passed the deterministic fixture gate.

## Evidence

- Run report: {report_path}
- Action queue: {queue_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm the baseline failure reproduces a long briefing instead of one action item.
2. Confirm the candidate output contains owner, evidence paths, next prompt, expiry, and a concise reason.
3. Confirm no network calls, GitHub writes, or production mutation were allowed.

## Promotion recommendation

Candidate passed the fixture gate and is suitable for manual review as an action-router artifact update.

## Rollback

Restore `action_router_v1` / the previous artifact manifest reference if downstream review finds ambiguity or operator-edit burden.
"""


def run_action_routing_fixture(out_dir: Path) -> dict[str, Any]:
    """Run the deterministic action-routing fixture and write all artifacts."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "run_report.json"
    queue_path = out_dir / "action_queue.json"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    baseline_output = _baseline_action_router_output()
    baseline_eval = evaluate_action_item(baseline_output)

    # Candidate validation requires local evidence paths to exist. Create placeholder
    # artifacts first; they are overwritten with final content below.
    report_path.write_text("{}\n")
    dossier_text = _build_promotion_dossier(report_path, queue_path, manifest_path)
    dossier_path.write_text(dossier_text)
    candidate_output = _candidate_action_router_output(report_path, dossier_path)
    candidate_eval = evaluate_action_item(candidate_output)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "task_type": "action_routing",
        "fixture": {
            "failure_class": "long_briefing_instead_of_concise_action_queue",
            "expected_behavior": "emit exactly one concise action item with owner, evidence_paths, next_prompt, and expires_at",
        },
        "baseline": {
            "artifact_id": "action_router_v1",
            "artifact_type": "template",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
        },
        "candidate": {
            "artifact_id": "action_router_v2",
            "artifact_type": "template",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(candidate_output, sort_keys=True)),
        },
        "metrics": {
            "baseline_pass_rate": 1.0 if baseline_eval["passed"] else 0.0,
            "candidate_pass_rate": 1.0 if candidate_eval["passed"] else 0.0,
            "holdout_delta": (1.0 if candidate_eval["passed"] else 0.0) - (1.0 if baseline_eval["passed"] else 0.0),
        },
        "verdict": "pass" if (not baseline_eval["passed"] and candidate_eval["passed"]) else "fail",
        "safety": {
            "mode": "fixture",
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
    }
    _write_json(report_path, report)

    action_queue = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "external_writes_allowed": False,
        "items": [candidate_output],
    }
    _write_json(queue_path, action_queue)

    # Rewrite dossier after the report exists so all evidence paths are present.
    dossier_path.write_text(_build_promotion_dossier(report_path, queue_path, manifest_path))

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "artifact_versions": {
            "baseline": "action_router_v1",
            "candidate": "action_router_v2",
        },
        "artifacts": {
            "run_report": str(report_path),
            "action_queue": str(queue_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "restore action_router_v1 or previous artifact manifest reference",
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
@click.option("--out", "out_dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--mode", required=True, type=click.Choice(["fixture"]))
@click.option("--no-network", is_flag=True, default=False)
@click.option("--no-external-writes", is_flag=True, default=False)
def main(out_dir: Path, mode: str, no_network: bool, no_external_writes: bool) -> None:
    """Run the deterministic action-router fixture demo."""
    if mode != "fixture":
        raise click.ClickException("only fixture mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_action_routing_fixture(out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("action-routing fixture gate failed")


if __name__ == "__main__":
    main()
