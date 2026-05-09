"""Tests for local-first PR body generation from run reports."""

import json

from click.testing import CliRunner

from evolution.core.pr_builder import build_pr_body, build_pr_title, main, prepare_pr


def _report(**overrides):
    data = {
        "target_name": "github-code-review",
        "artifact_type": "skill",
        "baseline_score": 0.4,
        "evolved_score": 0.55,
        "improvement": 0.15,
        "baseline_size": 1000,
        "evolved_size": 1120,
        "baseline_hash": "abc123",
        "evolved_hash": "def456",
        "dataset_source": "sessiondb",
        "split_counts": {"train": 4, "val": 2, "holdout": 2},
        "optimizer_model": "optimizer/model",
        "eval_model": "eval/model",
        "constraints_passed": True,
        "constraint_results": [
            {"constraint_name": "size_limit", "passed": True, "message": "Size OK"},
            {"constraint_name": "growth_limit", "passed": True, "message": "Growth OK"},
        ],
        "diff_path": "output/github-code-review/run/skill.diff",
        "output_dir": "output/github-code-review/run",
        "report_path": "reports/runs/20260509-github-code-review.json",
        "benchmark_gate": {"passed": True, "failures": []},
    }
    data.update(overrides)
    return data


def test_build_pr_title_is_deterministic_from_target():
    assert build_pr_title(_report()) == "chore: promote evolved github-code-review skill"


def test_build_pr_body_contains_required_review_sections():
    body = build_pr_body(_report())

    assert "## Summary" in body
    assert "github-code-review" in body
    assert "## Before / After Metrics" in body
    assert "0.400" in body
    assert "0.550" in body
    assert "+0.150" in body
    assert "## Constraints" in body
    assert "size_limit" in body
    assert "## Benchmark Gate" in body
    assert "Passed: True" in body
    assert "## Risk Notes" in body
    assert "## Rollback" in body
    assert "git revert" in body
    assert "## Test Plan" in body
    assert "output/github-code-review/run/skill.diff" in body


def test_prepare_pr_does_not_run_remote_commands_by_default(tmp_path):
    commands = []

    def fake_runner(command):
        commands.append(command)

    result = prepare_pr(
        _report(),
        dry_run=False,
        push=False,
        open_pr=False,
        runner=fake_runner,
    )

    assert result["pushed"] is False
    assert result["opened_pr"] is False
    assert commands == []


def test_prepare_pr_only_pushes_or_opens_behind_explicit_flags():
    commands = []

    def fake_runner(command):
        commands.append(command)

    prepare_pr(
        _report(),
        dry_run=False,
        push=True,
        open_pr=True,
        runner=fake_runner,
    )

    assert any(command[:3] == ["git", "push", "-u"] for command in commands)
    assert any(command[:3] == ["gh", "pr", "create"] for command in commands)


def test_cli_dry_run_prints_deterministic_title_and_body(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_report()))

    result = CliRunner().invoke(main, ["--report", str(report_path), "--dry-run"])

    assert result.exit_code == 0
    assert "PR Title: chore: promote evolved github-code-review skill" in result.output
    assert "## Summary" in result.output
    assert "## Test Plan" in result.output
    assert "git push" not in result.output
