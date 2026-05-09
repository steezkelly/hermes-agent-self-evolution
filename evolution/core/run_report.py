"""Machine-readable evolution run reports for promotion review."""

from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from evolution.core.constraints import ConstraintResult
from evolution.core.dataset_builder import EvalDataset


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _constraint_to_dict(result: ConstraintResult) -> dict:
    if hasattr(result, "__dataclass_fields__"):
        return asdict(result)
    return dict(result)


def _source_counts(dataset: EvalDataset) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ex in dataset.all_examples:
        counts[ex.source] = counts.get(ex.source, 0) + 1
    return counts


def write_run_report(
    *,
    target_name: str,
    target_type: str,
    baseline_path: Path,
    optimized_path: Path,
    dataset: EvalDataset,
    optimizer_model: str,
    eval_model: str,
    optimizer_type: str,
    constraints: Iterable[ConstraintResult],
    baseline_score: float,
    optimized_score: float,
    elapsed_seconds: float,
    report_dir: Path = Path("reports/runs"),
    cost_estimate: Optional[dict] = None,
    dry_run: bool = False,
) -> Path:
    """Write a promotion-ready run report and sidecar diff file."""
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_target = target_name.replace("/", "-").replace(" ", "-")
    report_path = report_dir / f"{timestamp}-{safe_target}.json"
    diff_path = report_dir / f"{timestamp}-{safe_target}.diff"

    baseline_text = baseline_path.read_text()
    optimized_text = optimized_path.read_text()
    diff_text = "".join(difflib.unified_diff(
        baseline_text.splitlines(keepends=True),
        optimized_text.splitlines(keepends=True),
        fromfile=str(baseline_path),
        tofile=str(optimized_path),
    ))
    diff_path.write_text(diff_text)

    constraint_results = [_constraint_to_dict(c) for c in constraints]
    all_constraints_passed = all(c.get("passed", False) for c in constraint_results)

    report = {
        "schema_version": 1,
        "timestamp": timestamp,
        "target": {"type": target_type, "name": target_name},
        "baseline": {
            "path": str(baseline_path),
            "sha256": _sha256(baseline_path),
            "size_bytes": baseline_path.stat().st_size,
        },
        "optimized": {
            "path": str(optimized_path),
            "sha256": _sha256(optimized_path),
            "size_bytes": optimized_path.stat().st_size,
        },
        "dataset": {
            "splits": {
                "train": len(dataset.train),
                "val": len(dataset.val),
                "holdout": len(dataset.holdout),
            },
            "source_counts": _source_counts(dataset),
        },
        "models": {
            "optimizer_model": optimizer_model,
            "eval_model": eval_model,
            "optimizer_type": optimizer_type,
        },
        "constraints": {
            "all_passed": all_constraints_passed,
            "results": constraint_results,
        },
        "scores": {
            "baseline_holdout": baseline_score,
            "optimized_holdout": optimized_score,
            "holdout_delta": optimized_score - baseline_score,
        },
        "economics": {
            "elapsed_seconds": elapsed_seconds,
            "cost_estimate": cost_estimate,
        },
        "diff": {
            "path": str(diff_path),
        },
        "benchmark_gate": None,
        "safety": {
            "dry_run": dry_run,
            "pushed": False,
            "opened_pr": False,
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report_path
