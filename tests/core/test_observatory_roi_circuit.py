"""Unit tests for evolution.core.observatory.roi_circuit."""

import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from evolution.core.observatory.roi_circuit import ROICircuitBreaker, RunRecord


class TestROICircuitBreaker:

    def test_fresh_skill_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=3)
            is_open, msg = breaker.check("fresh")
            assert is_open is False
            assert "No prior runs" in msg

    def test_window_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=3, min_improvement=0.01)
            # 2 flat runs — not enough
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            is_open, msg = breaker.check("skill")
            assert is_open is False
            assert "Only 2/3" in msg

    def test_opens_after_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=2, min_improvement=0.01)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            is_open, msg = breaker.check("skill")
            assert is_open is True
            assert "Circuit OPEN" in msg

    def test_resets_on_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=2, min_improvement=0.01)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            breaker.record_run("skill", 0.10, 0.5, 0.6, 5, 0.50)
            is_open, msg = breaker.check("skill")
            assert is_open is False

    def test_override_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=2, min_improvement=0.01)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            breaker.record_run("skill", 0.0, 0.5, 0.5, 5, 0.50)
            breaker.override("skill", "forced")
            is_open, msg = breaker.check("skill")
            assert is_open is False

    def test_cooldown_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db, window=2, min_improvement=0.01, cooldown_days=0)
            old = (datetime.utcnow() - timedelta(days=1)).isoformat()
            conn = sqlite3.connect(db)
            conn.execute("INSERT INTO roi_history (skill_name, timestamp, improvement, total_cost, baseline_score, evolved_score, iterations, halted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        ("skill", old, 0.0, 0.5, 0.5, 0.5, 5, 0))
            conn.commit()
            conn.close()
            is_open, msg = breaker.check("skill")
            assert is_open is False
            assert "RESET" in msg

    def test_compute_run_cost_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db)
            c = breaker.compute_run_cost("nosuchskill")
            assert c == 0.0

    def test_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            breaker = ROICircuitBreaker(db_path=db)
            status = breaker.status("nosuchskill")
            assert status["circuit_open"] is False
            assert status["total_runs"] == 0
