"""Tests for the session-end full chain runner.

Verifies real_trace_ingestion -> attention_router_bridge orchestration,
chain_run.json aggregation, baseline-vs-candidate gate, and local-only CLI
safety boundaries.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner


_ALLOWED_BUCKETS = {"needsSteve", "autonomous", "blocked", "stale"}


def _write_tool_underuse_trace(path: Path) -> Path:
    content = (
        "To check if Docker is running, you should run `systemctl status docker`. "
        "Then you can list containers with `docker ps`. You should also verify "
        "the docker socket is accessible at /var/run/docker.sock. Check the "
        "permissions and make sure your user is in the docker group. "
        "Additionally, you could examine the Docker daemon configuration."
    )
    path.write_text(
        "\n".join(
            [
                json.dumps({"role": "session_meta", "session_id": "session-end-chain"}),
                json.dumps({"role": "user", "content": "Check if Docker is running and list containers."}),
                json.dumps({"role": "assistant", "content": content}),
            ]
        )
        + "\n"
    )
    return path


def _write_healthy_observatory_db(path: Path) -> Path:
    from evolution.core.observatory.logger import JudgeAuditLogger

    logger = JudgeAuditLogger(db_path=path)
    for generation in [1, 2, 3]:
        for index, score in enumerate([0.2, 0.5, 0.8]):
            logger.log(
                generation=generation,
                skill_name="session-end-chain",
                model_used="minimax/minimax-m2.7",
                task_id=f"g{generation}-t{index}",
                expected_behavior="evidence-backed action queue",
                actual_behavior="structured action item emitted",
                rubric="score action-router quality",
                raw_score=score,
                token_cost_estimate=0.001,
            )
    return path


def test_baseline_chain_output_is_empty_and_fails_eval():
    from evolution.core.session_end_chain import _baseline_chain_output, evaluate_chain_run

    baseline = _baseline_chain_output()
    evaluation = evaluate_chain_run(baseline)

    assert baseline["ingestion"] == {}
    assert baseline["bridge"] == {}
    assert baseline["action_items"] == []
    assert evaluation["passed"] is False
    assert any("missing ingestion" in failure for failure in evaluation["failures"])


def test_run_session_end_chain_writes_chain_run(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    assert result["verdict"] == "pass"
    assert (tmp_path / "out" / "chain_run.json").exists()


def test_chain_run_contains_ingestion_verdict_and_detected_failures(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    assert result["ingestion"]["verdict"] == "pass"
    assert result["ingestion"]["detected_failure_classes"]
    assert "agent_describes_instead_of_calls_tools" in result["ingestion"]["detected_failure_classes"]
    assert result["ingestion"]["failure_count"] == len(result["ingestion"]["detected_failure_classes"])


def test_chain_run_contains_bridge_verdict_and_action_items(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    assert result["bridge"]["verdict"] == "pass"
    assert result["bridge"]["action_item_count"] == len(result["action_items"])
    assert result["action_items"]


def test_chain_verdict_passes_only_when_ingestion_and_bridge_pass(tmp_path):
    from evolution.core.session_end_chain import evaluate_chain_run, run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")
    assert result["verdict"] == "pass"

    broken = dict(result)
    broken["bridge"] = {**result["bridge"], "verdict": "fail"}
    evaluation = evaluate_chain_run(broken)
    assert evaluation["passed"] is False
    assert any("bridge verdict" in failure for failure in evaluation["failures"])


def test_chain_run_json_matches_return_value(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    result = run_session_end_chain(trace, out)
    chain_run = json.loads((out / "chain_run.json").read_text())

    assert chain_run == result


def test_chain_writes_child_artifacts_in_sequence(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    run_session_end_chain(trace, out)

    assert (out / "real_trace_ingestion" / "run_report.json").exists()
    assert (out / "real_trace_ingestion" / "eval_examples.json").exists()
    assert (out / "attention_router_bridge" / "run_report.json").exists()
    assert (out / "attention_router_bridge" / "action_queue.json").exists()


def test_chain_report_paths_are_absolute_and_existing(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    for section in ["ingestion", "bridge"]:
        path = Path(result[section]["run_report"])
        assert path.is_absolute()
        assert path.exists()


def test_chain_action_items_keep_attention_router_contract(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    for item in result["action_items"]:
        assert item["bucket"] in _ALLOWED_BUCKETS
        assert item["owner"]
        assert item["title"]
        assert 0 < len(item["why"]) <= 380
        assert item["evidence_paths"]
        assert item["next_prompt"].startswith(
            "Work in `/home/steve/repos/steezkelly-hermes-agent-self-evolution`"
        )
        assert item["expires_at"]


def test_chain_metrics_count_failures_and_actions(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    assert result["metrics"]["detected_failure_count"] == result["ingestion"]["failure_count"]
    assert result["metrics"]["action_items_aggregated"] == len(result["action_items"])
    assert result["metrics"]["steps_passed"] == 2
    assert result["metrics"]["steps_failed"] == 0


def test_chain_run_json_has_safety_flags(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = run_session_end_chain(trace, tmp_path / "out")

    assert result["external_writes_allowed"] is False
    assert result["network_allowed"] is False
    assert result["safety"] == {
        "mode": "chain",
        "network_allowed": False,
        "external_writes_allowed": False,
        "github_writes_allowed": False,
        "production_mutation_allowed": False,
    }


def test_evaluate_chain_run_rejects_missing_action_items():
    from evolution.core.session_end_chain import evaluate_chain_run

    evaluation = evaluate_chain_run(
        {
            "ingestion": {"verdict": "pass", "detected_failure_classes": ["x"], "failure_count": 1},
            "bridge": {"verdict": "pass", "action_item_count": 0},
            "action_items": [],
        }
    )

    assert evaluation["passed"] is False
    assert any("action item" in failure for failure in evaluation["failures"])


def test_evaluate_chain_run_rejects_failure_count_mismatch():
    from evolution.core.session_end_chain import evaluate_chain_run

    evaluation = evaluate_chain_run(
        {
            "ingestion": {"verdict": "pass", "detected_failure_classes": ["x", "y"], "failure_count": 99},
            "bridge": {"verdict": "pass", "action_item_count": 1},
            "action_items": [{"title": "placeholder"}],
        }
    )

    assert evaluation["passed"] is False
    assert any("failure_count" in failure for failure in evaluation["failures"])


def test_cli_writes_chain_run_without_stdout_noise(tmp_path):
    from evolution.core.session_end_chain import main

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    out = tmp_path / "out"
    result = CliRunner().invoke(
        main,
        [
            "--trace",
            str(trace),
            "--out",
            str(out),
            "--mode",
            "chain",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert (out / "chain_run.json").exists()


def test_cli_fails_closed_without_safety_flags(tmp_path):
    from evolution.core.session_end_chain import main

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    missing_network_flag = CliRunner().invoke(
        main,
        ["--trace", str(trace), "--out", str(tmp_path / "out"), "--mode", "chain", "--no-external-writes"],
    )
    assert missing_network_flag.exit_code != 0
    assert "--no-network is required" in missing_network_flag.output

    missing_external_flag = CliRunner().invoke(
        main,
        ["--trace", str(trace), "--out", str(tmp_path / "out"), "--mode", "chain", "--no-network"],
    )
    assert missing_external_flag.exit_code != 0
    assert "--no-external-writes is required" in missing_external_flag.output


def test_cli_requires_chain_mode(tmp_path):
    from evolution.core.session_end_chain import main

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = CliRunner().invoke(
        main,
        [
            "--trace",
            str(trace),
            "--out",
            str(tmp_path / "out"),
            "--mode",
            "fixture",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid value" in result.output


def test_cli_requires_trace(tmp_path):
    from evolution.core.session_end_chain import main

    result = CliRunner().invoke(
        main,
        ["--out", str(tmp_path / "out"), "--mode", "chain", "--no-network", "--no-external-writes"],
    )

    assert result.exit_code != 0
    assert "Missing option '--trace'" in result.output


def test_chain_observe_appends_observatory_health_report(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    db = _write_healthy_observatory_db(tmp_path / "judge_audit_log.db")
    result = run_session_end_chain(
        trace,
        tmp_path / "out",
        optimize=True,
        gepa_bridge=True,
        observe=True,
        observatory_db_path=db,
    )

    assert result["mode"] == "chain_observe"
    assert result["verdict"] == "pass"
    assert result["observatory_health"]["verdict"] == "pass"
    assert result["observatory_health"]["db_path"] == str(db.resolve())
    assert result["observatory_health"]["total_calls"] == 9
    assert result["observatory_health"]["alert_count"] == 0
    assert result["observatory_health"]["alerts"] == []
    assert result["metrics"]["observatory_alert_count"] == 0
    assert result["metrics"]["steps_passed"] == 5
    assert Path(result["observatory_health"]["health_report"]).is_absolute()
    assert Path(result["observatory_health"]["health_report"]).exists()


def test_chain_observe_writes_health_artifact_in_sequence(tmp_path):
    from evolution.core.session_end_chain import run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    db = _write_healthy_observatory_db(tmp_path / "judge_audit_log.db")
    out = tmp_path / "out"
    run_session_end_chain(trace, out, optimize=True, gepa_bridge=True, observe=True, observatory_db_path=db)

    health_report = out / "observatory_health" / "health_report.json"
    assert (out / "trace_optimizer" / "run_report.json").exists()
    assert (out / "gepa_bridge" / "run_report.json").exists()
    assert health_report.exists()
    payload = json.loads(health_report.read_text())
    assert payload["mode"] == "observatory_health"
    assert payload["verdict"] == "pass"
    assert payload["health"]["total_calls"] == 9


def test_evaluate_chain_run_rejects_observatory_alerts(tmp_path):
    from evolution.core.session_end_chain import evaluate_chain_run, run_session_end_chain

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    db = _write_healthy_observatory_db(tmp_path / "judge_audit_log.db")
    result = run_session_end_chain(
        trace,
        tmp_path / "out",
        optimize=True,
        gepa_bridge=True,
        observe=True,
        observatory_db_path=db,
    )
    broken = {**result, "observatory_health": {**result["observatory_health"], "verdict": "fail", "alert_count": 1}}

    evaluation = evaluate_chain_run(broken)

    assert evaluation["passed"] is False
    assert any("observatory health" in failure for failure in evaluation["failures"])


def test_cli_chain_observe_requires_observatory_db(tmp_path):
    from evolution.core.session_end_chain import main

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    result = CliRunner().invoke(
        main,
        [
            "--trace",
            str(trace),
            "--out",
            str(tmp_path / "out"),
            "--mode",
            "chain_observe",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code != 0
    assert "--observatory-db is required for chain_observe" in result.output


def test_cli_chain_observe_writes_chain_and_health_report(tmp_path):
    from evolution.core.session_end_chain import main

    trace = _write_tool_underuse_trace(tmp_path / "session.jsonl")
    db = _write_healthy_observatory_db(tmp_path / "judge_audit_log.db")
    out = tmp_path / "out"
    result = CliRunner().invoke(
        main,
        [
            "--trace",
            str(trace),
            "--out",
            str(out),
            "--mode",
            "chain_observe",
            "--observatory-db",
            str(db),
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    chain_run = json.loads((out / "chain_run.json").read_text())
    assert chain_run["mode"] == "chain_observe"
    assert chain_run["observatory_health"]["verdict"] == "pass"
    assert (out / "observatory_health" / "health_report.json").exists()
