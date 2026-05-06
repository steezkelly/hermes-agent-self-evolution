"""ROI Circuit Breaker — stops repeated zero-improvement evolution runs.

Stateful gate that tracks (improvement, cost) per skill across runs.
If a skill has had 3 consecutive runs with improvement < threshold,
future runs are blocked (open circuit). The breaker auto-resets if
enough time passes or if the user overrides.

This lives in the Observatory but is conceptually "Phase 3" — it
consumes the cost data that token_cost.py now provides.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


_DEFAULT_DB = lambda: (Path(__file__).parent.parent.parent.parent / "output" / "judge_audit_log.db")


@dataclass(frozen=True)
class RunRecord:
    """One evolution run's ROI summary."""
    skill_name: str
    timestamp: datetime
    improvement: float        # delta score (evolved - baseline)
    total_cost: float       # USD spent on judge calls this run
    baseline_score: float
    evolved_score: float
    iterations: int
    halted: bool = False    # was this run itself halted by the breaker?


class ROICircuitBreaker:
    """Stateful circuit breaker: open after 3 zero-ROI runs for a skill."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        window: int = 3,
        min_improvement: float = 0.005,
        min_cost_threshold: float = 0.01,     # must spend > 1¢ to count as a \"real\" run
        cooldown_days: int = 7,
    ):
        self.db_path = db_path or _DEFAULT_DB()
        self.window = window
        self.min_improvement = min_improvement
        self.min_cost_threshold = min_cost_threshold
        self.cooldown = timedelta(days=cooldown_days)
        self._init_db()

    def _init_db(self) -> None:
        """Create roi_history table if missing."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roi_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                improvement REAL NOT NULL,
                total_cost REAL NOT NULL,
                baseline_score REAL NOT NULL,
                evolved_score REAL NOT NULL,
                iterations INTEGER NOT NULL DEFAULT 0,
                halted INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            )
        """)
        conn.commit()
        conn.close()

    def record_run(
        self,
        skill_name: str,
        improvement: float,
        baseline_score: float,
        evolved_score: float,
        iterations: int,
        total_cost: float,
        notes: str = "",
    ) -> None:
        """Log a completed run so the breaker can reason about it later."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO roi_history
            (skill_name, timestamp, improvement, total_cost,
             baseline_score, evolved_score, iterations, halted, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            skill_name,
            datetime.utcnow().isoformat(),
            improvement,
            total_cost,
            baseline_score,
            evolved_score,
            iterations,
            0,
            notes,
        ))
        conn.commit()
        conn.close()

    def compute_run_cost(self, skill_name: str, since: Optional[datetime] = None) -> float:
        """Sum token_cost_estimate from judge_audit_log for this skill's latest run.

        If `since` is given, sums from that timestamp. Otherwise sums the
        most recent contiguous block of rows for this skill (heuristic:
        all rows within the last 2 hours for this skill).
        """
        conn = sqlite3.connect(self.db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "judge_audit_log" not in tables:
            conn.close()
            return 0.0
        if since:
            row = conn.execute(
                "SELECT SUM(token_cost_estimate) FROM judge_audit_log "
                "WHERE skill_name = ? AND timestamp >= ? AND token_cost_estimate IS NOT NULL",
                (skill_name, since.isoformat()),
            ).fetchone()
        else:
            # Last 2-hour window for this skill
            cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
            row = conn.execute(
                "SELECT SUM(token_cost_estimate) FROM judge_audit_log "
                "WHERE skill_name = ? AND timestamp >= ? AND token_cost_estimate IS NOT NULL",
                (skill_name, cutoff),
            ).fetchone()
        conn.close()
        return float(row[0]) if row and row[0] else 0.0

    def recent_runs(self, skill_name: str, limit: int = 10) -> list[RunRecord]:
        """Return most recent runs for a skill, newest first."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM roi_history WHERE skill_name = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (skill_name, limit),
        ).fetchall()
        conn.close()
        return [
            RunRecord(
                skill_name=r["skill_name"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                improvement=r["improvement"],
                total_cost=r["total_cost"],
                baseline_score=r["baseline_score"],
                evolved_score=r["evolved_score"],
                iterations=r["iterations"],
                halted=bool(r["halted"]),
            )
            for r in rows
        ]

    def _should_open(self, skill_name: str, records: list[RunRecord]) -> tuple[bool, str]:
        """Core logic: open the circuit if the last `window` runs have zero ROI."""
        recent = [r for r in records if r.skill_name == skill_name][: self.window]
        if len(recent) < self.window:
            return False, f"Only {len(recent)}/{self.window} prior runs — not enough data"

        worthless = 0
        for r in recent:
            if r.halted:
                continue
            delta = r.improvement
            cost = r.total_cost
            # Must have cost > threshold AND delta < min_improvement
            if cost >= self.min_cost_threshold and delta < self.min_improvement:
                worthless += 1
            elif cost < self.min_cost_threshold:
                # Cheap runs don't count toward the breaker
                pass
            else:
                # Reset counter on any meaningful improvement
                return False, f"Recent improvement +{delta:.4f} resets breaker window"

        if worthless >= self.window:
            return True, (
                f"Circuit OPEN for '{skill_name}': {worthless} consecutive runs "
                f"costing ≥{self.min_cost_threshold}$ with improvement < {self.min_improvement}. "
                f"Last improvement: {recent[0].improvement:+.4f}. Wait {self.cooldown.days} days or override."
            )
        return False, (
            f"Circuit CLOSED: {worthless}/{self.window} worthless runs recently"
        )

    def check(self, skill_name: str) -> tuple[bool, str]:
        """Check whether the circuit is open for a skill.

        Returns (is_open, explanation_message).
        If open, the caller should refuse to start evolution.
        """
        records = self.recent_runs(skill_name, limit=self.window + 2)
        if not records:
            return False, f"No prior runs for '{skill_name}' — circuit closed."

        # Cooldown: if the most recent record is older than cooldown, reset
        newest = max(r.timestamp for r in records)
        if datetime.utcnow() - newest > self.cooldown:
            return False, (
                f"Circuit RESET for '{skill_name}': last run {newest.isoformat()} "
                f"is older than {self.cooldown.days}-day cooldown."
            )

        return self._should_open(skill_name, records)

    def override(self, skill_name: str, reason: str) -> None:
        """Manually override the breaker: record a synthetic \"forced\" entry."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO roi_history
            (skill_name, timestamp, improvement, total_cost,
             baseline_score, evolved_score, iterations, halted, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            skill_name,
            datetime.utcnow().isoformat(),
            999.0,  # sentinel improvement to break the window
            0.0,
            0.0,
            0.0,
            0,
            0,
            f"MANUAL OVERRIDE: {reason}",
        ))
        conn.commit()
        conn.close()

    def status(self, skill_name: str) -> dict:
        """Human-readable summary of a skill's ROI history."""
        records = self.recent_runs(skill_name, limit=10)
        is_open, msg = self.check(skill_name)
        return {
            "skill": skill_name,
            "circuit_open": is_open,
            "message": msg,
            "total_runs": len(records),
            "recent_improvements": [r.improvement for r in records[:5]],
            "recent_costs": [r.total_cost for r in records[:5]],
            "last_run": records[0].timestamp.isoformat() if records else None,
        }
