"""GEPA Observatory — judge audit logging, health monitoring, and meta-evaluation.

Architecture:
    observatory/
        __init__.py       — exports public API
        context.py        — thread-safe evaluation context (generation, skill_name, task_id)
        logger.py         — SQLite audit table + log_judge_call()
        health.py         — score distribution analysis + alert thresholds
        calibrator.py     — pre-run calibration batch (Phase 2)
        appeals.py        — Tier-2 sampling + Cohen's Kappa (Phase 2)
"""

from evolution.core.observatory.logger import JudgeAuditLogger, log_judge_call
from evolution.core.observatory.health import JudgeHealthMonitor, HealthReport, Alert
from evolution.core.observatory.context import (
    set_evaluation_context,
    get_evaluation_context,
    update_context_latency,
    update_context_cost,
)
from evolution.core.observatory.calibrator import CalibrationRunner, CalibrationResult
from evolution.core.observatory.appeals import Tier2Sampler, cohens_kappa, Tier2AuditResult

__all__ = [
    # Core
    "JudgeAuditLogger",
    "log_judge_call",
    "JudgeHealthMonitor",
    "HealthReport",
    "Alert",
    # Context
    "set_evaluation_context",
    "get_evaluation_context",
    "update_context_latency",
    "update_context_cost",
    # Phase 2
    "CalibrationRunner",
    "CalibrationResult",
    "Tier2Sampler",
    "cohens_kappa",
    "Tier2AuditResult",
]
