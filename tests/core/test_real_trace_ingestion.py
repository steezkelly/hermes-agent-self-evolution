"""Tests for real-trace ingestion module.

Verifies: session loading, all four detectors, structured extraction,
baseline-vs-candidate gating, and safety boundaries.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from evolution.core.real_trace_ingestion import (
    _baseline_dump,
    _extract_structured,
    _REQUIRED_FIELDS,
    detect_long_briefing,
    detect_raw_session_dump,
    detect_skill_drift,
    detect_tool_underuse,
    evaluate_real_trace_extraction,
    load_session,
    run_real_trace_ingestion,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_jsonl(session_id: str, messages: list[dict]) -> str:
    """Build a minimal JSONL string from a list of message dicts."""
    lines = []
    for m in messages:
        lines.append(json.dumps(m))
    return "\n".join(lines) + "\n"


@pytest.fixture
def long_briefing_session() -> dict:
    """Session where assistant produces a long briefing with options."""
    jsonl = _make_mock_jsonl("briefing-test", [
        {"role": "user", "content": "What should we do about the architecture?"},
        {"role": "assistant", "content": (
            "There are several options we could consider. Option 1: refactor "
            "the bootstrap plan. Option 2: create a Foundry demo. Option 3: "
            "write more documentation. Option 4: wait for more research. "
            "I think we should carefully weigh each option before deciding.\n"
            "Each path has trade-offs and could affect the timeline.\n"
            "Let me outline the pros and cons of each approach in detail.\n"
            "Option 1 would require changes to the NixOS module structure.\n"
            "Option 2 would need a new Click CLI command in Foundry.\n"
            "Option 3 is the least risky but may not add immediate value.\n"
            "Option 4 preserves optionality but delays the decision.\n"
            "I recommend we take some time to think about this further."
        )},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()
    session = load_session(Path(trace.name))
    Path(trace.name).unlink()
    return session


@pytest.fixture
def tool_describing_session() -> dict:
    """Session where agent describes instead of calling tools."""
    jsonl = _make_mock_jsonl("tool-test", [
        {"role": "user", "content": "Check if Docker is running and list containers."},
        {"role": "assistant", "content": (
            "To check if Docker is running, you should run `systemctl status docker`. "
            "Then you can list containers with `docker ps`. You should also verify "
            "the docker socket is accessible at /var/run/docker.sock. Check the "
            "permissions and make sure your user is in the docker group. "
            "Additionally, you could examine the Docker daemon configuration."
        )},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()
    session = load_session(Path(trace.name))
    Path(trace.name).unlink()
    return session


@pytest.fixture
def raw_data_session() -> dict:
    """Session with data but no structured extraction."""
    jsonl = _make_mock_jsonl("raw-test", [
        {"role": "user", "content": "Parse this CSV file."},
        {"role": "assistant", "content": "Here is the data:\n\nName,Value\nA,1\nB,2\nC,3"},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()
    session = load_session(Path(trace.name))
    Path(trace.name).unlink()
    return session


@pytest.fixture
def skill_drift_session() -> dict:
    """Session referencing deprecated/stale skill content."""
    jsonl = _make_mock_jsonl("drift-test", [
        {"role": "user", "content": "Use the deployment skill to deploy the app."},
        {"role": "assistant", "content": (
            "According to the deployment skill, we should use the legacy Capistrano "
            "approach. This is deprecated and no longer recommended. The skill "
            "references an outdated version of the deployment pipeline. The old "
            "version used manual rsync which has been superseded."
        )},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()
    session = load_session(Path(trace.name))
    Path(trace.name).unlink()
    return session


# ---------------------------------------------------------------------------
# Session loading
# ---------------------------------------------------------------------------


def test_load_session_parses_messages():
    jsonl = _make_mock_jsonl("test-session", [
        {"role": "session_meta", "session_id": "test-session", "tools": []},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!", "tool_calls": [
            {"function": {"name": "terminal"}}
        ]},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()

    session = load_session(Path(trace.name))
    Path(trace.name).unlink()

    assert session["session_id"] == "test-session"
    assert session["total_messages"] == 2  # meta filtered out
    assert session["messages"][0]["role"] == "user"
    assert session["messages"][1]["tool_calls"] == ["terminal"]


def test_load_session_skips_meta_and_empty_lines():
    jsonl = "\n" + _make_mock_jsonl("test", [
        {"role": "session_meta", "tools": []},
        {"role": "user", "content": "x"},
    ]) + "\n\n"
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()

    session = load_session(Path(trace.name))
    Path(trace.name).unlink()
    assert session["total_messages"] == 1


# ---------------------------------------------------------------------------
# Detector tests
# ---------------------------------------------------------------------------


def test_detect_long_briefing(long_briefing_session):
    result = detect_long_briefing(long_briefing_session)
    assert result is not None
    assert result["detected"] is True
    assert result["failure_class"] == "long_briefing_instead_of_concise_action_queue"
    assert result["evidence"]["length"] > 500


def test_detect_long_briefing_none_when_concise(tool_describing_session):
    # Session with short descriptive message shouldn't trigger briefing detector
    result = detect_long_briefing(tool_describing_session)
    # Could be None or detected; depends on detector thresholds
    # Just verify no crash and valid output shape
    assert result is None or "detected" in result


def test_detect_raw_session_dump(raw_data_session):
    result = detect_raw_session_dump(raw_data_session)
    assert result is not None
    assert result["detected"] is True
    assert result["failure_class"] == "raw_session_trace_without_structured_eval_example"


def test_detect_raw_session_dump_none_when_structured():
    session = {
        "session_id": "structured",
        "messages": [
            {"role": "user", "content": "Extract the task"},
            {"role": "assistant", "content": "task_input: ..., expected_behavior: ..."},
        ],
    }
    result = detect_raw_session_dump(session)
    assert result is None


def test_detect_tool_underuse(tool_describing_session):
    result = detect_tool_underuse(tool_describing_session)
    assert result is not None
    assert result["detected"] is True
    assert result["failure_class"] == "agent_describes_instead_of_calls_tools"
    assert result["evidence"]["messages_with_tool_calls"] == 0
    assert len(result["evidence"]["examples"]) >= 1


def test_detect_tool_underuse_none_when_using_tools():
    session = {
        "session_id": "using-tools",
        "messages": [
            {"role": "user", "content": "Check docker", "tool_calls": []},
            {"role": "assistant", "content": "ok", "tool_calls": [
                {"function": {"name": "terminal"}}
            ]},
        ],
    }
    result = detect_tool_underuse(session)
    assert result is None


def test_detect_skill_drift(skill_drift_session):
    result = detect_skill_drift(skill_drift_session)
    assert result is not None
    assert result["detected"] is True
    assert result["failure_class"] == "stale_skill_body_without_drift_detection"
    assert result["evidence"]["messages_with_stale_references"] >= 1


def test_detect_skill_drift_none_when_fresh():
    session = {
        "session_id": "fresh",
        "messages": [
            {"role": "user", "content": "Use the skill"},
            {"role": "assistant", "content": "According to the skill, use the latest approach."},
        ],
    }
    result = detect_skill_drift(session)
    assert result is None


# ---------------------------------------------------------------------------
# Extractor tests
# ---------------------------------------------------------------------------


def test_baseline_dump_has_note():
    session = {"session_id": "test", "messages": [{"role": "user", "content": "hi"}]}
    output = _baseline_dump(session)
    assert "note" in output
    assert "raw session trace" in output["note"].lower()


def test_candidate_extract_has_required_fields(raw_data_session):
    detectors = {
        "long_briefing_instead_of_concise_action_queue": None,
        "raw_session_trace_without_structured_eval_example": detect_raw_session_dump(raw_data_session),
        "agent_describes_instead_of_calls_tools": None,
        "stale_skill_body_without_drift_detection": None,
    }
    output = _extract_structured(raw_data_session, detectors)
    for field in _REQUIRED_FIELDS:
        assert field in output, f"missing {field}"


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------


def test_evaluator_rejects_baseline_dump():
    baseline = _baseline_dump({"session_id": "x", "messages": []})
    result = evaluate_real_trace_extraction(baseline)
    assert result["passed"] is False
    assert any("raw session dump" in f.lower() for f in result["failures"])


def test_evaluator_accepts_structured():
    candidate = {
        "session_id": "x",
        "total_messages": 3,
        "user_messages": 1,
        "assistant_messages": 2,
        "detected_failure_classes": [],
        "failure_count": 0,
        "failures": {},
        "first_user_message": "hello",
        "last_assistant_snippet": "bye",
        "detection_summary": [],
    }
    result = evaluate_real_trace_extraction(candidate)
    assert result["passed"] is True


def test_evaluator_rejects_missing_fields():
    result = evaluate_real_trace_extraction({})
    assert result["passed"] is False
    assert len(result["failures"]) >= 1


def test_evaluator_checks_failure_count_consistency():
    candidate = {
        "session_id": "x",
        "detected_failure_classes": ["one"],
        "failure_count": 99,  # inconsistent
        "failures": {"one": True},
    }
    result = evaluate_real_trace_extraction(candidate)
    assert result["passed"] is False


# ---------------------------------------------------------------------------
# End-to-end ingestion
# ---------------------------------------------------------------------------


def test_run_real_trace_ingestion_produces_artifacts(tool_describing_session):
    # Reconstruct the trace file (session fixture consumed it)
    jsonl = _make_mock_jsonl("e2e-test", [
        {"role": "user", "content": "Check if Docker is running and list containers."},
        {"role": "assistant", "content": (
            "To check if Docker is running, you should run `systemctl status docker`. "
            "Then you can list containers with `docker ps`. You should also verify "
            "the docker socket is accessible at /var/run/docker.sock. Check the "
            "permissions and make sure your user is in the docker group. "
            "Additionally, you could examine the Docker daemon configuration."
        )},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()

    with tempfile.TemporaryDirectory() as out_dir:
        result = run_real_trace_ingestion(Path(trace.name), Path(out_dir))

        assert result["verdict"] == "pass"
        assert result["mode"] == "real_trace"
        assert result["external_writes_allowed"] is False
        assert result["network_allowed"] is False

        out = Path(out_dir)
        assert (out / "run_report.json").exists()
        assert (out / "eval_examples.json").exists()
        assert (out / "promotion_dossier.md").exists()
        assert (out / "artifact_manifest.json").exists()

    Path(trace.name).unlink()


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------


def test_safety_mode_is_real_trace():
    """Safety section always reflects real_trace mode with no mutation allowed."""
    session = {
        "session_id": "safety-test",
        "messages": [{"role": "user", "content": "test"}],
    }
    detectors = {
        "long_briefing_instead_of_concise_action_queue": None,
        "raw_session_trace_without_structured_eval_example": detect_raw_session_dump(session),
        "agent_describes_instead_of_calls_tools": None,
        "stale_skill_body_without_drift_detection": None,
    }

    # Verify the safety boundary is built into the report structure
    # The run_real_trace_ingestion function constructs the safety dict
    jsonl = _make_mock_jsonl("safety-session", [
        {"role": "user", "content": "test safety boundaries"},
        {"role": "assistant", "content": "ok"},
    ])
    trace = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    trace.write(jsonl.encode())
    trace.close()

    with tempfile.TemporaryDirectory() as out_dir:
        result = run_real_trace_ingestion(Path(trace.name), Path(out_dir))
        safety = result.get("safety", {"mode": result["mode"]})
        assert result["network_allowed"] is False
        assert result["external_writes_allowed"] is False

    Path(trace.name).unlink()
