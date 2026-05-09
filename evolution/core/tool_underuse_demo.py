"""Deterministic tool-underuse fixture demo.

Failure class: agent_describes_instead_of_calls_tools

Baseline agent describes what it would do verbally ("I will run the tests, check
the logs, then review the config") without ever making a tool call. Candidate
agent makes actual tool calls (terminal, read_file) and reports results.

This fixture demonstrates the most common Hermes Agent failure pattern and
proves it can be caught with deterministic assertions — no LLM needed for
the fixture path, no network calls, no GitHub writes, no production mutation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

_FIXED_GENERATED_AT = "1970-01-01T00:00:00Z"
_REPO_PATH = "/home/steve/repos/steezkelly-hermes-agent-self-evolution"

# Tool names that count as "actual tool usage" vs verbal description
_TOOL_NAMES = {
    "terminal", "read_file", "write_file", "search_files", "web_search",
    "web_extract", "patch", "delegate_task", "execute_code", "memory",
    "clarify", "todo", "skill_view", "skill_manage",
}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Fixture: a task that clearly requires tool use
# ---------------------------------------------------------------------------

FIXTURE_TASK = {
    "task": "Check the disk usage on the current machine and report which directory under /var is consuming the most space.",
    "expected_tool_calls": ["terminal"],
    "expected_tool_commands": ["du", "df", "ncdu"],
}


# ---------------------------------------------------------------------------
# Baseline: describes actions without calling tools
# ---------------------------------------------------------------------------

def _baseline_response() -> dict[str, Any]:
    """Old behavior: describes what it would do, never invokes a tool."""
    return {
        "agent_response": (
            "I will check the disk usage on this machine. I would run `df -h` "
            "to see the overall disk usage, then `du -sh /var/* | sort -rh | head -5` "
            "to find which directory under /var is consuming the most space. Once I "
            "have those results, I'd report the findings. Let me know if you want "
            "me to proceed with the check."
        ),
        "tool_calls_made": [],
        "tool_call_count": 0,
        "describes_actions": True,
        "actually_executes": False,
    }


# ---------------------------------------------------------------------------
# Candidate: makes actual tool calls and reports results
# ---------------------------------------------------------------------------

def _candidate_response() -> dict[str, Any]:
    """New behavior: makes actual tool calls, reports results from output."""
    return {
        "agent_response": (
            "Ran `df -h` and `du -sh /var/* | sort -rh | head -5` to check disk usage. "
            "The largest directory under /var is /var/log at 2.1G, followed by "
            "/var/cache at 890M and /var/lib at 450M. Total disk usage is 67% on the "
            "root partition."
        ),
        "tool_calls_made": [
            {
                "tool": "terminal",
                "command": "df -h /",
                "exit_code": 0,
                "output_preview": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1        50G   32G   16G  67% /",
            },
            {
                "tool": "terminal",
                "command": "du -sh /var/* 2>/dev/null | sort -rh | head -5",
                "exit_code": 0,
                "output_preview": "2.1G    /var/log\n890M    /var/cache\n450M    /var/lib\n120M    /var/tmp\n8.0K    /var/local",
            },
        ],
        "tool_call_count": 2,
        "describes_actions": False,
        "actually_executes": True,
    }


# ---------------------------------------------------------------------------
# Evaluator: checks for actual tool usage vs verbal descriptions
# ---------------------------------------------------------------------------

def evaluate_tool_usage(output: dict[str, Any]) -> dict[str, Any]:
    """Evaluate whether the agent made tool calls or just described them."""
    failures: list[str] = []

    if not isinstance(output, dict):
        failures.append("output must be a JSON object")
        return {"passed": False, "failures": failures}

    # Check for verbal description patterns
    agent_response = output.get("agent_response", "")
    if not agent_response:
        failures.append("agent_response is empty")

    describes_actions = output.get("describes_actions", False)
    actually_executes = output.get("actually_executes", False)

    if describes_actions and not actually_executes:
        failures.append(
            "agent describes actions verbally instead of making tool calls"
        )

    tool_call_count = output.get("tool_call_count", 0)
    if tool_call_count == 0:
        failures.append("no tool calls were made")

    tool_calls_made = output.get("tool_calls_made", [])
    if isinstance(tool_calls_made, list) and not tool_calls_made:
        failures.append("tool_calls_made is empty")

    # Check for "I will" / "I would" / "Let me" verbal patterns
    # that signal description instead of execution
    verbal_tells = ["I will", "I would", "I'll run", "I'd run", "let me"]
    for tell in verbal_tells:
        if tell.lower() in agent_response.lower():
            if actually_executes and tool_call_count > 0:
                # Candidate might still mention what it did ("I ran df -h and found...")
                pass
            elif not actually_executes:
                failures.append(
                    f"agent uses verbal future-tense ('{tell}') without making tool calls"
                )
                break

    return {"passed": not failures, "failures": failures}


# ---------------------------------------------------------------------------
# Promotion dossier builder
# ---------------------------------------------------------------------------

def _build_dossier(
    report_path: Path, snapshot_path: Path, manifest_path: Path
) -> str:
    return f"""# Tool-Underuse Fixture Promotion Dossier

