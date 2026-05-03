"""Tests for dataset_builder.py — P0.1 extensions."""

import json
import tempfile
from pathlib import Path

import pytest

from evolution.core.dataset_builder import EvalExample, EvalDataset


class TestEvalExample:
    """EvalExample dataclass behaviour."""

    def test_to_dict_includes_new_fields(self):
        ex = EvalExample(
            task_input="test",
            expected_behavior="rubric",
            tool_sequence=["web_search", "terminal"],
            complexity_score=3,
            session_id="abc-123",
            success_pattern="Completed with 3 tools",
        )
        d = ex.to_dict()
        assert d["tool_sequence"] == ["web_search", "terminal"]
        assert d["complexity_score"] == 3
        assert d["session_id"] == "abc-123"
        assert d["success_pattern"] == "Completed with 3 tools"

    def test_from_dict_backward_compat(self):
        """Old JSONL files without new fields should load with defaults."""
        old = {
            "task_input": "old task",
            "expected_behavior": "old rubric",
            "difficulty": "hard",
            "category": "code",
            "source": "synthetic",
        }
        ex = EvalExample.from_dict(old)
        assert ex.task_input == "old task"
        assert ex.tool_sequence == []
        assert ex.complexity_score == 0
        assert ex.session_id == ""
        assert ex.success_pattern == ""

    def test_from_dict_round_trip(self):
        ex = EvalExample(
            task_input="t",
            expected_behavior="e",
            difficulty="easy",
            category="test",
            source="captured",
            tool_sequence=["a", "b"],
            complexity_score=2,
            session_id="sid",
            success_pattern="ok",
        )
        ex2 = EvalExample.from_dict(ex.to_dict())
        assert ex2 == ex


class TestEvalDatasetMerge:
    """EvalDataset.merge() dedup behaviour."""

    def test_merge_adds_new_examples(self):
        ds1 = EvalDataset(
            train=[EvalExample("t1", "e1")],
            val=[EvalExample("v1", "e_v1")],
        )
        ds2 = EvalDataset(
            train=[EvalExample("t2", "e2")],
            holdout=[EvalExample("h1", "e_h1")],
        )
        result = ds1.merge(ds2)
        assert result == {"train": 1, "val": 0, "holdout": 1}
        assert len(ds1.train) == 2
        assert len(ds1.val) == 1
        assert len(ds1.holdout) == 1

    def test_merge_skips_duplicates(self):
        ds1 = EvalDataset(train=[EvalExample("same", "e1")])
        ds2 = EvalDataset(
            train=[EvalExample("same", "e1")],
            val=[EvalExample("same", "e1")],
            holdout=[EvalExample("same", "e1")],
        )
        result = ds1.merge(ds2)
        assert result == {"train": 0, "val": 0, "holdout": 0}
        assert len(ds1.train) == 1

    def test_merge_empty_other(self):
        ds1 = EvalDataset(train=[EvalExample("a", "b")])
        ds2 = EvalDataset()
        result = ds1.merge(ds2)
        assert result == {"train": 0, "val": 0, "holdout": 0}


class TestEvalDatasetAtomicSave:
    """EvalDataset.save_atomic() behaviour."""

    def test_atomic_save_creates_jsonl_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset"
            ds = EvalDataset(
                train=[EvalExample("t1", "e1")],
                val=[EvalExample("v1", "e_v1")],
                holdout=[EvalExample("h1", "e_h1")],
            )
            ds.save_atomic(path)
            assert (path / "train.jsonl").exists()
            assert (path / "val.jsonl").exists()
            assert (path / "holdout.jsonl").exists()

    def test_atomic_save_does_not_leave_tmp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset"
            ds = EvalDataset(train=[EvalExample("x", "y")])
            ds.save_atomic(path)
            tmp_files = list(path.glob(".*.tmp"))
            assert tmp_files == []

    def test_atomic_save_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset"
            ds = EvalDataset(
                train=[EvalExample("t1", "e1", tool_sequence=["a"], complexity_score=2)],
            )
            ds.save_atomic(path)
            loaded = EvalDataset.load(path)
            assert len(loaded.train) == 1
            assert loaded.train[0].tool_sequence == ["a"]
            assert loaded.train[0].complexity_score == 2

    def test_atomic_save_overwrites_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset"
            path.mkdir()
            (path / "train.jsonl").write_text(json.dumps({"old": "data"}) + "\n")
            ds = EvalDataset(train=[EvalExample("new", "rubric")])
            ds.save_atomic(path)
            lines = (path / "train.jsonl").read_text().strip().split("\n")
            assert len(lines) == 1
            assert json.loads(lines[0])["task_input"] == "new"
