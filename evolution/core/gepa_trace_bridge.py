"""Bridge from trace-optimizer templates to GEPA/DSPy-compatible eval datasets.

Reads ``candidate_artifacts.json`` from the trace_optimizer stage and
produces golden eval datasets (JSONL) that GEPA dispatch can consume.

Each candidate constraint becomes a mini-skill body. The dataset contains
eval examples that test whether an optimized agent actually follows the
constraint. This module does NOT invoke LLMs — it only prepares data and
generates the GEPA invocation manifest.

Safety: local only, no network calls, no API keys, deterministic output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from evolution.core.dataset_builder import EvalDataset, EvalExample

_FIXED_TIMESTAMP = "1970-01-01T00:00:00Z"
_SCHEMA_VERSION = 1

# ── Eval example generators per failure class ──────────────────────────

_LONG_BRIEFING_EXAMPLES: list[dict[str, str]] = [
    {
        "task_input": "What config options are available for Hermes Agent?",
        "expected_behavior": (
            "RESPONSE: owner=hermes-runtime, evidence_paths=[/etc/hermes/config.yaml], "
            "next_prompt='hermes config list', expires_at=2026-06-01T00:00:00Z, "
            "title='Show Hermes config options', bucket=autonomous. "
            "Output must be a single action item, under 200 chars total."
        ),
        "difficulty": "medium",
        "category": "delivery",
    },
    {
        "task_input": "Summarize the current system state.",
        "expected_behavior": (
            "RESPONSE: owner=hermes-runtime, evidence_paths=[/proc/cpuinfo, /proc/meminfo], "
            "next_prompt='hermes status', expires_at=2026-06-01T00:00:00Z, "
            "title='Report system state in one line', bucket=autonomous."
        ),
        "difficulty": "easy",
        "category": "delivery",
    },
]

_RAW_TRACE_EXAMPLES: list[dict[str, str]] = [
    {
        "task_input": "Extract structured eval examples from session 20260501.",
        "expected_behavior": (
            "For each assistant message >200 chars: extract task_input (user query), "
            "expected_behavior (what good output looks like), difficulty (easy/medium/hard), "
            "category (tool-use/delivery/planning/briefing). Store as JSONL with "
            "evidence_path pointing to source message index."
        ),
        "difficulty": "medium",
        "category": "tool-use",
    },
    {
        "task_input": "Convert raw conversation into eval training data.",
        "expected_behavior": (
            "Parse every user→assistant exchange. Extract: task_input from user message, "
            "expected_behavior inferred from assistant output + tool calls. "
            "Tag difficulty based on tool count (0=easy, 1-3=medium, 4+=hard). "
            "Output as eval_examples.json with examples array."
        ),
        "difficulty": "hard",
        "category": "tool-use",
    },
]

_TOOL_UNDERUSE_EXAMPLES: list[dict[str, str]] = [
    {
        "task_input": "Check if the config file exists and show its contents.",
        "expected_behavior": (
            "DO NOT describe. First call: terminal('ls /etc/hermes/config.yaml'). "
            "Then call: read_file('/etc/hermes/config.yaml'). "
            "Only after tool results, state findings. "
            "No description longer than 200 chars without preceding tool call."
        ),
        "difficulty": "easy",
        "category": "tool-use",
    },
    {
        "task_input": "Find all Python files that import requests and count them.",
        "expected_behavior": (
            "DO NOT describe. First call: search_files(pattern='import requests',"
            " target='content', file_glob='*.py'). Then call: search_files("
            "pattern='import requests', target='content', output_mode='count', "
            "file_glob='*.py'). Only after results, report count. "
            "No description longer than 200 chars without preceding tool call."
        ),
        "difficulty": "medium",
        "category": "tool-use",
    },
]

_CLASS_TO_EXAMPLES: dict[str, list[dict[str, str]]] = {
    "long_briefing_instead_of_concise_action_queue": _LONG_BRIEFING_EXAMPLES,
    "raw_session_trace_without_structured_eval_example": _RAW_TRACE_EXAMPLES,
    "agent_describes_instead_of_calls_tools": _TOOL_UNDERUSE_EXAMPLES,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _build_dataset_for_class(
    failure_class: str, constraint: str, output_dir: Path
) -> tuple[Path, int]:
    """Build a golden eval dataset for one failure class.

    Returns (dataset_path, example_count).
    """
    dataset_dir = output_dir / failure_class
    dataset_dir.mkdir(parents=True, exist_ok=True)

    raw_examples = _CLASS_TO_EXAMPLES.get(failure_class, [])
    if not raw_examples:
        raw_examples = [
            {
                "task_input": f"Follow this constraint: {constraint[:120]}",
                "expected_behavior": constraint,
                "difficulty": "medium",
                "category": "general",
            }
        ]

    examples = [
        EvalExample(
            task_input=ex["task_input"],
            expected_behavior=ex["expected_behavior"],
            difficulty=ex.get("difficulty", "medium"),
            category=ex.get("category", "general"),
            source="golden",
        )
        for ex in raw_examples
    ]

    # Save as train/val/holdout splits
    n = len(examples)
    n_train = max(1, n // 2)
    n_val = max(1, (n - n_train) // 2)

    dataset = EvalDataset(
        train=examples[:n_train],
        val=examples[n_train : n_train + n_val],
        holdout=examples[n_train + n_val :],
    )
    dataset.save(dataset_dir)

    return dataset_dir, n


def _build_gepa_manifest(
    datasets: list[dict[str, Any]],
    optimizer_model: str,
    eval_model: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Build manifest of GEPA-ready invocations."""
    jobs = []
    for ds in datasets:
        jobs.append({
            "failure_class": ds["failure_class"],
            "improvement_type": ds["improvement_type"],
            "dataset_path": ds["dataset_path"],
            "example_count": ds["example_count"],
            "command": (
                f"python -m evolution.core.gepa_v2_dispatch "
                f"--skill-name '{ds['failure_class']}' "
                f"--iterations 5 "
                f"--eval-source golden "
                f"--dataset-path '{ds['dataset_path']}' "
                f"--optimizer-model '{optimizer_model}' "
                f"--eval-model '{eval_model}'"
            ),
        })

    manifest = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": _FIXED_TIMESTAMP,
        "optimizer_model": optimizer_model,
        "eval_model": eval_model,
        "total_datasets": len(jobs),
        "datasets": jobs,
    }

    _write_json(output_dir / "gepa_manifest.json", manifest)
    return manifest


