"""Tests for evolution run report generation."""

import json

import pytest

from evolution.core.constraints import ConstraintResult
from evolution.core.run_report import build_run_report, write_run_report


def test_build_run_report_contains_promotion_artifact_fields(tmp_path):
    baseline = "# Skill\nold behavior\n"
    evolved = "# Skill\nnew improved behavior\n"
    constraints = [ConstraintResult(True, "size_limit", "Size OK", "details")]

    report = build_run_report(
        target_name="demo-skill",
        artifact_type="skill",
        baseline_artifact=baseline,
        optimized_artifact=evolved,
        dataset_source="golden",
        split_counts={"train": 2, "val": 1, "holdout": 1},
        optimizer_model="openai/gpt-4.1",
        eval_model="openai/gpt-4.1-mini",
        baseline_score=0.4,
        evolved_score=0.7,
        constraints=constraints,
        elapsed_seconds=12.5,
        output_dir=tmp_path / "output" / "demo-skill" / "run",
        diff_path=tmp_path / "output" / "demo-skill" / "run" / "skill.diff",
        timestamp="20260509_010203",
    )

    assert report["target_name"] == "demo-skill"
    assert report["artifact_type"] == "skill"
    assert report["baseline_hash"] != report["optimized_hash"]
    assert report["baseline_size"] == len(baseline)
    assert report["optimized_size"] == len(evolved)
    assert report["evolved_size"] == len(evolved)
    assert report["dataset_source"] == "golden"
    assert report["split_counts"] == {"train": 2, "val": 1, "holdout": 1}
    assert report["train_examples"] == 2
    assert report["val_examples"] == 1
    assert report["holdout_examples"] == 1
    assert report["optimizer_model"] == "openai/gpt-4.1"
    assert report["eval_model"] == "openai/gpt-4.1-mini"
    assert report["baseline_score"] == 0.4
    assert report["evolved_score"] == 0.7
    assert report["improvement"] == pytest.approx(0.3)
    assert report["holdout_score_delta"] == pytest.approx(0.3)
    assert report["constraints_passed"] is True
    assert report["constraint_results"] == [
        {
            "passed": True,
            "constraint_name": "size_limit",
            "message": "Size OK",
            "details": "details",
        }
    ]
    assert report["output_dir"].endswith("output/demo-skill/run")
    assert report["diff_path"].endswith("skill.diff")


def test_build_run_report_allows_failed_run_before_holdout_scores(tmp_path):
    report = build_run_report(
        target_name="demo-skill",
        artifact_type="skill",
        baseline_artifact="baseline",
        optimized_artifact="optimized",
        dataset_source="golden",
        split_counts={"train": 1, "val": 1, "holdout": 1},
        optimizer_model="optimizer/model",
        eval_model="eval/model",
        baseline_score=None,
        evolved_score=None,
        constraints=[ConstraintResult(False, "size_limit", "Too large")],
        elapsed_seconds=2.0,
        output_dir=tmp_path / "output",
        diff_path=tmp_path / "output" / "skill.diff",
        timestamp="20260509_010203",
        extra={"status": "failed_constraints"},
    )

    assert report["baseline_score"] is None
    assert report["evolved_score"] is None
    assert report["improvement"] is None
    assert report["holdout_score_delta"] is None
    assert report["constraints_passed"] is False
    assert report["status"] == "failed_constraints"


def test_write_run_report_writes_machine_readable_report_and_diff(tmp_path):
    baseline = "line one\nold line\n"
    evolved = "line one\nnew line\n"
    report_dir = tmp_path / "reports" / "runs"
    diff_path = tmp_path / "output" / "demo" / "run" / "artifact.diff"

    report_path = write_run_report(
        report_dir=report_dir,
        target_name="demo skill",
        artifact_type="skill",
        baseline_artifact=baseline,
        optimized_artifact=evolved,
        dataset_source="sessiondb",
        split_counts={"train": 1, "val": 1, "holdout": 1},
        optimizer_model="optimizer/model",
        eval_model="eval/model",
        baseline_score=0.5,
        evolved_score=0.6,
        constraints=[ConstraintResult(True, "non_empty", "Non-empty")],
        elapsed_seconds=1.25,
        output_dir=tmp_path / "output" / "demo" / "run",
        diff_path=diff_path,
        timestamp="20260509_010203",
    )

    assert report_path == report_dir / "20260509_010203-demo-skill.json"
    payload = json.loads(report_path.read_text())
    assert payload["target_name"] == "demo skill"
    assert payload["report_path"] == str(report_path)
    assert payload["diff_path"] == str(diff_path)
    assert "-old line" in diff_path.read_text()
    assert "+new line" in diff_path.read_text()
    assert payload["cost_estimate"] is None
    assert payload["latency_estimate"] is None
