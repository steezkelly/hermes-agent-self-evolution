"""Judge Audit Logger — Phase 1 of the GEPA Observatory.

Append-only SQLite table that logs every judge call:
    timestamp, generation, skill_name, model_used, task_id,
    expected_behavior, actual_behavior, rubric, raw_score,
    latency_ms, token_cost_estimate, error_flag

This is the foundation. Nothing else in the Observatory (health monitor,
Tier-2 appeals, ROI tracker) can function without this log.

Usage:
    from evolution.core.observatory import JudgeAuditLogger

    logger = JudgeAuditLogger()

    # Log a judge call
    logger.log(
        generation=1,
        skill_name="python-debugpy",
        model_used="minimax/minimax-m2.7",
        task_id="task-001",
        expected_behavior="Use pdb.set_trace() for inline breakpoints",
        actual_behavior="The response correctly identified set_trace() usage",
        rubric="Did the agent correctly reference the pdb API?",
        raw_score=0.95,
        latency_ms=1240,
        token_cost_estimate=0.003,
        error_flag=None,          # None = clean, "NameError" = error class
        skill_body_hash=None,      # optional: hash of the skill body evaluated
    )

    # Inspect recent health
    report = logger.health_report(generations_since=3)
    print(report)
"""

import json
import hashlib
import sqlite3
import threading
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# Database path — stored alongside GEPA output, not in ~/.hermes
# ─────────────────────────────────────────────────────────────────────────────

def _default_db_path() -> Path:
    """Discover the audit log path. Priority: GEPA_OUTPUT_DIR env, then
    ./output/ relative to the evolution package (matches EvolutionConfig)."""
    env_path = os.getenv("GEPA_OUTPUT_DIR")
    if env_path:
        p = Path(env_path)
    else:
        # Match EvolutionConfig default: ./output relative to package root
        p = Path(__file__).parent.parent.parent / "output"
    p.mkdir(parents=True, exist_ok=True)
    return p / "judge_audit_log.db"


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS judge_audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    generation      INTEGER NOT NULL,
    skill_name      TEXT    NOT NULL,
    model_used      TEXT    NOT NULL,
    task_id         TEXT    NOT NULL DEFAULT '',
    expected_behavior TEXT  NOT NULL,
    actual_behavior TEXT    NOT NULL,
    rubric          TEXT    NOT NULL,
    raw_score       REAL    NOT NULL,
    latency_ms      INTEGER,
    token_cost_estimate REAL,
    error_flag      TEXT,
    skill_body_hash TEXT,
    session_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_generation ON judge_audit_log(generation);
