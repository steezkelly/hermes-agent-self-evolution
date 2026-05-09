"""Tests for the Foundry pipeline runner.

Verifies fixture and real-trace orchestration, verdict aggregation, action-item
aggregation, baseline-vs-candidate gating, and fail-closed CLI safety flags.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner


FIXTURE_RUNS = [
    "action_routing_demo",
    "session_import_demo",
    "tool_underuse_demo",
    "skill_drift_demo",
]


def _write_trace(path: Path) -> Path:
    long_tool_miss = (
        "To check if Docker is running, you should run `systemctl status docker`. "
        "Then you can list containers with `docker ps`. You should also verify "
        "the docker socket is accessible at /var/run/docker.sock. Check the "
        "permissions and make sure your user is in the docker group. "
        "Additionally, you could examine the Docker daemon configuration."
    )
    path.write_text(
        "\n".join(
            [
                json.dumps({"role": "session_meta", "session_id": "pipeline-real-trace"}),
                json.dumps({"role": "user", "content": "Check if Docker is running."}),
                json.dumps({"role": "assistant", "content": long_tool_miss}),
            ]
        )
        + "\n"
    )
    return path


def test_baseline_pipeline_output_is_empty_and_fails_eval():
    from evolution.core.pipeline_runner import _baseline_pipeline_output, evaluate_pipeline_run

    baseline = _baseline_pipeline_output()
    evaluation = evaluate_pipeline_run(baseline, expected_run_count=4)

    assert baseline["reports"] == []
    assert baseline["action_items"] == []
    assert evaluation["passed"] is False
    assert any("no reports" in failure for failure in evaluation["failures"])


def test_fixture_mode_runs_all_four_fixture_demos(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    result = run_pipeline(tmp_path, mode="fixture")

    assert result["verdict"] == "pass"
    assert result["mode"] == "fixture"
    assert [report["name"] for report in result["reports"]] == FIXTURE_RUNS
    assert len(result["reports"]) == 4


def test_fixture_mode_writes_four_child_run_reports(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    result = run_pipeline(tmp_path, mode="fixture")

    for report in result["reports"]:
        path = Path(report["run_report"])
        assert path.name == "run_report.json"
        assert path.exists()
        assert json.loads(path.read_text())["verdict"] == "pass"


def test_fixture_mode_pipeline_run_json_contains_verdict_aggregation(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    run_pipeline(tmp_path, mode="fixture")
    pipeline_run = json.loads((tmp_path / "pipeline_run.json").read_text())

    assert pipeline_run["schema_version"] == 1
    assert pipeline_run["mode"] == "fixture"
    assert pipeline_run["metrics"]["reports_collected"] == 4
    assert pipeline_run["metrics"]["passed_reports"] == 4
    assert pipeline_run["metrics"]["failed_reports"] == 0
    assert pipeline_run["verdict"] == "pass"


def test_fixture_mode_does_not_emit_action_items(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    result = run_pipeline(tmp_path, mode="fixture")

    assert result["action_items"] == []
    assert result["metrics"]["action_items_aggregated"] == 0


def test_fixture_mode_report_paths_are_absolute(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    result = run_pipeline(tmp_path, mode="fixture")

    assert all(Path(report["run_report"]).is_absolute() for report in result["reports"])
    assert all(Path(report["run_report"]).exists() for report in result["reports"])


def test_real_trace_mode_requires_trace(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    result = run_pipeline(tmp_path, mode="real_trace")

    assert result["verdict"] == "fail"
    assert result["candidate"]["passed"] is False
    assert any("--trace" in failure for failure in result["candidate"]["failures"])


def test_real_trace_mode_runs_ingestion_then_attention_bridge(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    trace = _write_trace(tmp_path / "session.jsonl")
    result = run_pipeline(tmp_path / "out", mode="real_trace", trace_path=trace)

    assert result["verdict"] == "pass"
    assert [report["name"] for report in result["reports"]] == [
        "real_trace_ingestion",
        "attention_router_bridge",
    ]
    assert len(result["reports"]) == 2


def test_real_trace_mode_produces_full_chain_artifacts(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    trace = _write_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    run_pipeline(out, mode="real_trace", trace_path=trace)

    assert (out / "real_trace_ingestion" / "run_report.json").exists()
    assert (out / "real_trace_ingestion" / "eval_examples.json").exists()
    assert (out / "attention_router_bridge" / "run_report.json").exists()
    assert (out / "attention_router_bridge" / "action_queue.json").exists()
    assert (out / "pipeline_run.json").exists()


def test_real_trace_mode_aggregates_attention_router_action_items(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    trace = _write_trace(tmp_path / "session.jsonl")
    result = run_pipeline(tmp_path / "out", mode="real_trace", trace_path=trace)

    assert result["action_items"]
    assert result["metrics"]["action_items_aggregated"] == len(result["action_items"])
    assert all(item["bucket"] in {"needsSteve", "autonomous", "blocked", "stale"} for item in result["action_items"])
    assert all(item["next_prompt"].startswith("Work in `/home/steve/repos/steezkelly-hermes-agent-self-evolution`") for item in result["action_items"])


def test_real_trace_pipeline_run_json_embeds_action_items(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    trace = _write_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    run_pipeline(out, mode="real_trace", trace_path=trace)
    pipeline_run = json.loads((out / "pipeline_run.json").read_text())

    assert pipeline_run["action_items"]
    assert pipeline_run["metrics"]["action_items_aggregated"] == len(pipeline_run["action_items"])


def test_evaluate_pipeline_run_rejects_missing_expected_report_count():
    from evolution.core.pipeline_runner import evaluate_pipeline_run

    evaluation = evaluate_pipeline_run(
        {"reports": [{"name": "one", "verdict": "pass"}], "action_items": []},
        expected_run_count=4,
    )

    assert evaluation["passed"] is False
    assert any("expected 4 reports" in failure for failure in evaluation["failures"])


def test_evaluate_pipeline_run_rejects_failed_child_verdict():
    from evolution.core.pipeline_runner import evaluate_pipeline_run

    evaluation = evaluate_pipeline_run(
        {
            "reports": [
                {"name": "one", "verdict": "pass"},
                {"name": "two", "verdict": "fail"},
            ],
            "action_items": [],
        },
        expected_run_count=2,
    )

    assert evaluation["passed"] is False
    assert any("failed child report" in failure for failure in evaluation["failures"])


def test_pipeline_run_json_has_safety_flags(tmp_path):
    from evolution.core.pipeline_runner import run_pipeline

    run_pipeline(tmp_path, mode="fixture")
    pipeline_run = json.loads((tmp_path / "pipeline_run.json").read_text())

    assert pipeline_run["safety"] == {
        "mode": "fixture",
        "network_allowed": False,
        "external_writes_allowed": False,
        "github_writes_allowed": False,
        "production_mutation_allowed": False,
    }
    assert pipeline_run["external_writes_allowed"] is False
    assert pipeline_run["network_allowed"] is False


def test_cli_fixture_mode_writes_pipeline_run_without_stdout_noise(tmp_path):
    from evolution.core.pipeline_runner import main

    result = CliRunner().invoke(
        main,
        [
            "--out",
            str(tmp_path),
            "--mode",
            "fixture",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert (tmp_path / "pipeline_run.json").exists()


def test_cli_real_trace_mode_accepts_trace_and_writes_pipeline_run(tmp_path):
    from evolution.core.pipeline_runner import main

    trace = _write_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    result = CliRunner().invoke(
        main,
        [
            "--out",
            str(out),
            "--mode",
            "real_trace",
            "--trace",
            str(trace),
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out / "pipeline_run.json").exists()
    assert json.loads((out / "pipeline_run.json").read_text())["action_items"]


def test_cli_fails_closed_without_safety_flags(tmp_path):
    from evolution.core.pipeline_runner import main

    missing_network_flag = CliRunner().invoke(
        main,
        ["--out", str(tmp_path), "--mode", "fixture", "--no-external-writes"],
    )
    assert missing_network_flag.exit_code != 0
    assert "--no-network is required" in missing_network_flag.output

    missing_external_flag = CliRunner().invoke(
        main,
        ["--out", str(tmp_path), "--mode", "fixture", "--no-network"],
    )
    assert missing_external_flag.exit_code != 0
    assert "--no-external-writes is required" in missing_external_flag.output


def test_cli_real_trace_fails_closed_without_trace(tmp_path):
    from evolution.core.pipeline_runner import main

    result = CliRunner().invoke(
        main,
        [
            "--out",
            str(tmp_path),
            "--mode",
            "real_trace",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code != 0
    assert "--trace is required" in result.output
