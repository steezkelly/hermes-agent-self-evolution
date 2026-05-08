"""Issue #54 ingestion metadata and source availability tests."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from evolution.core.dataset_builder import EvalExample
from evolution.core.external_importers import (
    ClaudeCodeImporter,
    RelevanceFilter,
    describe_source_availability,
    main,
)


def test_eval_example_roundtrip_preserves_source_metadata():
    example = EvalExample(
        task_input="review this PR",
        expected_behavior="identify risks",
        source="claude-code",
        project="/repo/demo",
        repo="demo",
        session_id="session-1",
        timestamp="2026-05-08T12:00:00Z",
        message_role="user",
        extraction_reason="llm_relevant",
    )

    loaded = EvalExample.from_dict(example.to_dict())

    assert loaded.project == "/repo/demo"
    assert loaded.repo == "demo"
    assert loaded.session_id == "session-1"
    assert loaded.timestamp == "2026-05-08T12:00:00Z"
    assert loaded.message_role == "user"
    assert loaded.extraction_reason == "llm_relevant"


def test_claude_importer_emits_canonical_metadata(tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({
            "display": "review this pull request for security issues",
            "timestamp": "2026-05-08T12:00:00Z",
            "project": "/tmp/demo-repo",
            "sessionId": "abc123",
        }) + "\n"
    )

    with patch.object(ClaudeCodeImporter, "HISTORY_PATH", history):
        messages = ClaudeCodeImporter.extract_messages()

    assert messages == [{
        "source": "claude-code",
        "task_input": "review this pull request for security issues",
        "assistant_response": "",
        "project": "/tmp/demo-repo",
        "repo": "demo-repo",
        "session_id": "abc123",
        "timestamp": "2026-05-08T12:00:00Z",
        "message_role": "user",
        "extraction_reason": "claude_history_user_prompt",
    }]


def test_source_availability_distinguishes_missing_path_from_empty_available_source(tmp_path):
    missing = tmp_path / "missing.jsonl"
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")

    with patch.object(ClaudeCodeImporter, "HISTORY_PATH", missing):
        missing_status = describe_source_availability(["claude-code"])[0]
    with patch.object(ClaudeCodeImporter, "HISTORY_PATH", empty):
        empty_status = describe_source_availability(["claude-code"])[0]

    assert missing_status.available is False
    assert missing_status.reason == "missing_path"
    assert missing_status.candidate_count == 0
    assert empty_status.available is True
    assert empty_status.reason == "ok"
    assert empty_status.candidate_count == 0


def test_relevance_filter_carries_message_metadata_into_eval_examples():
    with patch("evolution.core.external_importers.dspy") as mock_dspy:
        mock_dspy.context.return_value.__enter__ = MagicMock(return_value=None)
        mock_dspy.context.return_value.__exit__ = MagicMock(return_value=False)
        rf = RelevanceFilter.__new__(RelevanceFilter)
        rf.model = "test-model"
        rf.scorer = MagicMock(return_value=SimpleNamespace(
            scoring=json.dumps({
                "relevant": True,
                "expected_behavior": "review thoroughly",
                "difficulty": "medium",
                "category": "code-review",
            })
        ))

        examples = rf.filter_and_score([
            {
                "source": "hermes",
                "task_input": "review this PR and flag risky code",
                "assistant_response": "Done",
                "project": "/tmp/demo",
                "repo": "demo",
                "session_id": "s1",
                "timestamp": "2026-05-08T12:00:00Z",
                "message_role": "user",
                "extraction_reason": "hermes_user_assistant_pair",
            }
        ], "code-review", "Review pull requests and risky code", max_examples=5)

    assert len(examples) == 1
    ex = examples[0]
    assert ex.project == "/tmp/demo"
    assert ex.repo == "demo"
    assert ex.session_id == "s1"
    assert ex.timestamp == "2026-05-08T12:00:00Z"
    assert ex.message_role == "user"
    assert ex.extraction_reason == "llm_relevant"


def test_external_importer_dry_run_reports_source_availability(tmp_path):
    skills_dir = tmp_path / ".hermes" / "skills" / "code-review"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("Review pull requests and risky code")

    history = tmp_path / ".claude" / "history.jsonl"
    history.parent.mkdir()
    history.write_text(json.dumps({"display": "review this PR", "project": "/tmp/demo", "sessionId": "s"}) + "\n")

    with patch.object(ClaudeCodeImporter, "HISTORY_PATH", history):
        result = CliRunner().invoke(
            main,
            ["--source", "claude-code", "--skill", "code-review", "--dry-run"],
            env={"HOME": str(tmp_path)},
        )

    assert result.exit_code == 0
    assert "available" in result.output
    assert "candidates=1" in result.output
    assert str(history) in result.output
