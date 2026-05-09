"""Tests for benchmark promotion gate."""

import json

from click.testing import CliRunner

from evolution.core.benchmark_gate import BenchmarkThresholds, evaluate_report, main


def _report(**overrides):
    data = {
        "skill_name": "demo-skill",
        "baseline_score": 0.50,
        "evolved_score": 0.62,
        "improvement": 0.12,
        "baseline_size": 1000,
        "evolved_size": 1100,
        "constraints_passed": True,
    }
    data.update(overrides)
    return data


def test_gate_passes_when_required_metrics_clear_thresholds():
    result = evaluate_report(_report(), BenchmarkThresholds(min_holdout_improvement=0.05))

    assert result.passed is True
    assert result.failures == []
    assert result.checks["holdout_improvement"]["passed"] is True


def test_gate_fails_closed_when_required_field_is_missing():
    report = _report()
    del report["constraints_passed"]

    result = evaluate_report(report, BenchmarkThresholds())

    assert result.passed is False
    assert "missing required report field: constraints_passed" in result.failures


def test_gate_fails_when_constraints_did_not_pass():
    result = evaluate_report(_report(constraints_passed=False), BenchmarkThresholds())

    assert result.passed is False
    assert "constraints_passed is not true" in result.failures


def test_gate_fails_when_holdout_improvement_below_override():
    result = evaluate_report(_report(improvement=0.01), BenchmarkThresholds(min_holdout_improvement=0.05))

    assert result.passed is False
    assert "holdout improvement 0.0100 is below minimum 0.0500" in result.failures


def test_gate_fails_when_artifact_growth_exceeds_limit():
    result = evaluate_report(_report(evolved_size=1400), BenchmarkThresholds(max_artifact_growth=0.20))

    assert result.passed is False
    assert "artifact growth 0.4000 exceeds maximum 0.2000" in result.failures


def test_cli_exits_nonzero_for_failing_report_and_prints_json(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report(improvement=-0.01)))

    result = CliRunner().invoke(
        main,
        ["--report", str(report_path), "--min-holdout-improvement", "0.0"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["passed"] is False
    assert "holdout improvement -0.0100 is below minimum 0.0000" in payload["failures"]


def test_cli_threshold_override_allows_growth(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report(evolved_size=1300)))

    result = CliRunner().invoke(
        main,
        ["--report", str(report_path), "--max-artifact-growth", "0.35"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["passed"] is True
