"""Machine-readable evolution run reports for promotion review."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evolution.core.constraints import ConstraintResult


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify_target(target_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", target_name.strip()).strip("-")
    return slug or "target"


def _constraint_to_dict(result: ConstraintResult) -> dict[str, Any]:
    return asdict(result)


def _write_diff(
    baseline_artifact: str,
    optimized_artifact: str,
    diff_path: Path,
) -> None:
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff = difflib.unified_diff(
        baseline_artifact.splitlines(keepends=True),
        optimized_artifact.splitlines(keepends=True),
        fromfile="baseline",
        tofile="optimized",
    )
    diff_path.write_text("".join(diff))


def build_run_report(
    *,
    target_name: str,
    artifact_type: str,
    baseline_artifact: str,
    optimized_artifact: str,
    dataset_source: str,
    split_counts: dict[str, int],
    optimizer_model: str,
    eval_model: str,
    baseline_score: float | None,
    evolved_score: float | None,
    constraints: list[ConstraintResult],
    elapsed_seconds: float,
    output_dir: Path,
    diff_path: Path,
    timestamp: str,
    cost_estimate: dict[str, Any] | None = None,
    latency_estimate: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a sanitized, machine-readable report for one evolution run."""
    improvement = (
        evolved_score - baseline_score
        if baseline_score is not None and evolved_score is not None
        else None
    )
    constraint_results = [_constraint_to_dict(result) for result in constraints]
    report: dict[str, Any] = {
        "timestamp": timestamp,
        "target_name": target_name,
        "artifact_type": artifact_type,
        "baseline_hash": _sha256_text(baseline_artifact),
        "optimized_hash": _sha256_text(optimized_artifact),
        "baseline_size": len(baseline_artifact),
        "optimized_size": len(optimized_artifact),
        # Compatibility aliases for benchmark gates that expect evolved_* fields.
        "evolved_hash": _sha256_text(optimized_artifact),
        "evolved_size": len(optimized_artifact),
        "dataset_source": dataset_source,
        "split_counts": dict(split_counts),
        "train_examples": split_counts.get("train", 0),
        "val_examples": split_counts.get("val", 0),
        "holdout_examples": split_counts.get("holdout", 0),
        "optimizer_model": optimizer_model,
        "eval_model": eval_model,
        "baseline_score": baseline_score,
        "evolved_score": evolved_score,
        "improvement": improvement,
        "holdout_score_delta": improvement,
        "constraint_results": constraint_results,
        "constraints_passed": all(result.passed for result in constraints),
        "elapsed_seconds": elapsed_seconds,
        "cost_estimate": cost_estimate,
        "latency_estimate": latency_estimate,
        "output_dir": str(output_dir),
        "diff_path": str(diff_path),
    }
    if extra:
        report.update(extra)
    return report


def write_run_report(
    *,
    report_dir: Path,
    target_name: str,
    artifact_type: str,
    baseline_artifact: str,
    optimized_artifact: str,
    dataset_source: str,
    split_counts: dict[str, int],
    optimizer_model: str,
    eval_model: str,
    baseline_score: float | None,
    evolved_score: float | None,
    constraints: list[ConstraintResult],
    elapsed_seconds: float,
    output_dir: Path,
    diff_path: Path,
    timestamp: str,
    cost_estimate: dict[str, Any] | None = None,
    latency_estimate: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write the run report and artifact diff, returning the report path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_diff(baseline_artifact, optimized_artifact, diff_path)
    report_path = report_dir / f"{timestamp}-{_slugify_target(target_name)}.json"
    report = build_run_report(
        target_name=target_name,
        artifact_type=artifact_type,
        baseline_artifact=baseline_artifact,
        optimized_artifact=optimized_artifact,
        dataset_source=dataset_source,
        split_counts=split_counts,
        optimizer_model=optimizer_model,
        eval_model=eval_model,
        baseline_score=baseline_score,
        evolved_score=evolved_score,
        constraints=constraints,
        elapsed_seconds=elapsed_seconds,
        output_dir=output_dir,
        diff_path=diff_path,
        timestamp=timestamp,
        cost_estimate=cost_estimate,
        latency_estimate=latency_estimate,
        extra=extra,
    )
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report_path
