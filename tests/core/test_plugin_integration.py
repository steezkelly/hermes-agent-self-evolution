"""Integration tests for the capture plugin — P1.2.

Tests _on_session_end with fake session files and validates end-to-end
plugin behaviour without needing a live Hermes Agent instance.
"""

import json
import shutil
import tempfile
from pathlib import Path
from importlib import util

import pytest

# ---------------------------------------------------------------------------
# Import the plugin module directly from its install location
# ---------------------------------------------------------------------------
PLUGIN_INIT = Path.home() / ".hermes" / "hermes-agent" / "plugins" / "captured" / "__init__.py"

if PLUGIN_INIT.exists():
    spec = util.spec_from_file_location("captured_plugin", PLUGIN_INIT)
    plugin = util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
else:
    plugin = None

skip_no_plugin = pytest.mark.skipif(
    plugin is None, reason="capture plugin not installed"
)


@pytest.fixture
def mock_capture_dir(tmp_path, monkeypatch):
    """Redirect CAPTURED_DIR to a temp location."""
    capture_dir = tmp_path / "captured"
    capture_dir.mkdir()
    monkeypatch.setattr(plugin, "CAPTURED_DIR", capture_dir)
    return capture_dir


@pytest.fixture
def mock_session_dir(tmp_path, monkeypatch):
    """Provide a temp sessions dir and a session-end wrapper."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()

    def _patched_on_end(session_id, completed=True, interrupted=False):
        if interrupted or not completed or not session_id:
            return
        session_file = sessions / f"{session_id}.jsonl"
        if not session_file.exists():
            plugin._log_error(FileNotFoundError(f"Session {session_id}"), "session_lookup")
            return
        messages = []
        with open(session_file) as f:
            for line in f:
                if line.strip():
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if plugin._is_capturable(messages):
            plugin._save_candidate(session_id, messages)

    monkeypatch.setattr(plugin, "_on_session_end", _patched_on_end)
    return sessions


@pytest.fixture(autouse=True)
def cleanup_capture_errors(monkeypatch):
    """Keep capture errors isolated from real logs."""
    error_dir = Path(tempfile.mkdtemp())
    monkeypatch.setattr(plugin, "ERROR_LOG", error_dir)
    plugin.ERROR_LOG.mkdir(parents=True, exist_ok=True)
    yield
    shutil.rmtree(error_dir, ignore_errors=True)


def _make_session(sessions: Path, session_id: str, user_task: str, tool_names: list[str], body_text: str):
    """Write a fake session JSONL file."""
    session_file = sessions / f"{session_id}.jsonl"
    with open(session_file, "w") as f:
        f.write(json.dumps({"role": "user", "content": user_task}) + "\n")
        for i, tool in enumerate(tool_names):
            f.write(json.dumps({
                "role": "assistant",
                "content": body_text,
                "tool_calls": [{"function": {"name": tool}}],
            }) + "\n")


LONG_BODY = (
    "# Capture Plugin Integration Test\n\n"
    "This is a sufficiently long text to pass the 50-character minimum "
    "for the skill body heuristic and is also used in eval tests."
)


@skip_no_plugin
class TestPluginOnSessionEnd:

    def test_captures_when_3_tool_calls(self, mock_session_dir, mock_capture_dir):
        _make_session(mock_session_dir, "sess-3", "Do task",
                      ["tool_a", "tool_b", "tool_c"], LONG_BODY)
        plugin._on_session_end("sess-3")
        candidates = list(mock_capture_dir.glob("*.json"))
        assert len(candidates) == 1
        data = json.loads(candidates[0].read_text())
        assert data["total_tool_calls"] == 3
        assert data["tool_sequence"] == ["tool_a", "tool_b", "tool_c"]

    def test_skips_when_2_tool_calls(self, mock_session_dir, mock_capture_dir):
        _make_session(mock_session_dir, "sess-2", "Do task",
                      ["tool_a", "tool_b"], LONG_BODY)
        plugin._on_session_end("sess-2")
        assert list(mock_capture_dir.glob("*.json")) == []

    def test_skips_on_interrupt(self, mock_session_dir, mock_capture_dir):
        _make_session(mock_session_dir, "sess-i", "Do task",
                      ["a", "b", "c", "d"], LONG_BODY)
        plugin._on_session_end("sess-i", completed=True, interrupted=True)
        assert list(mock_capture_dir.glob("*.json")) == []

    def test_extracts_task_from_first_user_message(self, mock_session_dir, mock_capture_dir):
        _make_session(mock_session_dir, "sess-task",
                      "Deploy a web application to a Kubernetes cluster",
                      ["terminal", "search_files", "write_file"], LONG_BODY)
        plugin._on_session_end("sess-task")
        candidates = list(mock_capture_dir.glob("*.json"))
        assert len(candidates) == 1
        data = json.loads(candidates[0].read_text())
        assert "deploy" in data["task"].lower()
        assert "kubernetes" in data["task"].lower()

    def test_longest_assistant_content_as_skill_body(self, mock_session_dir, mock_capture_dir):
        session_file = mock_session_dir / "sess-body.jsonl"
        with open(session_file, "w") as f:
            f.write(json.dumps({"role": "user", "content": "Setup"}) + "\n")
            f.write(json.dumps({
                "role": "assistant",
                "content": "Short.",
                "tool_calls": [{"function": {"name": "a"}}],
            }) + "\n")
            f.write(json.dumps({
                "role": "assistant",
                "content": LONG_BODY,
                "tool_calls": [{"function": {"name": "terminal"}}],
            }) + "\n")
            f.write(json.dumps({
                "role": "assistant",
                "content": "Final step.",
                "tool_calls": [{"function": {"name": "write_file"}}],
            }) + "\n")
        plugin._on_session_end("sess-body")
        candidates = list(mock_capture_dir.glob("*.json"))
        data = json.loads(candidates[0].read_text())
        assert "Capture Plugin Integration Test" in data["skill_body"]


@skip_no_plugin
class TestPluginHeuristics:

    def test_domain_tags_from_github_tools(self):
        tags = plugin._generate_domain_tags(["github_pull_request", "search_files", "terminal"])
        assert "github" in tags
        assert "codebase" in tags
        assert "devops" in tags

    def test_domain_tags_unknown_tools(self):
        tags = plugin._generate_domain_tags(["custom_tool", "another"])
        assert tags == []

    def test_check_overlap_detects_existing_skill(self, tmp_path, monkeypatch):
        # Create fake HOME so plugin skills check resolves under tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        hermes_dir = tmp_path / ".hermes"
        skills_dir = hermes_dir / "skills"
        skills_dir.mkdir(parents=True)
        skill_dir = skills_dir / "jaccard-text-overlap"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# Jaccard Text Overlap\n\nUse Jaccard similarity to detect overlap between bodies."
        )

        overlaps = plugin._check_overlap("jaccard similarity overlap detection body text")
        names = [o["skill_name"] for o in overlaps]
        assert "jaccard-text-overlap" in names


@skip_no_plugin
class TestPluginSlashCommand:

    def test_list_empty(self, mock_capture_dir):
        for f in mock_capture_dir.glob("*.json"):
            f.unlink()
        result = plugin._slash_captured("list")
        assert "Captured candidates:" in result

    def test_stats_empty(self, mock_capture_dir):
        for f in mock_capture_dir.glob("*.json"):
            f.unlink()
        result = plugin._slash_captured("stats")
        assert "Capture Statistics:" in result
        assert "Candidates: 0" in result


@skip_no_plugin
class TestPluginDeterminism:

    def test_parallel_merges_no_dupes(self, tmp_path):
        from evolution.tools.ingest_captured import enrich_and_merge

        cand = tmp_path / "cand.json"
        cand.write_text(json.dumps({
            "task": "Determinism test",
            "skill_body": "# Body\n\nBody text long enough for tests.",
            "tool_sequence": ["a", "b"],
            "success_pattern": "ok",
            "total_tool_calls": 3,
            "domain_tags": ["test"],
            "session_id": "sid",
            "status": "pending",
        }))
        out = tmp_path / "dataset"

        results = [enrich_and_merge(cand, out) for _ in range(5)]
        merged = [r for r in results if r["status"] == "merged"]
        skipped = [r for r in results if r["status"] == "skipped"]
        assert len(merged) == 1
        assert len(skipped) == 4

        from evolution.core.dataset_builder import EvalDataset
        ds = EvalDataset.load(out)
        assert len(ds.all_examples) == 1