def run_gepa_bridge(
    candidate_artifacts_path: Path,
    output_dir: Path,
    *,
    optimizer_model: str = "minimax/minimax-m2.7",
    eval_model: str = "minimax/minimax-m2.7",
) -> dict[str, Any]:
    """Run the GEPA dataset bridge.

    Args:
        candidate_artifacts_path: Path to candidate_artifacts.json from optimizer.
        output_dir: Directory to write datasets + manifest.
        optimizer_model: Model to use for optimization (injected into manifest).
        eval_model: Model to use for evaluation (injected into manifest).

    Returns:
        Run report dict.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if not candidate_artifacts_path.is_file():
        baseline = {
            "schema_version": _SCHEMA_VERSION,
            "verdict": "fail",
            "reason": "candidate_artifacts.json not found",
            "datasets_built": 0,
            "safety": {
                "network_allowed": False,
                "external_writes_allowed": False,
                "github_writes_allowed": False,
            },
        }
        _write_json(output_dir / "run_report.json", baseline)
        return baseline

    artifacts = _load_json(candidate_artifacts_path)
    candidates = artifacts.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        baseline = {
            "schema_version": _SCHEMA_VERSION,
            "verdict": "fail",
            "reason": "no candidates in artifacts",
            "datasets_built": 0,
            "safety": {
                "network_allowed": False,
                "external_writes_allowed": False,
                "github_writes_allowed": False,
            },
        }
        _write_json(output_dir / "run_report.json", baseline)
        return baseline

    datasets: list[dict[str, Any]] = []
    for candidate in candidates:
        fc = candidate.get("failure_class", "")
        constraint = candidate.get("candidate_constraint", "")
        imp_type = candidate.get("improvement_type", "unknown")

        ds_path, count = _build_dataset_for_class(fc, constraint, output_dir)

        datasets.append({
            "failure_class": fc,
            "improvement_type": imp_type,
            "dataset_path": str(ds_path.resolve()),
            "example_count": count,
        })

    manifest = _build_gepa_manifest(
        datasets, optimizer_model, eval_model, output_dir
    )

    report = {
        "schema_version": _SCHEMA_VERSION,
        "verdict": "pass" if datasets else "fail",
        "mode": "gepa_bridge",
        "datasets_built": len(datasets),
        "total_examples": sum(d["example_count"] for d in datasets),
        "manifest_path": str((output_dir / "gepa_manifest.json").resolve()),
        "safety": {
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
        },
    }
    _write_json(output_dir / "run_report.json", report)

    return report


@click.command()
@click.option(
    "--candidate-artifacts",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to candidate_artifacts.json from trace-optimizer.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for GEPA datasets.",
)
@click.option(
    "--optimizer-model",
    type=str,
    default="minimax/minimax-m2.7",
    help="Model name for optimization.",
)
@click.option(
    "--eval-model",
    type=str,
    default="minimax/minimax-m2.7",
    help="Model name for evaluation.",
)
@click.option(
    "--no-network",
    is_flag=True,
    default=True,
    help="Safety: no network calls allowed.",
)
@click.option(
    "--no-external-writes",
    is_flag=True,
    default=True,
    help="Safety: no external writes allowed.",
)
def main(
    candidate_artifacts: Path,
    out: Path,
    optimizer_model: str,
    eval_model: str,
    no_network: bool,
    no_external_writes: bool,
) -> None:
    """Bridge optimizer templates into GEPA-ready eval datasets."""
    # Safety flags are asserted at chain level; this module is deterministic
    # and makes no network calls regardless of flag state.

    result = run_gepa_bridge(
        candidate_artifacts_path=candidate_artifacts,
        output_dir=out,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
    )

    click.echo(f"VERDICT: {result['verdict']}")
    click.echo(f"DATASETS: {result['datasets_built']}")
    click.echo(f"EXAMPLES: {result['total_examples']}")
    click.echo(f"OUTPUT: {out}")


if __name__ == "__main__":
    main()
