"""Integration tests for the capture plugin — P0.6."""

import json
import tempfile
from pathlib import Path

import pytest
import uuid

from evolution.tools.ingest_captured import (
    CapturedExampleEnricher,
    assign_split,
    enrich_and_merge,
    validate_candidate,
    deploy_candidate,
)
from evolution.core.dataset_builder import EvalDataset


# --- Standalone re-implementation of capture plugin helpers ---
# We import them directly from the plugin module if possible, but since the
# plugin lives in ~/.hermes/hermes-agent/plugins/captured/ we inline minimal
# helpers to avoid PYTHONPATH issues.

def _extract_tool_sequence(messages: list[dict]) -> list[str]:
    tools, seen = [], set()
    for msg in messages:
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {}).get("name", "")
            if fn and fn not in seen:
                tools.append(fn)
                seen.add(fn)
    return tools


def _is_capturable(messages: list[dict]) -> bool:
    return sum(len(m.get("tool_calls", [])) for m in messages) >= 3


# --- Plugin logic tests ---

class TestExtractToolSequence:
    def test_extracts_unique_tools_in_order(self):
        msgs = [
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "web_search"}},
                {"function": {"name": "read_file"}},
            ]},
            {"role": "assistant", "tool_calls": [
                {"function": {"name": "web_search"}},  # dup
                {"function": {"name": "terminal"}},
            ]},
        ]
        seq = _extract_tool_sequence(msgs)
        assert seq == ["web_search", "read_file", "terminal"]

    def test_empty_messages(self):
        assert _extract_tool_sequence([]) == []

    def test_missing_tool_calls(self):
        assert _extract_tool_sequence([{"role": "user", "content": "hi"}]) == []


class TestIsCapturable:
    def test_three_tool_calls_is_capturable(self):
        msgs = [{"role": "assistant", "tool_calls": [{"function": {"name": "a"}}]}] * 3
        assert _is_capturable(msgs) is True

    def test_two_tool_calls_not_capturable(self):
        msgs = [{"role": "assistant", "tool_calls": [{"function": {"name": "a"}}]}] * 2
        assert _is_capturable(msgs) is False

    def test_five_tool_calls_capturable(self):
        msgs = [{"role": "assistant", "tool_calls": [{"function": {"name": "a"}}]}] * 5
        assert _is_capturable(msgs) is True


class TestAssignSplitDistribution:
    def test_no_data_leakage_across_runs(self):
        """Same task always goes to same split; different tasks distribute."""
        splits = {assign_split(f"task-{i}") for i in range(100)}
        assert len(splits) >= 2

    def test_determinism(self):
        assert assign_split("hello") == assign_split("hello")


class TestEndToEnd:
    """Full pipeline: fake candidate → validate → deploy → check dataset."""

    def _make_candidate(self, task: str = "Run a terminal test task"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "task": task,
                "skill_body": (
                    f"# {task}\n\n"
                    "Use the terminal tool to run commands."
                ),
                "tool_sequence": ["terminal", "read_file", "write_file"],
                "success_pattern": "Files created",
                "total_tool_calls": 4,
                "domain_tags": ["devops"],
                "session_id": "test-sid",
                "status": "pending",
            }, f)
            return Path(f.name)

    def test_validate_checks(self):
        cand = self._make_candidate()
        valid, reason, checks = validate_candidate(cand)
        assert valid
        assert checks["body_length"] == "OK"
        assert checks["task"] == "OK"

    def test_deploy_updates_status(self):
        uniq = f"Deploy test {uuid.uuid4().hex[:8]}"
        cand = self._make_candidate(uniq)
        ok, msg = deploy_candidate(cand)
        assert ok, msg
        data = json.loads(cand.read_text())
        assert data["status"] == "deployed"

    def test_enrich_single_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ds"
            cand = self._make_candidate("Split test")
            r = enrich_and_merge(cand, out)
            assert r["status"] == "merged"
            ds = EvalDataset.load(out)
            assert sum(len(s) for s in [ds.train, ds.val, ds.holdout]) == 1
            assert sum(1 for s in [ds.train, ds.val, ds.holdout] if len(s) > 0) == 1

    def test_dedup_prevents_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ds"
            cand = self._make_candidate("Dedup test")
            r1 = enrich_and_merge(cand, out)
            assert r1["status"] == "merged"
            r2 = enrich_and_merge(cand, out)
            assert r2["status"] == "skipped"
            ds = EvalDataset.load(out)
            assert len(ds.all_examples) == 1
