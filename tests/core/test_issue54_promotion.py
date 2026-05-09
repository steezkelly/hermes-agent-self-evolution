"""Issue #54: auditable promotion artifacts, benchmark gates, and PR bodies."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from evolution.core.constraints import ConstraintResult
from evolution.core.dataset_builder import EvalDataset, EvalExample


def _write_artifacts(tmp_path: Path) -> tuple[Path, Path, EvalDataset]:
    baseline = tmp_path / "baseline.md"
    optimized = tmp_path / "optimized.md"
    baseline.write_text("---\nname: demo\ndescription: Demo\n---\n\n# Demo\n\nDo the old thing.\n")
    optimized.write_text("---\nname: demo\ndescription: Demo\n---\n\n# Demo\n\nDo the improved thing.\n")
    dataset = EvalDataset(
        train=[EvalExample("train task", "train expected", source="golden")],
        val=[EvalExample("val task", "val expected", source="golden")],
        holdout=[EvalExample("holdout task", "holdout expected", source="golden")],
    )
    return baseline, optimized, dataset


def test_run_report_contains_hashes_split_counts_constraints_and_diff_path(tmp_path):
    from evolution.core.run_report import write_run_report

    baseline, optimized, dataset = _write_artifacts(tmp_path)
    report_path = write_run_report(
        target_name="demo",
        target_type="skill",
        baseline_path=baseline,
        optimized_path=optimized,
        dataset=dataset,
        optimizer_model="optimizer-model",
        eval_model="eval-model",
        optimizer_type="GEPA",
        constraints=[ConstraintResult(True, "size_limit", "ok")],
        baseline_score=0.4,
        optimized_score=0.7,
        elapsed_seconds=12.5,
        report_dir=tmp_path / "reports" / "runs",
    )

    report = json.loads(report_path.read_text())
    assert report_path.parent == tmp_path / "reports" / "runs"
    assert report["target"] == {"type": "skill", "name": "demo"}
    assert report["baseline"]["sha256"]
    assert report["optimized"]["sha256"]
    assert report["baseline"]["size_bytes"] == baseline.stat().st_size
    assert report["optimized"]["size_bytes"] == optimized.stat().st_size
    assert report["scores"]["holdout_delta"] == pytest.approx(0.3)
    assert report["dataset"]["splits"] == {"train": 1, "val": 1, "holdout": 1}
    assert report["dataset"]["source_counts"] == {"golden": 3}
    assert report["models"] == {
        "optimizer_model": "optimizer-model",
        "eval_model": "eval-model",
        "optimizer_type": "GEPA",
    }
    assert report["constraints"]["all_passed"] is True
    assert report["constraints"]["results"][0]["constraint_name"] == "size_limit"
    assert Path(report["diff"]["path"]).exists()
    assert "-Do the old thing." in Path(report["diff"]["path"]).read_text()
    assert "+Do the improved thing." in Path(report["diff"]["path"]).read_text()


def test_benchmark_gate_fails_closed_on_missing_required_fields(tmp_path):
    from evolution.core.benchmark_gate import evaluate_report

    report_path = tmp_path / "bad-report.json"
    report_path.write_text(json.dumps({"target": {"name": "demo"}}))

    result = evaluate_report(report_path)

    assert result.passed is False
    assert any("missing required field" in failure for failure in result.failures)


def test_benchmark_gate_pass_fail_and_cli_exit_codes(tmp_path):
    from evolution.core.benchmark_gate import evaluate_report, main

    report = {
        "target": {"type": "skill", "name": "demo"},
        "baseline": {"size_bytes": 100, "sha256": "a" * 64},
        "optimized": {"size_bytes": 120, "sha256": "b" * 64},
        "scores": {"baseline_holdout": 0.4, "optimized_holdout": 0.55, "holdout_delta": 0.15},
        "constraints": {"all_passed": True, "results": []},
        "economics": {"cost_estimate": {"baseline": 1.0, "optimized": 1.1}},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    passed = evaluate_report(report_path, min_holdout_delta=0.1, max_artifact_growth=0.5)
    assert passed.passed is True

    failed = evaluate_report(report_path, min_holdout_delta=0.2, max_artifact_growth=0.5)
    assert failed.passed is False
    assert any("holdout" in failure for failure in failed.failures)

    runner = CliRunner()
    ok = runner.invoke(main, ["--report", str(report_path), "--min-holdout-delta", "0.1"])
    assert ok.exit_code == 0
    bad = runner.invoke(main, ["--report", str(report_path), "--min-holdout-delta", "0.2"])
    assert bad.exit_code != 0


def test_benchmark_gate_optional_benchmark_command_fails_closed(tmp_path):
    from evolution.core.benchmark_gate import main

    report = {
        "target": {"type": "skill", "name": "demo"},
        "baseline": {"size_bytes": 100, "sha256": "a" * 64},
        "optimized": {"size_bytes": 100, "sha256": "b" * 64},
        "scores": {"baseline_holdout": 0.4, "optimized_holdout": 0.5, "holdout_delta": 0.1},
        "constraints": {"all_passed": True, "results": []},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    result = CliRunner().invoke(
        main,
        ["--report", str(report_path), "--benchmark-command", "python3 -c 'raise SystemExit(3)'"],
    )

    assert result.exit_code != 0
    assert "benchmark command failed" in result.output


def test_benchmark_gate_benchmark_command_timeout_fails_closed(tmp_path):
    from evolution.core.benchmark_gate import main

    report = {
        "target": {"type": "skill", "name": "demo"},
        "baseline": {"size_bytes": 100, "sha256": "a" * 64},
        "optimized": {"size_bytes": 100, "sha256": "b" * 64},
        "scores": {"baseline_holdout": 0.4, "optimized_holdout": 0.5, "holdout_delta": 0.1},
        "constraints": {"all_passed": True, "results": []},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    result = CliRunner().invoke(
        main,
        [
            "--report", str(report_path),
            "--benchmark-command", "python3 -c 'import time; time.sleep(5)'",
            "--benchmark-timeout-seconds", "1",
        ],
    )

    assert result.exit_code != 0
    assert "benchmark command timed out" in result.output


def test_pr_builder_dry_run_is_deterministic_and_does_not_mutate_git(tmp_path, monkeypatch):
    from evolution.core.pr_builder import build_pr_text, main

    report = {
        "target": {"type": "skill", "name": "demo"},
        "scores": {"baseline_holdout": 0.4, "optimized_holdout": 0.7, "holdout_delta": 0.3},
        "constraints": {"all_passed": True, "results": [{"constraint_name": "size_limit", "passed": True, "message": "ok"}]},
        "benchmark_gate": {"passed": True, "failures": [], "warnings": []},
        "diff": {"path": str(tmp_path / "demo.diff")},
        "safety": {"pushed": False, "opened_pr": False},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))

    title, body = build_pr_text(report_path)
    assert title == "Improve demo via self-evolution"
    assert "Holdout delta: +0.300" in body
    assert "Benchmark gate: PASS" in body
    assert "Rollback" in body
    assert "Test plan" in body

    calls = []
    monkeypatch.setattr("evolution.core.pr_builder._run_git", lambda *args, **kwargs: calls.append(args))
    result = CliRunner().invoke(main, ["--report", str(report_path), "--dry-run"])
    assert result.exit_code == 0
    assert "Improve demo via self-evolution" in result.output
    assert calls == []
