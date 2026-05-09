"""Tests for the real-trace attention-router bridge.

Verifies: real-trace run_report/eval_examples input loading, baseline-vs-candidate
routing gate, one action item per detected failure class, and local-only safety.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner


_FAILURES = {
    "long_briefing_instead_of_concise_action_queue": {
        "detected": True,
        "failure_class": "long_briefing_instead_of_concise_action_queue",
        "description": "Agent produced a 900-char briefing instead of one action item.",
        "evidence": {"message_index": 1, "length": 900},
    },
    "raw_session_trace_without_structured_eval_example": {
        "detected": True,
        "failure_class": "raw_session_trace_without_structured_eval_example",
        "description": "Session lacked structured eval examples.",
        "evidence": {"num_user_messages": 2},
    },
    "agent_describes_instead_of_calls_tools": {
        "detected": True,
        "failure_class": "agent_describes_instead_of_calls_tools",
        "description": "Agent described checks instead of calling tools.",
        "evidence": {"descriptive_messages_that_should_use_tools": 1},
    },
    "stale_skill_body_without_drift_detection": {
        "detected": True,
        "failure_class": "stale_skill_body_without_drift_detection",
        "description": "Skill text referenced deprecated guidance.",
        "evidence": {"messages_with_stale_references": 1},
    },
}


def _write_real_trace_output(out_dir: Path, classes: list[str] | None = None) -> Path:
    classes = list(_FAILURES) if classes is None else classes
    source_trace = out_dir / "session.jsonl"
    source_trace.write_text('{"role":"user","content":"test"}\n')

    report = {
        "schema_version": 1,
        "generated_at": "1970-01-01T00:00:00Z",
        "mode": "real_trace",
        "task_type": "trace_ingestion",
        "source_trace": str(source_trace),
        "baseline": {"passed": False, "failures": ["raw dump"]},
        "candidate": {"passed": True, "failures": [], "output_sha256": "abc"},
        "metrics": {"failure_classes_detected": len(classes)},
        "verdict": "pass",
        "safety": {
            "mode": "real_trace",
            "network_allowed": False,
            "external_writes_allowed": False,
            "github_writes_allowed": False,
            "production_mutation_allowed": False,
        },
    }
    eval_examples = {
        "schema_version": 1,
        "mode": "real_trace",
        "source_trace": str(source_trace),
        "external_writes_allowed": False,
        "examples": [
            {
                "session_id": "test-session",
                "detected_failure_classes": classes,
                "failure_count": len(classes),
                "failures": {name: _FAILURES[name] for name in classes},
            }
        ],
        "total_examples": 1,
    }
    (out_dir / "run_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out_dir / "eval_examples.json").write_text(json.dumps(eval_examples, indent=2) + "\n")
    (out_dir / "promotion_dossier.md").write_text("# Real trace dossier\n")
    (out_dir / "artifact_manifest.json").write_text("{}\n")
    return out_dir / "run_report.json"


def test_baseline_dumps_raw_report_and_fails_action_item_eval(tmp_path):
    from evolution.core.action_routing_demo import evaluate_action_item
    from evolution.core.attention_router_bridge import _baseline_attention_router_output

    report_path = _write_real_trace_output(tmp_path, ["agent_describes_instead_of_calls_tools"])
    raw_report = json.loads(report_path.read_text())

    baseline = _baseline_attention_router_output(raw_report)
    evaluation = evaluate_action_item(baseline)

    assert baseline == raw_report
    assert evaluation["passed"] is False
    assert any("missing required field" in failure for failure in evaluation["failures"])


def test_bridge_emits_one_valid_action_item_per_detected_failure(tmp_path):
    from evolution.core.action_routing_demo import evaluate_action_item
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    _write_real_trace_output(tmp_path)
    result = run_attention_router_bridge(tmp_path, tmp_path / "bridge-out")

    assert result["verdict"] == "pass"
    assert result["baseline"]["passed"] is False
    assert result["candidate"]["passed"] is True
    assert result["metrics"]["failure_classes_detected"] == 4
    assert result["metrics"]["action_items_emitted"] == 4

    queue = json.loads((tmp_path / "bridge-out" / "action_queue.json").read_text())
    assert [item["failure_class"] for item in queue["items"]] == list(_FAILURES)
    for item in queue["items"]:
        item_eval = evaluate_action_item(item)
        assert item_eval["passed"] is True, item_eval["failures"]


def test_bridge_accepts_run_report_path_input(tmp_path):
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    report_path = _write_real_trace_output(tmp_path, ["raw_session_trace_without_structured_eval_example"])
    result = run_attention_router_bridge(report_path, tmp_path / "bridge-out")

    queue = json.loads((tmp_path / "bridge-out" / "action_queue.json").read_text())
    assert result["verdict"] == "pass"
    assert len(queue["items"]) == 1
    assert queue["items"][0]["failure_class"] == "raw_session_trace_without_structured_eval_example"


def test_bridge_uses_candidate_output_embedded_in_report(tmp_path):
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    report_path = _write_real_trace_output(tmp_path, ["agent_describes_instead_of_calls_tools"])
    report = json.loads(report_path.read_text())
    report["candidate"]["output"] = {
        "detected_failure_classes": ["stale_skill_body_without_drift_detection"],
        "failures": {
            "stale_skill_body_without_drift_detection": _FAILURES[
                "stale_skill_body_without_drift_detection"
            ]
        },
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    (tmp_path / "eval_examples.json").unlink()

    run_attention_router_bridge(report_path, tmp_path / "bridge-out")

    queue = json.loads((tmp_path / "bridge-out" / "action_queue.json").read_text())
    assert len(queue["items"]) == 1
    assert queue["items"][0]["failure_class"] == "stale_skill_body_without_drift_detection"


def test_action_items_have_steve_contract_fields_and_existing_evidence(tmp_path):
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    report_path = _write_real_trace_output(tmp_path, ["long_briefing_instead_of_concise_action_queue"])
    run_attention_router_bridge(report_path, tmp_path / "bridge-out")
    item = json.loads((tmp_path / "bridge-out" / "action_queue.json").read_text())["items"][0]

    assert item["bucket"] in {"needsSteve", "autonomous", "blocked", "stale"}
    assert item["owner"]
    assert item["title"]
    assert 0 < len(item["why"]) <= 380
    assert item["evidence_paths"]
    assert all(Path(path).is_absolute() for path in item["evidence_paths"])
    assert all(Path(path).exists() for path in item["evidence_paths"])
    assert item["next_prompt"].startswith(
        "Work in `/home/steve/repos/steezkelly-hermes-agent-self-evolution`"
    )
    assert item["expires_at"] == "1970-01-08T00:00:00Z"


def test_bridge_writes_required_artifacts_with_safety_flags(tmp_path):
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    _write_real_trace_output(tmp_path, ["agent_describes_instead_of_calls_tools"])
    result = run_attention_router_bridge(tmp_path, tmp_path / "bridge-out")
    out = tmp_path / "bridge-out"

    assert (out / "run_report.json").exists()
    assert (out / "action_queue.json").exists()
    assert (out / "promotion_dossier.md").exists()
    assert (out / "artifact_manifest.json").exists()

    report = json.loads((out / "run_report.json").read_text())
    queue = json.loads((out / "action_queue.json").read_text())
    manifest = json.loads((out / "artifact_manifest.json").read_text())
    dossier = (out / "promotion_dossier.md").read_text()

    assert result["network_allowed"] is False
    assert result["external_writes_allowed"] is False
    assert report["safety"] == {
        "mode": "attention_router_bridge",
        "network_allowed": False,
        "external_writes_allowed": False,
        "github_writes_allowed": False,
        "production_mutation_allowed": False,
    }
    assert queue["external_writes_allowed"] is False
    assert manifest["external_writes_allowed"] is False
    assert manifest["artifacts"]["action_queue"] == str(out / "action_queue.json")
    assert "Baseline dumped the raw report" in dossier
    assert "Candidate emitted 1 attention-router action item" in dossier


def test_bridge_fails_gate_when_no_detected_failures(tmp_path):
    from evolution.core.attention_router_bridge import run_attention_router_bridge

    _write_real_trace_output(tmp_path, [])
    result = run_attention_router_bridge(tmp_path, tmp_path / "bridge-out")

    assert result["verdict"] == "fail"
    assert result["candidate"]["passed"] is False
    assert any("at least one" in failure for failure in result["candidate"]["failures"])


def test_bridge_cli_writes_artifacts_without_stdout_noise(tmp_path):
    from evolution.core.attention_router_bridge import main

    report_path = _write_real_trace_output(tmp_path, ["agent_describes_instead_of_calls_tools"])
    out = tmp_path / "bridge-out"
    result = CliRunner().invoke(
        main,
        [
            "--input",
            str(report_path),
            "--out",
            str(out),
            "--mode",
            "fixture",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert (out / "run_report.json").exists()
    assert (out / "action_queue.json").exists()
    assert (out / "promotion_dossier.md").exists()
    assert (out / "artifact_manifest.json").exists()


def test_bridge_cli_fails_closed_without_safety_flags(tmp_path):
    from evolution.core.attention_router_bridge import main

    report_path = _write_real_trace_output(tmp_path, ["agent_describes_instead_of_calls_tools"])
    out = tmp_path / "bridge-out"

    missing_network_flag = CliRunner().invoke(
        main,
        ["--input", str(report_path), "--out", str(out), "--mode", "fixture", "--no-external-writes"],
    )
    assert missing_network_flag.exit_code != 0
    assert "--no-network is required" in missing_network_flag.output

    missing_external_flag = CliRunner().invoke(
        main,
        ["--input", str(report_path), "--out", str(out), "--mode", "fixture", "--no-network"],
    )
    assert missing_external_flag.exit_code != 0
    assert "--no-external-writes is required" in missing_external_flag.output
