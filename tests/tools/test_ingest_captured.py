"""Tests for the ingest-captured pipeline."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def sample_candidate():
    """Create a temporary captured candidate file."""
    data = {
        "session_id": "test-session-001",
        "captured_at": "2026-04-28T12:00:00+00:00",
        "task": "Build a Python script to analyze log files for error patterns",
        "success_pattern": "Built and verified solution through iterative code and shell commands",
        "domain_tags": ["python", "testing", "config"],
        "tool_sequence": [
            {"tool_name": "search_files", "args_preview": {"pattern": "*.log"}},
            {"tool_name": "read_file", "args_preview": {"path": "/var/log/app.log"}},
            {"tool_name": "write_file", "args_preview": {"path": "analyze_logs.py"}},
            {"tool_name": "terminal", "args_preview": {"command": "python analyze_logs.py"}},
        ],
        "total_tool_calls": 4,
        "skill_body": (
            "# Analyze Log Files for Error Patterns\n\n"
            "## When to Use\n"
            "- System log analysis with pattern extraction\n"
            "- Error frequency tracking across time windows\n\n"
            "## Approach\n\n"
            "1. Search for log files matching the target pattern\n"
            "2. Read the log file to understand its structure\n"
            "3. Write an analysis script that extracts error patterns\n"
            "4. Run the script and review results\n"
        ),
        "overlapping_skills": [],
        "status": "pending",
    }

    with tempfile.TemporaryDirectory() as tmp:
        # Save to a fake captured directory
        captured_dir = Path(tmp) / "captured"
        captured_dir.mkdir()
        filepath = captured_dir / "analyze-logs__test-session-001.json"
        filepath.write_text(json.dumps(data, indent=2))

        # Create a dummy skills directory
        skills_dir = Path(tmp) / "skills"
        skills_dir.mkdir()

        yield {
            "captured_dir": captured_dir,
            "skills_dir": skills_dir,
            "filepath": filepath,
            "data": data,
        }


class TestIngestCapture:
    """Tests for the ingest_captured module."""

    def test_list_pending(self, sample_candidate, monkeypatch):
        monkeypatch.setattr("evolution.tools.ingest_captured.CAPTURED_DIR",
                           sample_candidate["captured_dir"])
        from evolution.tools.ingest_captured import list_candidates
        candidates = list_candidates(status_filter="pending")
        assert len(candidates) == 1
        assert candidates[0]["status"] == "pending"
        assert candidates[0]["task"].startswith("Build a Python script")

    def test_validate_valid(self, sample_candidate, monkeypatch):
        monkeypatch.setattr("evolution.tools.ingest_captured.SKILLS_DIRS",
                           [sample_candidate["skills_dir"]])
        monkeypatch.setattr("evolution.tools.ingest_captured.CAPTURED_DIR",
                           sample_candidate["captured_dir"])
        from evolution.tools.ingest_captured import validate_candidate
        valid, reason, checks = validate_candidate(sample_candidate["filepath"])
        assert valid, f"Should be valid: {reason}"
        assert checks["body_length"] == "OK"
        assert checks["structure"] == "OK"

    def test_validate_empty_body(self, sample_candidate, monkeypatch):
        monkeypatch.setattr("evolution.tools.ingest_captured.SKILLS_DIRS",
                           [sample_candidate["skills_dir"]])
        data = sample_candidate["data"].copy()
        data["skill_body"] = "Short"
        sample_candidate["filepath"].write_text(json.dumps(data, indent=2))

        from evolution.tools.ingest_captured import validate_candidate, list_candidates
        valid, reason, checks = validate_candidate(sample_candidate["filepath"])
        assert not valid
        assert "body_length" in reason

    def test_deploy_creates_skill(self, sample_candidate, monkeypatch):
        monkeypatch.setattr("evolution.tools.ingest_captured.SKILLS_DIRS",
                           [sample_candidate["skills_dir"]])
        monkeypatch.setattr("evolution.tools.ingest_captured.CAPTURED_DIR",
                           sample_candidate["captured_dir"])
        # Patch home to our temp dir
        monkeypatch.setattr("evolution.tools.ingest_captured.Path.home",
                           lambda: sample_candidate["skills_dir"].parent)

        from evolution.tools.ingest_captured import deploy_candidate
        success, msg = deploy_candidate(sample_candidate["filepath"])
        assert success, f"Deploy failed: {msg}"

        # Check skill was created at ~/.hermes/skills/<name>/
        home = sample_candidate["skills_dir"].parent
        skill_path = home / ".hermes" / "skills" / "analyze-log-files-for-error-patterns" / "SKILL.md"
        assert skill_path.exists(), f"Skill not created at {skill_path}"
        skill_text = skill_path.read_text()
        assert "Analyze Log Files" in skill_text
        assert "name: analyze-log-files-for-error-patterns" in skill_text

        # Clean up deployed skill
        skill_dir = home / ".hermes" / "skills" / "analyze-log-files-for-error-patterns"
        import shutil
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

    def test_deploy_twice_fails(self, sample_candidate, monkeypatch):
        """Deploying the same skill twice should fail."""
        monkeypatch.setattr("evolution.tools.ingest_captured.SKILLS_DIRS",
                           [sample_candidate["skills_dir"]])
        monkeypatch.setattr("evolution.tools.ingest_captured.CAPTURED_DIR",
                           sample_candidate["captured_dir"])
        monkeypatch.setattr("evolution.tools.ingest_captured.Path.home",
                           lambda: sample_candidate["skills_dir"].parent)

        from evolution.tools.ingest_captured import deploy_candidate
        success, _ = deploy_candidate(sample_candidate["filepath"])
        assert success

        # Second deploy should fail (skill already exists)
        success, msg = deploy_candidate(sample_candidate["filepath"])
        assert not success
        assert "already exists" in msg

        # Clean up deployed skill
        home = sample_candidate["skills_dir"].parent
        skill_dir = home / ".hermes" / "skills" / "analyze-log-files-for-error-patterns"
        import shutil
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

    def test_stats(self, sample_candidate, monkeypatch):
        monkeypatch.setattr("evolution.tools.ingest_captured.CAPTURED_DIR",
                           sample_candidate["captured_dir"])
        from evolution.tools.ingest_captured import list_candidates
        all_c = list_candidates()
        assert len(all_c) == 1

        pending = list_candidates(status_filter="pending")
        assert len(pending) == 1

    def test_generate_skill_name(self):
        from evolution.tools.ingest_captured import _generate_skill_name
        name = _generate_skill_name(
            "Build a Python script for log analysis",
            "# Analyze Logs\n\nSome content",
        )
        assert "analyze-logs" in name
        assert all(c.isalnum() or c == "-" for c in name)

        # Test with no heading
        name2 = _generate_skill_name(
            "Fix database connection pooling issue",
            "Some content without a heading",
        )
        assert "fix-database" in name2