## Summary

Baseline agent described actions verbally ("I will run df -h...") without
making any tool calls. Candidate agent made actual terminal tool calls
(df, du) and reported results from the output.

## Evidence

- Run report: {report_path}
- Tool usage snapshot: {snapshot_path}
- Artifact manifest: {manifest_path}

## Manual review

1. Confirm baseline response uses "I will" / "I would" language with zero tool calls.
2. Confirm candidate response contains tool_calls_made entries with exit codes and output.
3. Confirm no network calls, GitHub writes, or production mutation were allowed.

## Promotion recommendation

Candidate passed the fixture gate and demonstrates the tool-enforcement pattern
that the agent persona requires. Suitable for manual review as a tool-usage
artifact update.

## Rollback

Restore the description-only artifact if downstream review finds the tool-call
pattern too rigid for specific interaction styles.
"""


# ---------------------------------------------------------------------------
# Main fixture runner
# ---------------------------------------------------------------------------

def run_tool_underuse_fixture(out_dir: Path) -> dict[str, Any]:
    """Run the deterministic tool-underuse fixture and write all artifacts."""
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "run_report.json"
    snapshot_path = out_dir / "tool_usage_snapshot.json"
    dossier_path = out_dir / "promotion_dossier.md"
    manifest_path = out_dir / "artifact_manifest.json"

    baseline_output = _baseline_response()
    baseline_eval = evaluate_tool_usage(baseline_output)

    candidate_output = _candidate_response()
    candidate_eval = evaluate_tool_usage(candidate_output)

    report = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "task_type": "tool_underuse",
        "fixture": {
            "failure_class": "agent_describes_instead_of_calls_tools",
            "expected_behavior": "make actual tool calls to gather information and report results from tool output, not from speculation",
            "task": FIXTURE_TASK["task"],
        },
        "baseline": {
            "artifact_id": "description_agent_v1",
            "artifact_type": "agent_behavior",
            "passed": baseline_eval["passed"],
            "failures": baseline_eval["failures"],
            "output_sha256": _sha256_text(json.dumps(baseline_output, sort_keys=True)),
            "tool_call_count": baseline_output["tool_call_count"],
        },
        "candidate": {
            "artifact_id": "tool_enforcing_agent_v1",
            "artifact_type": "agent_behavior",
            "passed": candidate_eval["passed"],
            "failures": candidate_eval["failures"],
            "output_sha256": _sha256_text(
                json.dumps(candidate_output, sort_keys=True)
            ),
            "tool_call_count": candidate_output["tool_call_count"],
        },
        "metrics": {
            "baseline_pass_rate": 1.0 if baseline_eval["passed"] else 0.0,
            "candidate_pass_rate": 1.0 if candidate_eval["passed"] else 0.0,
            "holdout_delta": (1.0 if candidate_eval["passed"] else 0.0)
            - (1.0 if baseline_eval["passed"] else 0.0),
            "tool_call_delta": candidate_output["tool_call_count"]
            - baseline_output["tool_call_count"],
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

    tool_usage_snapshot = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "external_writes_allowed": False,
        "baseline": baseline_output,
        "candidate": candidate_output,
        "comparison": {
            "baseline_tool_calls": baseline_output["tool_call_count"],
            "candidate_tool_calls": candidate_output["tool_call_count"],
            "improvement": f"+{candidate_output['tool_call_count'] - baseline_output['tool_call_count']} tool calls",
        },
    }
    _write_json(snapshot_path, tool_usage_snapshot)

    dossier_path.write_text(
        _build_dossier(report_path, snapshot_path, manifest_path)
    )

    manifest = {
        "schema_version": 1,
        "generated_at": _FIXED_GENERATED_AT,
        "mode": "fixture",
        "artifact_versions": {
            "baseline": "description_agent_v1",
            "candidate": "tool_enforcing_agent_v1",
        },
        "artifacts": {
            "run_report": str(report_path),
            "tool_usage_snapshot": str(snapshot_path),
            "promotion_dossier": str(dossier_path),
            "artifact_manifest": str(manifest_path),
        },
        "external_writes_allowed": False,
        "review_required": True,
        "rollback": "restore description_agent_v1 or previous artifact manifest reference",
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
    """Run the deterministic tool-underuse fixture demo."""
    if mode != "fixture":
        raise click.ClickException("only fixture mode is supported")
    if not no_network:
        raise click.ClickException("--no-network is required")
    if not no_external_writes:
        raise click.ClickException("--no-external-writes is required")

    result = run_tool_underuse_fixture(out_dir)
    if result["verdict"] != "pass":
        raise click.ClickException("tool-underuse fixture gate failed")


if __name__ == "__main__":
    main()
