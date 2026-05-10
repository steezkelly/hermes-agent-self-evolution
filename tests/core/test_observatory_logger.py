"""Tests for evolution.core.observatory.logger

Covers: auto-init, logging, idempotency, stats, thread safety, STDDEV_SAMP fix.
"""

import sqlite3
import threading
import tempfile
from pathlib import Path

import numpy as np
import pytest

from evolution.core.observatory.logger import (
    JudgeAuditLogger,
    log_judge_call,
    _default_db_path,
)


@pytest.fixture
def tmp_logger():
    """Provide a fresh JudgeAuditLogger backed by a temporary DB."""
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "test_audit.db"
        logger = JudgeAuditLogger(db_path=db)
        yield logger


class TestAutoInit:
    def test_db_created(self, tmp_logger):
        assert tmp_logger.db_path.exists()

    def test_schema_tables(self, tmp_logger):
        conn = sqlite3.connect(tmp_logger.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='judge_audit_log'"
        )
        assert cur.fetchone() is not None

    def test_delete_journal_mode(self, tmp_logger):
        conn = sqlite3.connect(tmp_logger.db_path)
        cur = conn.execute("PRAGMA journal_mode")
        mode = cur.fetchone()[0]
        assert mode.upper() == "DELETE"

    def test_indexes_exist(self, tmp_logger):
        conn = sqlite3.connect(tmp_logger.db_path)
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_audit_%'"
        )
        names = {r[0] for r in cur.fetchall()}
        assert "idx_audit_generation" in names
        assert "idx_audit_skill" in names
        assert "idx_audit_timestamp" in names


class TestLogging:
    def test_log_returns_rowid(self, tmp_logger):
        rid = tmp_logger.log(
            generation=1,
            skill_name="test-skill",
            model_used="minimax/minimax-m2.7",
            task_id="t1",
            expected_behavior="e",
            actual_behavior="a",
            rubric="r",
            raw_score=0.85,
        )
        assert rid > 0

    def test_log_error(self, tmp_logger):
        rid = tmp_logger.log_error(
            generation=1,
            skill_name="test-skill",
            model_used="minimax/minimax-m2.7",
            task_id="t1",
            expected_behavior="e",
            rubric="r",
            error_flag="NameError",
        )
        assert rid > 0
        rows = tmp_logger.get_recent(skill_name="test-skill")
        assert rows[0]["actual_behavior"] == "[ERROR]"
        assert rows[0]["raw_score"] == 0.0
        assert rows[0]["error_flag"] == "NameError"

    def test_duplicate_calls_are_append_only(self, tmp_logger):
        params = dict(
            generation=1,
            skill_name="test-skill",
            model_used="minimax/minimax-m2.7",
            task_id="t1",
            expected_behavior="e",
            actual_behavior="a",
            rubric="r",
            raw_score=0.85,
        )
        rid1 = tmp_logger.log(**params)
        rid2 = tmp_logger.log(**params)
        assert rid1 > 0
        assert rid2 > rid1
        assert len(tmp_logger.get_recent(skill_name="test-skill", limit=10)) == 2

    def test_get_recent_filtering(self, tmp_logger):
        for i in range(5):
            tmp_logger.log(
                generation=i + 1,
                skill_name="skill-a" if i % 2 == 0 else "skill-b",
                model_used="minimax/minimax-m2.7",
                task_id=f"t{i}",
                expected_behavior="e",
                actual_behavior="a",
                rubric="r",
                raw_score=0.8,
            )
        rows = tmp_logger.get_recent(skill_name="skill-a", limit=10)
        assert len(rows) == 3
        assert all(r["skill_name"] == "skill-a" for r in rows)


