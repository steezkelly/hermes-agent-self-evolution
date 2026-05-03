"""Tests for ingest_captured.py enricher and split logic — P0.2 / P0.3."""

import json
import tempfile
from pathlib import Path

import pytest

from evolution.tools.ingest_captured import (
    CapturedExampleEnricher,
    assign_split,
    enrich_and_merge,
    validate_candidate,
    deploy_candidate,
)
from evolution.core.dataset_builder import EvalDataset, EvalExample


class TestCapturedExampleEnricher:
    """Rule-based rubric extraction."""

    def test_extract_rubric_from_first_section(self):
        body = """---
name: test
description: desc
---

# Overview
This is the overview content.

## Details
More details here.
"""
        rubric = CapturedExampleEnricher.extract_rubric(
            task="Do X", body=body, tool_sequence=["a", "b"], success_pattern="ok"
        )
        assert "Task: Do X" in rubric
        assert "Expected tools: a, b" in rubric
        assert "Procedure:" in rubric
        assert "This is the overview content." in rubric
        assert "## Details" not in rubric  # only first section body, not heading

    def test_extract_rubric_fallback_to_body(self):
        body = "Just some plain text without sections."
        rubric = CapturedExampleEnricher.extract_rubric(
            task="T", body=body, tool_sequence=[], success_pattern="ok"
        )
        assert "Procedure: Just some plain text" in rubric

    def test_enrich_returns_eval_example(self):
        data = {
            "task": "Search and deploy",
            "skill_body": "# Search\n\nUse web_search.",
            "tool_sequence": ["web_search", "deploy"],
            "success_pattern": "Found and deployed",
            "total_tool_calls": 4,
            "domain_tags": ["research", "devops"],
            "session_id": "sid-42",
        }
        ex = CapturedExampleEnricher.enrich(data)
        assert isinstance(ex, EvalExample)
        assert ex.task_input == "Search and deploy"
        assert ex.source == "captured"
        assert ex.tool_sequence == ["web_search", "deploy"]
        assert ex.complexity_score == 4
        assert ex.session_id == "sid-42"
        assert ex.difficulty == "medium"
        assert ex.category == "research"
        assert "Use web_search" in ex.expected_behavior

    def test_enrich_difficulty_easy(self):
        data = {
            "task": "t", "skill_body": "b", "tool_sequence": [],
            "success_pattern": "", "total_tool_calls": 1, "domain_tags": [],
        }
        ex = CapturedExampleEnricher.enrich(data)
        assert ex.difficulty == "easy"

    def test_enrich_difficulty_hard(self):
        data = {
            "task": "t", "skill_body": "b", "tool_sequence": [],
            "success_pattern": "", "total_tool_calls": 10, "domain_tags": [],
        }
        ex = CapturedExampleEnricher.enrich(data)
        assert ex.difficulty == "hard"


class TestAssignSplit:
    """Deterministic single-split assignment."""

    def test_assign_split_deterministic(self):
        s1 = assign_split("hello world")
        s2 = assign_split("hello world")
        assert s1 == s2
        assert s1 in ("train", "val", "holdout")

    def test_assign_split_distribution(self):
        counts = {"train": 0, "val": 0, "holdout": 0}
        for i in range(300):
            counts[assign_split(f"task-{i}")] += 1
        # All three splits should be reasonably represented
        assert all(c > 20 for c in counts.values()), counts

    def test_single_split_per_example(self):
        # An example can only be in one split
        splits = {assign_split(f"task-{i}") for i in range(100)}
        assert len(splits) >= 2  # all three are possible across different inputs


class TestEnrichAndMerge:
    """enrich_and_merge end-to-end."""

    def _make_candidate(self, task: str = "Test task"):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "task": task,
                "skill_body": "# Body\n\nProcedure text here.",
                "tool_sequence": ["web_search"],
                "success_pattern": "Done",
                "total_tool_calls": 3,
                "domain_tags": ["research"],
                "session_id": "s1",
                "status": "pending",
            }, f)
            return Path(f.name)

    def test_merges_into_single_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            cand = self._make_candidate()
            result = enrich_and_merge(cand, out)
            assert result["status"] == "merged"
            assert result["split"] in ("train", "val", "holdout")

            ds = EvalDataset.load(out)
            total = len(ds.train) + len(ds.val) + len(ds.holdout)
            assert total == 1
            splits_with_data = sum(1 for s in [ds.train, ds.val, ds.holdout] if len(s) > 0)
            assert splits_with_data == 1  # Gap B fix

    def test_skips_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            cand = self._make_candidate("Same task")
            r1 = enrich_and_merge(cand, out)
            assert r1["status"] == "merged"
            r2 = enrich_and_merge(cand, out)
            assert r2["status"] == "skipped"
            assert r2["reason"] == "duplicate task_input"

    def test_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            cand = self._make_candidate("Meta task")
            enrich_and_merge(cand, out)
            ds = EvalDataset.load(out)
            for split in [ds.train, ds.val, ds.holdout]:
                if split:
                    ex = split[0]
                    assert ex.tool_sequence == ["web_search"]
                    assert ex.complexity_score == 3
                    assert ex.session_id == "s1"
                    assert ex.success_pattern == "Done"
                    break

    def test_atomic_save_no_tmp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dataset"
            cand = self._make_candidate("Atomic")
            enrich_and_merge(cand, out)
            tmp_files = list(out.glob(".*.tmp"))
            assert tmp_files == []
