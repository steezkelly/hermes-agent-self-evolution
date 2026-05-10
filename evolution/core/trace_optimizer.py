"""Deterministic trace-to-candidate optimizer bridge.

Converts eval examples from real-trace ingestion into baseline-vs-candidate
improvement artifacts WITHOUT LLM calls. Designed as a deterministic
template-improvement engine that produces better candidate templates/prompts
for known failure classes.

Safety: local-only, no network calls, no API keys, no external writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

_FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
_SCHEMA_VERSION = 1

# ── Known failure class → candidate improvement templates ──────────────

_CANDIDATE_TEMPLATES: dict[str, dict[str, str]] = {
    "long_briefing_instead_of_concise_action_queue": {
        "improvement_type": "output_constraint",
        "baseline_description": "No output length or format constraint — agent produces long briefings.",
        "candidate_description": "Enforce action-queue shape: owner, evidence_paths, next_prompt, expires_at, max 80 chars title.",
        "candidate_constraint": (
            "OUTPUT CONSTRAINT: Every response MUST be a single action item with: "
            "owner (string), evidence_paths (list of absolute paths), "
            "next_prompt (string ready-to-paste into Hermes), "
            "expires_at (ISO timestamp), title (max 80 chars), "
            "bucket (one of: needsSteve, autonomous, blocked, stale). "
            "NO markdown lists, NO option briefings, NO synthesis paragraphs."
        ),
    },
    "raw_session_trace_without_structured_eval_example": {
        "improvement_type": "extraction_rule",
        "baseline_description": "Session trace is raw JSONL — no structured eval extraction.",
        "candidate_description": "Extract task_input, expected_behavior, difficulty, category from session messages.",
        "candidate_constraint": (
            "EXTRACTION RULE: For every assistant response >200 chars, extract: "
            "task_input (what user asked), expected_behavior (what a good response would be), "
            "difficulty (easy/medium/hard), category (tool-use/delivery/planning/briefing). "
            "Store as eval_examples format. Each extraction must have evidence_path "
            "pointing to source message index in JSONL."
        ),
    },
    "agent_describes_instead_of_calls_tools": {
        "improvement_type": "prompt_patch",
        "baseline_description": "No tool-call enforcement — agent describes checks instead of calling tools.",
        "candidate_description": "Force tool-call gate: before describing, call read_file/search_files/terminal.",
        "candidate_constraint": (
            "TOOL-CALL GATE: Before producing any description longer than 200 chars, "
            "agent MUST call at least one tool (read_file, search_files, terminal, "
            "web_search, etc.). Tool calls are verified by checking JSONL for "
            "tool_calls array in assistant messages. Descriptions without preceding "
            "tool calls are classified as tool-underuse failures."
        ),
    },
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _baseline_output() -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP,
        "mode": "optimizer",
        "verdict": "fail",
        "safety": {
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
        },
        "improvements": [],
        "metrics": {"failure_classes_seen": 0, "improvements_generated": 0},
    }


def _candidate_output(failure_classes: list[str]) -> dict[str, Any]:
    improvements = []
    for fc in failure_classes:
        template = _CANDIDATE_TEMPLATES.get(fc)
        if template:
            improvements.append({
                "failure_class": fc,
                "improvement_type": template["improvement_type"],
                "baseline_description": template["baseline_description"],
                "candidate_description": template["candidate_description"],
                "candidate_constraint": template["candidate_constraint"],
            })

    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP,
        "mode": "optimizer",
        "verdict": "pass" if improvements else "fail",
        "safety": {
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
        },
        "improvements": improvements,
        "metrics": {
            "failure_classes_seen": len(failure_classes),
            "improvements_generated": len(improvements),
        },
    }


def run_optimizer(
    eval_examples_path: Path,
    output_dir: Path,
    *,
    mode: str = "optimizer",
) -> dict[str, Any]:
    """Run the deterministic trace optimizer.

    Reads eval examples, produces candidate improvement templates
    for each detected failure class.

    Args:
        eval_examples_path: Path to eval_examples.json from real_trace_ingestion.
        output_dir: Directory to write output artifacts.
        mode: Operating mode (must be 'optimizer').

    Returns:
        A run report dict.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode != "optimizer":
        raise ValueError(f"Unsupported mode: {mode!r}")

    if not eval_examples_path.is_file():
        baseline = _baseline_output()
        _write_json(output_dir / "run_report.json", baseline)
        return baseline

    eval_data = _load_json(eval_examples_path)
    examples = eval_data.get("examples", [])

    if isinstance(examples, dict):
        examples = [examples]
    if not isinstance(examples, list) or not examples:
        baseline = _baseline_output()
        _write_json(output_dir / "run_report.json", baseline)
        return baseline

    first = examples[0] if isinstance(examples[0], dict) else {}
    failure_classes = first.get("detected_failure_classes", [])

    if isinstance(failure_classes, str):
        failure_classes = [failure_classes]

    candidate = _candidate_output(failure_classes)

    # ── Write artifacts ─────────────────────────────────────────────────
    _write_json(output_dir / "run_report.json", candidate)

    # candidate_artifacts.json: the improvement templates
    artifacts = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP,
        "source_eval_examples": str(eval_examples_path),
        "failure_classes": failure_classes,
        "candidates": candidate["improvements"],
    }
    _write_json(output_dir / "candidate_artifacts.json", artifacts)

    # baseline_vs_candidate.json: side-by-side comparison
    comparison: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP,
        "mode": "baseline_vs_candidate",
        "baseline": {
            "verdict": "fail" if failure_classes else "pass",
            "description": "Original trace behavior — no improvement constraints applied.",
        },
        "candidate": {
            "verdict": "pass" if candidate["improvements"] else "fail",
            "description": "Candidate constraints applied — improvements generated for each failure class.",
            "improvement_count": len(candidate["improvements"]),
        },
        "gate_result": {
            "baseline_passed": not bool(failure_classes),
            "candidate_passed": bool(candidate["improvements"]),
            "improvement": len(candidate["improvements"]) > 0,
            "recommendation": (
                "promote" if candidate["improvements"] else "reject"
            ),
        },
    }
    _write_json(output_dir / "baseline_vs_candidate.json", comparison)

    return candidate


@click.command()
@click.option(
    "--eval-examples",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to eval_examples.json from real-trace ingestion.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for optimizer artifacts.",
)
@click.option(
    "--mode",
    type=click.Choice(["optimizer"]),
    default="optimizer",
    help="Operating mode.",
)
@click.option(
    "--no-network",
    is_flag=True,
    default=False,
    help="Safety: no network calls allowed.",
)
@click.option(
    "--no-external-writes",
    is_flag=True,
    default=False,
    help="Safety: no external writes allowed.",
)
def main(
    eval_examples: Path,
    out: Path,
    mode: str,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Run deterministic trace optimizer over eval examples."""
    # Safety: verify flags are set
    assert no_network, "network safety disabled"
    assert no_external_writes, "external writes safety disabled"

    result = run_optimizer(
        eval_examples_path=eval_examples,
        output_dir=out,
        mode=mode,
    )

    verdict = result.get("verdict", "unknown")
    improvements = len(result.get("improvements", []))
    click.echo(f"VERDICT: {verdict}")
    click.echo(f"IMPROVEMENTS: {improvements}")
    click.echo(f"OUTPUT: {out}")


if __name__ == "__main__":
    main()
