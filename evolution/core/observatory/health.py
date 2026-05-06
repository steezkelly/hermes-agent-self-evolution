"""Judge Health Monitor — Phase 1 of the GEPA Observatory.

Monitors judge health using the audit log. Implements the alert thresholds
from the GEPA v3 brief:

    Alert thresholds:
        std_dev < 0.08 for 3+ generations:  Everyone scores the same. Judge broken or tasks too easy.
        mean      < 0.15 for 3+ generations:  All skills terrible or judge overly harsh.
        mean      > 0.90 for 3+ generations:  Judge is a rubber stamp. No selection pressure.
        error_rate > 0.5%:                     Judge is dying silently.

Usage:
    from evolution.core.observatory import JudgeHealthMonitor, JudgeAuditLogger

    logger = JudgeAuditLogger()
    monitor = JudgeHealthMonitor(logger)

    report = monitor.health_report(generations_since=3)
    print(report.format())

    alerts = monitor.check_alerts()
    if alerts:
        print("ALERTS:", alerts)
"""

from dataclasses import dataclass, field
from typing import Optional
from evolution.core.observatory.logger import JudgeAuditLogger, get_logger


# ─────────────────────────────────────────────────────────────────────────────
# Alert thresholds (from GEPA v3 brief)
# ─────────────────────────────────────────────────────────────────────────────

ALERT_THRESHOLDS = {
    "std_dev_floor":        0.08,   # std_dev below this for 3+ gens → broken judge
    "mean_ceiling":         0.90,   # mean above this for 3+ gens  → rubber stamp
    "mean_floor":           0.15,   # mean below this for 3+ gens  → harsh judge
    "error_rate_floor":     0.005,  # >0.5% error rate → judge dying
    "dead_zone_ceiling":    0.80,   # >80% of scores in dead zones → flat signal
}


@dataclass
class Alert:
    """A single health alert."""
    code: str
    message: str
    generations_affected: list[int]
    current_value: float
    threshold: float
    severity: str  # "critical" | "warning"


@dataclass
class HealthReport:
    """Complete judge health report for a set of generations."""
    generations: list[int]
    total_calls: int
    error_calls: int
    error_rate: float
    mean_score: Optional[float]
    std_score: Optional[float]
    dead_zone_fraction: float
    total_cost: float
    alerts: list[Alert] = field(default_factory=list)

    # Per-generation breakdown
    per_generation: dict[int, dict] = field(default_factory=dict)

    def format(self) -> str:
        """Human-readable report."""
        lines = [
            "=" * 60,
            "GEPA JUDGE HEALTH REPORT",
            "=" * 60,
            f"  Generations: {self.generations}",
            f"  Total judge calls: {self.total_calls}",
            f"  Errors:           {self.error_calls} ({self.error_rate:.2%})",
            f"  Mean score:       {self.mean_score:.4f}" if self.mean_score is not None else "  Mean score:       N/A",
            f"  Std-dev:           {self.std_score:.4f}" if self.std_score is not None else "  Std-dev:           N/A",
            f"  Dead-zone fraction:{self.dead_zone_fraction:.2%}",
            f"  Total cost:        ${self.total_cost:.4f}",
        ]
        if self.alerts:
            lines.append("")
            lines.append("  ALERTS:")
            for a in self.alerts:
                lines.append(f"    [{a.severity.upper()}] {a.code}: {a.message}")
                lines.append(f"      generations={a.generations_affected}, value={a.current_value:.4f}, threshold={a.threshold}")
        else:
            lines.append("")
            lines.append("  ✓ No alerts — judge appears healthy")
        lines.append("=" * 60)
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "generations": self.generations,
            "total_calls": self.total_calls,
            "error_calls": self.error_calls,
            "error_rate": self.error_rate,
            "mean_score": self.mean_score,
            "std_score": self.std_score,
            "dead_zone_fraction": self.dead_zone_fraction,
            "total_cost": self.total_cost,
            "alerts": [
                {"code": a.code, "severity": a.severity, "message": a.message,
                 "generations_affected": a.generations_affected,
                 "current_value": a.current_value, "threshold": a.threshold}
                for a in self.alerts
            ],
            "per_generation": self.per_generation,
        }