class TestStats:
    def test_summary_stats_empty(self, tmp_logger):
        stats = tmp_logger.summary_stats()
        assert stats["total_calls"] == 0
        assert stats["error_rate"] == 0.0
        assert stats["mean_score"] is None

    def test_mean_and_std(self, tmp_logger):
        scores = [0.2, 0.4, 0.6, 0.8, 1.0]
        for i, s in enumerate(scores):
            tmp_logger.log(
                generation=1,
                skill_name="test",
                model_used="m",
                task_id=f"t{i}",
                expected_behavior="e",
                actual_behavior="a",
                rubric="r",
                raw_score=s,
            )
        assert tmp_logger.mean_score() == pytest.approx(0.6, rel=1e-3)
        assert tmp_logger.std_score() == pytest.approx(np.std(scores, ddof=1), rel=1e-3)

    def test_std_score_less_than_two_rows(self, tmp_logger):
        tmp_logger.log(
            generation=1, skill_name="test", model_used="m", task_id="t1",
            expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
        )
        assert tmp_logger.std_score() is None

    def test_error_rate_calculation(self, tmp_logger):
        for i in range(4):
            tmp_logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"ok{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.8,
            )
        tmp_logger.log_error(
            generation=1, skill_name="test", model_used="m", task_id="err",
            expected_behavior="e", rubric="r", error_flag="ValueError",
        )
        assert tmp_logger.error_rate() == pytest.approx(1 / 5)

    def test_numeric_zero_error_flag_is_not_counted_as_error(self, tmp_logger):
        for idx, flag in enumerate([None, 0, "0", ""]):
            tmp_logger.log(
                generation=1,
                skill_name="calibration",
                model_used="manual",
                task_id=f"ok{idx}",
                expected_behavior="e",
                actual_behavior="a",
                rubric="r",
                raw_score=0.25 + (idx * 0.1),
                error_flag=flag,
            )
        tmp_logger.log_error(
            generation=1,
            skill_name="calibration",
            model_used="manual",
            task_id="err",
            expected_behavior="e",
            rubric="r",
            error_flag="ValueError",
        )

        assert tmp_logger.error_rate() == pytest.approx(1 / 5)
        assert tmp_logger.summary_stats()["error_calls"] == 1
        assert tmp_logger.count_errors() == {"ValueError": 1}
        assert tmp_logger.mean_score() == pytest.approx(np.mean([0.25, 0.35, 0.45, 0.55]))

    def test_dead_zone_fraction(self, tmp_logger):
        # 2 in dead zone (0.01, 0.99), 2 not (0.3, 0.7)
        for s in [0.01, 0.3, 0.7, 0.99]:
            tmp_logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"t{s}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=s,
            )
        assert tmp_logger.dead_zone_fraction() == pytest.approx(0.5)

    def test_generations_with_data(self, tmp_logger):
        for g in [1, 3, 5]:
            tmp_logger.log(
                generation=g, skill_name="test", model_used="m", task_id=f"t{g}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
            )
        assert tmp_logger.generations_with_data() == [1, 3, 5]
        assert tmp_logger.latest_generation() == 5

    def test_total_cost(self, tmp_logger):
        for i, cost in enumerate([0.001, 0.002, None, 0.003]):
            tmp_logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"t{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
                token_cost_estimate=cost,
            )
        assert tmp_logger.total_cost() == pytest.approx(0.006, rel=1e-6)


class TestSkillBodyHash:
    def test_hash_short(self, tmp_logger):
        h = tmp_logger.skill_body_hash("hello world")
        assert len(h) == 12
        assert h == tmp_logger.skill_body_hash("hello world")
        assert h != tmp_logger.skill_body_hash("different")


class TestThreadSafety:
    def test_concurrent_logging(self, tmp_logger):
        errors = []

        def worker(n):
            try:
                for i in range(20):
                    tmp_logger.log(
                        generation=1,
                        skill_name="concurrent",
                        model_used="m",
                        task_id=f"t{n}_{i}",
                        expected_behavior="e",
                        actual_behavior="a",
                        rubric="r",
                        raw_score=0.5,
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        stats = tmp_logger.summary_stats(skill_name="concurrent")
        assert stats["total_calls"] == 100


class TestSingleton:
    def test_singleton_same_db(self):
        # Reset singleton for this test
        import evolution.core.observatory.logger as log_mod
        log_mod._instance = None
        l1 = log_mod.get_logger()
        l2 = log_mod.get_logger()
        assert l1 is l2
        assert l1.db_path == l2.db_path

    def test_log_judge_call_convenience(self):
        import evolution.core.observatory.logger as log_mod
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "conv.db"
            log_mod._instance = None
            logger = log_mod.get_logger(db_path=db)
            rid = log_judge_call(
                generation=1,
                skill_name="conv-skill",
                model_used="m",
                task_id="t1",
                expected_behavior="e",
                actual_behavior="a",
                rubric="r",
                raw_score=0.77,
                skill_body="body text here",
            )
            assert rid > 0
            rows = logger.get_recent(skill_name="conv-skill")
            assert rows[0]["raw_score"] == pytest.approx(0.77)
            # SHA1 prefix of "body text here"
            assert rows[0]["skill_body_hash"] is not None
            assert len(rows[0]["skill_body_hash"]) == 12
