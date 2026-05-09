"""Deterministic skill-drift fixture demo.

Failure class: stale_skill_body_without_drift_detection

Baseline skill is never checked for staleness. Candidate diffs the current
skill body against its last-reviewed reference and flags discrepancies.

This fixture is deterministic — no network calls, no LLM, no GitHub writes.
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
# Fixture: a stale skill and a reference baseline
# ---------------------------------------------------------------------------

LAST_REVIEWED_SKILL = """## Docker Networking Troubleshooting

1. Verify containers are on the same bridge network: `docker network inspect bridge`
2. Check DNS resolution: `docker exec container1 ping container2`
3. Use a user-defined bridge network for automatic DNS: `docker network create mynet`
"""

CURRENT_SKILL_STALE = """## Docker Networking Troubleshooting

1. Verify containers are on the same bridge network: `docker network inspect bridge`
2. Check DNS resolution: `docker exec container1 ping container2`
3. Use a user-defined bridge network for automatic DNS: `docker network create mynet`
4. Also consider using Traefik as a reverse proxy for container-to-container routing.
5. Set up a Consul service mesh if you're running more than 10 containers.
"""


# ---------------------------------------------------------------------------
# Baseline: no drift detection at all
# ---------------------------------------------------------------------------

def _baseline_response() -> dict[str, Any]:
    return {
        "agent_response": "The Docker networking skill exists. No issues.",
        "drift_checked": False,
        "diff_lines": [],
        "additions": 0,
        "deletions": 0,
    }


# ---------------------------------------------------------------------------
# Candidate: diffs against last-reviewed reference
# ---------------------------------------------------------------------------

def _candidate_response() -> dict[str, Any]:
    import difflib

    diff = list(
        difflib.unified_diff(
            LAST_REVIEWED_SKILL.splitlines(keepends=True),
            CURRENT_SKILL_STALE.splitlines(keepends=True),
            fromfile="last_reviewed",
            tofile="current",
        )
    )
    additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    return {
        "agent_response": (
            "Skill drift detected: 2 additions relative to last review. "
            "Lines added include Traefik reverse proxy and Consul service mesh "
            "recommendations that were not in the reviewed version."
        ),
        "drift_checked": True,
        "diff_lines": diff,
        "additions": additions,
        "deletions": deletions,
        "recommendation": "review_and_possibly_rollback",
    }


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate_skill_drift(output: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    if not isinstance(output, dict):
        failures.append("output must be a JSON object")
        return {"passed": False, "failures": failures}

    if not output.get("drift_checked"):
        failures.append("skill drift was not checked at all")

    diff_lines = output.get("diff_lines", [])
    additions = output.get("additions", 0)

    if output.get("drift_checked") and additions > 0 and not diff_lines:
        failures.append("drift_checked is true but diff_lines is empty (inconsistent)")

    if output.get("drift_checked") and additions > 0 and not output.get("recommendation"):
        failures.append("drift detected but no recommendation given")

    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------------------
# Promotion dossier
# ---------------------------------------------------------------------------

def _build_dossier(report_path: Path, diff_path: Path, manifest_path: Path) -> str:
    return f"""# Skill-Drift Fixture Promotion Dossier

## Summary

Baseline never checks for skill staleness. Candidate diffs the current skill
body against its last-reviewed reference and flags 2 un-reviewed additions.

## Evidence

- Run report: {report_path}
- Skill diff: {diff_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm baseline output shows drift_checked=false with no diff.
2. Confirm candidate output contains diff_lines, additions, and a recommendation.
3. Confirm no network calls, GitHub writes, or production mutation.

## Promotion recommendation

Candidate passes the fixture gate and demonstrates skill-drift detection.
Suitable for manual review as a skill-maintenance artifact update.

## Rollback

Restore the no-drift-check artifact if downstream review finds the diff
heuristic too sensitive for specific skill bodies.
"""


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_skill_drift_fixture(out_dir: Path) -> dict[str, Any]:
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "run_report.json"
    diff_path = out_dir / "skill_diff.txt"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    baseline_output = _baseline_response()
    baseline_eval = evaluate_skill_drift(baseline_output)

    candidate_output = _candidate_response()
    candidate_eval = evaluate_skill_drift(candidate_output)

    diff_text = "".join(candidate_output["diff_lines"])
    diff_path.write_text(diff_text)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "task_type": "skill_drift",
        "fixture": {
            "failure_class": "stale_skill_body_without_drift_detection",
            "expected_behavior": "diff current skill body against last-reviewed reference and flag additions",
        },
        "baseline": {
            "artifact_id": "no_drift_check_v1",
            "artifact_type": "agent_behavior",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
        },
        "candidate": {
            "artifact_id": "drift_aware_agent_v1",
            "artifact_type": "agent_behavior",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
            "output_sha256": _sha256_text(
                json.dumps(candidate_output, sort_keys=True)
            ),
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

    dossier_path.write_text(_build_dossier(report_path, diff_path, manifest_path))

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "artifact_versions": {
            "baseline": "no_drift_check_v1",
            "candidate": "drift_aware_agent_v1",
        },
        "artifacts": {
            "run_report": str(report_path),
            "skill_diff": str(diff_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "restore no_drift_check_v1",
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
    if mode != "fixture":
        raise click.ClickException("only fixture mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_skill_drift_fixture(out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("skill-drift fixture gate failed")


if __name__ == "__main__":
    main()