class JudgeHealthMonitor:
    """Monitor judge health using the audit log.

    Analyzes score distributions, error rates, and dead-zone fractions
    across generations and emits alerts when thresholds are breached.
    """

    def __init__(self, logger: Optional[JudgeAuditLogger] = None):
        self._logger = logger or get_logger()

    def health_report(
        self,
        generations_since: int = 0,
        skill_name: Optional[str] = None,
    ) -> HealthReport:
        """Build a health report covering generations >= generations_since."""
        gens = self._logger.generations_with_data()
        gens_since = [g for g in gens if g >= generations_since]

        if not gens_since:
            return HealthReport(
                generations=[],
                total_calls=0, error_calls=0, error_rate=0.0,
                mean_score=None, std_score=None,
                dead_zone_fraction=0.0, total_cost=0.0,
                alerts=[],
                per_generation={},
            )

        # Overall stats
        stats = self._logger.summary_stats(
            since_generation=generations_since,
            skill_name=skill_name,
        )
        mean = stats.get("mean_score")
        std = stats.get("std_score")

        # Per-generation breakdown
        per_gen: dict[int, dict] = {}
        for g in gens_since:
            g_stats = self._logger.summary_stats(
                since_generation=g,
                skill_name=skill_name,
            )
            per_gen[g] = {
                "total_calls": g_stats["total_calls"],
                "mean_score": g_stats["mean_score"],
                "std_score": g_stats["std_score"],
                "error_rate": g_stats["error_rate"],
            }

        # Dead zone fraction across all generations since
        dz_frac = self._logger.dead_zone_fraction(
            since_generation=generations_since,
            skill_name=skill_name,
        )

        # Check alerts
        alerts = self._check_alerts_for_generations(gens_since, skill_name)

        return HealthReport(
            generations=gens_since,
            total_calls=stats["total_calls"],
            error_calls=stats["error_calls"],
            error_rate=stats["error_rate"],
            mean_score=mean,
            std_score=std,
            dead_zone_fraction=dz_frac,
            total_cost=stats["total_cost"],
            alerts=alerts,
            per_generation=per_gen,
        )

    def check_alerts(self, skill_name: Optional[str] = None) -> list[Alert]:
        """Run all alert checks and return any active alerts."""
        gens = self._logger.generations_with_data()
        return self._check_alerts_for_generations(gens, skill_name)

    def _check_alerts_for_generations(
        self,
        generations: list[int],
        skill_name: Optional[str] = None,
    ) -> list[Alert]:
        """Check alert thresholds against a list of generations.

        A sustained alert requires 3+ consecutive generations to breach
        the same threshold in the same direction.
        """
        alerts: list[Alert] = []
        if not generations:
            return alerts

        t = ALERT_THRESHOLDS

        # ── std_dev floor (3+ generations below 0.08) ──────────────────────
        std_by_gen = {}
        for g in generations:
            stats = self._logger.summary_stats(since_generation=g, skill_name=skill_name)
            std_by_gen[g] = stats.get("std_score")

        std_alert_gens = [
            g for g in generations
            if std_by_gen.get(g) is not None and std_by_gen[g] < t["std_dev_floor"]
        ]
        if len(std_alert_gens) >= 3:
            # Check consecutive
            alert_gens = self._last_n_consecutive(std_alert_gens, n=3)
            if alert_gens:
                alerts.append(Alert(
                    code="STD_DEV_FLAT",
                    message="Std-dev < 0.08 for 3+ generations. Judge has no selection pressure — everyone scores the same.",
                    generations_affected=alert_gens,
                    current_value=std_by_gen[alert_gens[-1]],
                    threshold=t["std_dev_floor"],
                    severity="critical",
                ))

        # ── mean ceiling (3+ generations above 0.90) ───────────────────────
        mean_by_gen = {}
        for g in generations:
            mean = self._logger.mean_score(since_generation=g, skill_name=skill_name)
            mean_by_gen[g] = mean

        mean_alert_gens = [
            g for g in generations
            if mean_by_gen.get(g) is not None and mean_by_gen[g] > t["mean_ceiling"]
        ]
        if len(mean_alert_gens) >= 3:
            alert_gens = self._last_n_consecutive(mean_alert_gens, n=3)
            if alert_gens:
                alerts.append(Alert(
                    code="RUBBER_STAMP",
                    message="Mean score > 0.90 for 3+ generations. Judge is too lenient — no selection pressure.",
                    generations_affected=alert_gens,
                    current_value=mean_by_gen[alert_gens[-1]],
                    threshold=t["mean_ceiling"],
                    severity="critical",
                ))

        # ── mean floor (3+ generations below 0.15) ─────────────────────────
        harsh_alert_gens = [
            g for g in generations
            if mean_by_gen.get(g) is not None and mean_by_gen[g] < t["mean_floor"]
        ]
        if len(harsh_alert_gens) >= 3:
            alert_gens = self._last_n_consecutive(harsh_alert_gens, n=3)
            if alert_gens:
                alerts.append(Alert(
                    code="OVERLY_HARSH",
                    message="Mean score < 0.15 for 3+ generations. Judge is too harsh, or all skills are broken.",
                    generations_affected=alert_gens,
                    current_value=mean_by_gen[alert_gens[-1]],
                    threshold=t["mean_floor"],
                    severity="critical",
                ))

        # ── error rate floor (>0.5% errors) ────────────────────────────────
        error_rate = self._logger.error_rate(since_generation=0, skill_name=skill_name)
        if error_rate > t["error_rate_floor"]:
            alerts.append(Alert(
                code="JUDGE_ERRORS",
                message=f"Judge error rate {error_rate:.2%} exceeds 0.5%. Judge is dying silently.",
                generations_affected=generations[-3:] if len(generations) >= 3 else generations,
                current_value=error_rate,
                threshold=t["error_rate_floor"],
                severity="critical",
            ))

        # ── dead zone ceiling (>80% in dead zones) ─────────────────────────
        dz_frac = self._logger.dead_zone_fraction(since_generation=0, skill_name=skill_name)
        if dz_frac > t["dead_zone_ceiling"]:
            alerts.append(Alert(
                code="DEAD_ZONE",
                message=f"{dz_frac:.1%} of scores are in dead zones. Judge discrimination is broken.",
                generations_affected=generations[-3:] if len(generations) >= 3 else generations,
                current_value=dz_frac,
                threshold=t["dead_zone_ceiling"],
                severity="critical",
            ))

        return alerts

    @staticmethod
    def _last_n_consecutive(sorted_gens: list[int], n: int) -> list[int] | None:
        """Check if the last n items in sorted_gens are consecutive integers.

        Returns those n generations if so, else None.
        Used to detect *sustained* threshold breaches.
        """
        if len(sorted_gens) < n:
            return None
        tail = sorted_gens[-n:]
        # Consecutive means each differs by exactly 1
        if all(tail[i + 1] - tail[i] == 1 for i in range(n - 1)):
            return tail
        return None