CREATE INDEX IF NOT EXISTS idx_audit_skill ON judge_audit_log(skill_name);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON judge_audit_log(timestamp);
"""


# ─────────────────────────────────────────────────────────────────────────────
# JudgeAuditLogger
# ─────────────────────────────────────────────────────────────────────────────

class JudgeAuditLogger:
    """Thread-safe, append-only SQLite audit logger for judge calls.

    Schema notes (2026-05-04):
    - task_id has NOT NULL DEFAULT '' — callers must NEVER pass None. The
      fitness.py layer normalizes None to "" before calling log().
    - No UNIQUE constraint on (generation, skill_name, task_id, model_used) to
      avoid IntegrityError during rapid-fire evaluations.
    - Journal mode is DELETE (not WAL) for single-writer safety.

    Singleton lifecycle warning:
    get_logger() caches the DB path at first import. If you change GEPA_OUTPUT_DIR
    and re-import without clearing __pycache__, the old DB path persists.

    Parameters
    ----------
    db_path : Path, optional
        Defaults to GEPA_OUTPUT_DIR/judge_audit_log.db or ./output/judge_audit_log.db
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path: Path = db_path or _default_db_path()
        self._lock = threading.RLock()
        self._init_db()

    # ─── Initialisation ───────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.commit()

    # ─── Logging ─────────────────────────────────────────────────────────────

    def log(
        self,
        generation: int,
        skill_name: str,
        model_used: str,
        task_id: str,
        expected_behavior: str,
        actual_behavior: str,
        rubric: str,
        raw_score: float,
        latency_ms: Optional[int] = None,
        token_cost_estimate: Optional[float] = None,
        error_flag: Optional[str] = None,
        skill_body_hash: Optional[str] = None,
        session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Log a single judge evaluation call.

        Returns the row ID on success. The audit log is intentionally append-only:
        repeated calls are recorded as distinct rows so rapid-fire evaluations are
        not collapsed or hidden.
        """
        ts = timestamp or datetime.utcnow().isoformat(timespec="milliseconds")

        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO judge_audit_log (
                        timestamp, generation, skill_name, model_used,
                        task_id, expected_behavior, actual_behavior,
                        rubric, raw_score, latency_ms, token_cost_estimate,
                        error_flag, skill_body_hash, session_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts, generation, skill_name, model_used,
                        task_id, expected_behavior, actual_behavior,
                        rubric, raw_score, latency_ms, token_cost_estimate,
                        error_flag, skill_body_hash, session_id,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except sqlite3.IntegrityError:
                # Duplicate — idempotent, no-op
                return -1

    def log_error(
        self,
        generation: int,
        skill_name: str,
        model_used: str,
        task_id: str,
        expected_behavior: str,
        rubric: str,
        error_flag: str,
        latency_ms: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        """Log a judge call that raised an exception.

        Records the error_flag so health monitors can detect judge death events.
        actual_behavior is set to "[ERROR]" to make queries easy.
        """
        return self.log(
            generation=generation,
            skill_name=skill_name,
            model_used=model_used,
            task_id=task_id,
            expected_behavior=expected_behavior,
            actual_behavior="[ERROR]",
            rubric=rubric,
            raw_score=0.0,
            latency_ms=latency_ms,
            token_cost_estimate=None,
            error_flag=error_flag,
            skill_body_hash=None,
            session_id=session_id,
        )

    # ─── Query helpers ───────────────────────────────────────────────────────

    def get_recent(
        self,
        generations: Optional[int] = None,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch recent audit log entries."""
        query = "SELECT * FROM judge_audit_log WHERE 1=1"
        params: list = []
        if generations is not None:
            query += " AND generation >= ?"
            params.append(generations)
        if skill_name is not None:
            query += " AND skill_name = ?"
            params.append(skill_name)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_errors(self, since_generation: int = 0) -> dict:
        """Return error counts by error class since the given generation."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT error_flag, COUNT(*) as cnt
                FROM judge_audit_log
                WHERE error_flag IS NOT NULL
                  AND error_flag != 0
                  AND error_flag != '0'
                  AND error_flag != ''
                  AND generation >= ?
                GROUP BY error_flag
                """,
                (since_generation,),
            ).fetchall()
            return {r["error_flag"]: r["cnt"] for r in rows}

    def error_rate(
        self,
        since_generation: int = 0,
        skill_name: Optional[str] = None,
    ) -> float:
        """Fraction of judge calls that errored since the given generation."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM judge_audit_log WHERE generation >= ?"
                + (" AND skill_name = ?" if skill_name else ""),
                ([since_generation] + ([skill_name] if skill_name else [])),
            ).fetchone()[0]
            if total == 0:
                return 0.0
            errors = conn.execute(
                "SELECT COUNT(*) FROM judge_audit_log "
                "WHERE error_flag IS NOT NULL AND error_flag != 0 AND error_flag != '0' AND error_flag != '' AND generation >= ?"
                + (" AND skill_name = ?" if skill_name else ""),
                ([since_generation] + ([skill_name] if skill_name else [])),
            ).fetchone()[0]
            return errors / total

    def mean_score(
        self,
        since_generation: int = 0,
        skill_name: Optional[str] = None,
    ) -> Optional[float]:
        """Mean score since the given generation (None if no data)."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            cond = "generation >= ?" + (" AND skill_name = ?" if skill_name else "")
            params = [since_generation] + ([skill_name] if skill_name else [])
            row = conn.execute(
                f"SELECT AVG(raw_score) as mean FROM judge_audit_log WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')",
                params,
            ).fetchone()
            return float(row[0]) if row[0] is not None else None

    def std_score(
        self,
        since_generation: int = 0,
        skill_name: Optional[str] = None,
    ) -> Optional[float]:
        """Sample std-dev of scores since the given generation (None if <2 rows)."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            cond = "generation >= ?" + (" AND skill_name = ?" if skill_name else "")
            params = [since_generation] + ([skill_name] if skill_name else [])
            scores = [
                row[0] for row in conn.execute(
                    f"SELECT raw_score FROM judge_audit_log WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')",
                    params,
                ).fetchall()
            ]
            if len(scores) < 2:
                return None
            return float(np.std(scores, ddof=1))

    def dead_zone_fraction(
        self,
        since_generation: int = 0,
        skill_name: Optional[str] = None,
    ) -> float:
        """Fraction of non-error scores in dead zones (0.00-0.05 or 0.95-1.00)."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            cond = "generation >= ?" + (" AND skill_name = ?" if skill_name else "")
            params = [since_generation] + ([skill_name] if skill_name else [])
            total = conn.execute(
                f"SELECT COUNT(*) FROM judge_audit_log WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')",
                params,
            ).fetchone()[0]
            if total == 0:
                return 0.0
            dead = conn.execute(
                f"""SELECT COUNT(*) FROM judge_audit_log
                    WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')
                      AND (raw_score <= 0.05 OR raw_score >= 0.95)""",
                params,
            ).fetchone()[0]
            return dead / total

    def generations_with_data(self) -> list[int]:
        """Return sorted list of generations that have at least one log entry."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            rows = conn.execute(
                "SELECT DISTINCT generation FROM judge_audit_log ORDER BY generation"
            ).fetchall()
            return [r[0] for r in rows]

    def latest_generation(self) -> Optional[int]:
        """Return the highest generation number in the log, or None if empty."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            row = conn.execute(
                "SELECT MAX(generation) FROM judge_audit_log"
            ).fetchone()
            return int(row[0]) if row[0] is not None else None

    def total_cost(self, since_generation: int = 0) -> float:
        """Sum of token_cost_estimate since the given generation."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            row = conn.execute(
                """SELECT SUM(token_cost_estimate) FROM judge_audit_log
                   WHERE generation >= ? AND token_cost_estimate IS NOT NULL""",
                (since_generation,),
            ).fetchone()
            return float(row[0]) if row[0] is not None else 0.0

    def summary_stats(
        self,
        since_generation: int = 0,
        skill_name: Optional[str] = None,
    ) -> dict:
        """Return a complete stats dict for health reporting."""
        with self._lock, sqlite3.connect(self._db_path, timeout=30) as conn:
            cond = "generation >= ?" + (" AND skill_name = ?" if skill_name else "")
            params = [since_generation] + ([skill_name] if skill_name else [])

            def fetchone(sql, p):
                r = conn.execute(sql, p).fetchone()
                return r[0] if r else None

            total = fetchone(
                f"SELECT COUNT(*) FROM judge_audit_log WHERE {cond}", params
            ) or 0
            errors = fetchone(
                f"SELECT COUNT(*) FROM judge_audit_log WHERE {cond} AND error_flag IS NOT NULL AND error_flag != 0 AND error_flag != '0' AND error_flag != '' ",
                params,
            ) or 0
            mean = fetchone(
                f"SELECT AVG(raw_score) FROM judge_audit_log WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')",
                params,
            )
            # Compute std-dev in Python (SQLite doesn't ship STDDEV by default)
            scores = [
                row[0] for row in conn.execute(
                    f"SELECT raw_score FROM judge_audit_log WHERE {cond} AND (error_flag IS NULL OR error_flag = 0 OR error_flag = '0' OR error_flag = '')",
                    params,
                ).fetchall()
            ]
            sd = float(np.std(scores, ddof=1)) if len(scores) >= 2 else None
            cost = fetchone(
                "SELECT SUM(token_cost_estimate) FROM judge_audit_log "
                "WHERE generation >= ? AND token_cost_estimate IS NOT NULL",
                [since_generation],
            ) or 0.0
            return {
                "total_calls": total,
                "error_calls": errors,
                "error_rate": errors / total if total > 0 else 0.0,
                "mean_score": float(mean) if mean is not None else None,
                "std_score": sd,
                "total_cost": float(cost),
                "generations": self.generations_with_data(),
            }

    # ─── Utility ─────────────────────────────────────────────────────────────

    @staticmethod
    def skill_body_hash(text: str) -> str:
        """Return a short SHA1 hex digest of a skill body for log correlation."""
        return hashlib.sha1(text.encode()).hexdigest()[:12]

    @property
    def db_path(self) -> Path:
        return self._db_path

    def connection(self):
        """Return a sqlite3 connection for read-only CLI queries.

        The caller must NOT write to the DB through this connection.
        Thread-safe via the internal lock.
        """
        with self._lock:
            return sqlite3.connect(self._db_path, timeout=30)

    def __repr__(self) -> str:
        return (
            f"JudgeAuditLogger(db={self._db_path.name}, "
            f"latest_gen={self.latest_generation()})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton + convenience decorator
# ─────────────────────────────────────────────────────────────────────────────

_instance: Optional[JudgeAuditLogger] = None
_instance_lock = threading.Lock()


def get_logger(db_path: Optional[Path] = None) -> JudgeAuditLogger:
    """Return the module-level JudgeAuditLogger singleton."""
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = JudgeAuditLogger(db_path=db_path)
        return _instance


def log_judge_call(
    generation: int,
    skill_name: str,
    model_used: str,
    task_id: str,
    expected_behavior: str,
    actual_behavior: str,
    rubric: str,
    raw_score: float,
    latency_ms: Optional[int] = None,
    token_cost_estimate: Optional[float] = None,
    error_flag: Optional[str] = None,
    skill_body: Optional[str] = None,
    session_id: Optional[str] = None,
) -> int:
    """Convenience function that logs to the singleton logger.

    This is the function you call from inside LLMJudge.score() and
    skill_fitness_metric(). Pass the skill_body for hash correlation;
    it is stored only as a 12-char prefix of its SHA1.
    """
    logger = get_logger()
    body_hash = logger.skill_body_hash(skill_body) if skill_body else None
    return logger.log(
        generation=generation,
        skill_name=skill_name,
        model_used=model_used,
        task_id=task_id,
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        rubric=rubric,
        raw_score=raw_score,
        latency_ms=latency_ms,
        token_cost_estimate=token_cost_estimate,
        error_flag=error_flag,
        skill_body_hash=body_hash,
        session_id=session_id,
    )
