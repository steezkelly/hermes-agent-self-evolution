#!/usr/bin/env python3
"""GEPA Observatory CLI — Phase 1.

Inspect judge audit logs and health metrics from the command line.

Invocation (from the evolution repo root):
    cd ~/hermes0/hermes-agent-self-evolution
    python -m evolution.core.observatory.cli --help

    # Health report
    python -m evolution.core.observatory.cli health

    # Stats per skill/generation
    python -m evolution.core.observatory.cli stats --skill github-code-review

    # Show recent judge calls
    python -m evolution.core.observatory.cli log --limit 20

    # Pre-run calibration (Phase 2)
    python -m evolution.core.observatory.cli calibrate --skill github-code-review

    # Tier-2 appeals audit (Phase 2)
    python -m evolution.core.observatory.cli appeals --skill github-code-review
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Add the repo root to the path so 'evolution.*' imports resolve
_repo_root = Path(__file__).parent.parent.parent.parent.resolve()
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def cmd_health(args) -> int:
    """Run judge health report."""
    from evolution.core.observatory.logger import JudgeAuditLogger as JAL
    from evolution.core.observatory.health import JudgeHealthMonitor
    db_path = Path(args.db_path) if args.db_path else None
    logger = JAL(db_path=db_path) if db_path else JAL()
    monitor = JudgeHealthMonitor(logger)

    skill_filter = args.skill if hasattr(args, "skill") and args.skill else None
    generation_filter = args.generation if hasattr(args, "generation") and args.generation else None

    # generations_since: include all generations up to and including the filter
    gens_since = 0 if generation_filter is None else generation_filter
    report = monitor.health_report(
        generations_since=gens_since,
        skill_name=skill_filter,
    )
    if args.json:
        import json
        print(json.dumps(report.as_dict(), indent=2, default=str))
    else:
        print(_format_health_report(report, logger.db_path))
    return 0 if not report.alerts else 1


def cmd_stats(args) -> int:
    """Print per-skill, per-generation score statistics using the logger's API."""
    from evolution.core.observatory.logger import JudgeAuditLogger as JAL
    db_path = Path(args.db_path) if args.db_path else None
    logger = JAL(db_path=db_path) if db_path else JAL()

    skill_filter = args.skill if args.skill else None
    generation_filter = args.generation if args.generation else None

    # Use the logger's built-in summary_stats which handles SQLite portability
    try:
        stats = logger.summary_stats(skill_name=skill_filter)
    except Exception as exc:
        print(f"Query error: {exc}")
        return 0

    # Fetch per-generation breakdown
    conn = logger.connection()
    query = """
        SELECT skill_name, generation, COUNT(*) as n,
               ROUND(AVG(raw_score), 4) as mean_score,
               ROUND(AVG(latency_ms), 1) as mean_latency_ms,
               SUM(CASE WHEN error_flag IS NOT NULL THEN 1 ELSE 0 END) as n_errors
        FROM   judge_audit_log
        WHERE  (:skill IS NULL OR skill_name = :skill)
          AND  (:generation IS NULL OR generation = :generation)
        GROUP BY skill_name, generation
        ORDER BY skill_name, generation
    """
    try:
        rows = conn.execute(query, {"skill": skill_filter, "generation": generation_filter}).fetchall()
    except Exception as exc:
        print(f"Query error (audit log may be empty or uninitialised): {exc}")
        return 0

    if not rows:
        print("No audit records found.")
        return 0

    print(f"{'skill':<30} {'gen':>4} {'n':>6} {'mean':>7} {'latency_ms':>11} {'errors':>6}")
    print("-" * 72)
    for r in rows:
        print(f"{r.skill_name:<30} {r.generation:>4} {r.n:>6} {r.mean_score:>7.4f} "
              f"{r.mean_latency_ms:>11.1f} {r.n_errors:>6}")

    return 0


def cmd_log(args) -> int:
    """Show recent judge call log entries."""
    from evolution.core.observatory.logger import JudgeAuditLogger as JAL
    db_path = Path(args.db_path) if args.db_path else None
    logger = JAL(db_path=db_path) if db_path else JAL()
    conn = logger.connection()
    log_query = """
        SELECT timestamp, skill_name, generation, model_used,
               ROUND(raw_score, 4) as score, latency_ms, error_flag
        FROM   judge_audit_log
        ORDER BY timestamp DESC
        LIMIT  :limit
    """
    try:
        rows = conn.execute(log_query, {"limit": args.limit}).fetchall()
    except Exception as exc:
        print(f"Query error (audit log may be empty or uninitialised): {exc}")
        return 0

    if not rows:
        print("No audit records found.")
        return 0

    print(f"{'timestamp':<26} {'skill':<25} {'gen':>4} {'model':<20} {'score':>6} {'ms':>6} {'error'}")
    print("-" * 100)
    for r in rows:
        flag = f"[{r.error_flag}]" if r.error_flag else ""
        model_short = r.model_used.split("/")[-1] if r.model_used else ""
        print(f"{r.timestamp:<26} {r.skill_name[:25]:<25} {r.generation:>4} "
              f"{model_short:<20} {r.score:>6.4f} {r.latency_ms:>6} {flag}")

    return 0


def cmd_calibrate(args) -> int:
    """Run pre-run calibration (Phase 2)."""
    from evolution.core.observatory.logger import JudgeAuditLogger as JAL
    from evolution.core.observatory.calibrator import CalibrationRunner
    db_path = Path(args.db_path) if args.db_path else None
    logger = JAL(db_path=db_path) if db_path else JAL()
    runner = CalibrationRunner(logger)
    # Calibration requires a skill_body and degraded_body — use the skill from disk
    skill_name = args.skill
    skill_path = None
    for base in [Path.home() / ".hermes" / "skills", Path.home() / "hermes0" / "hermes-agent-self-evolution"]:
        candidate = base / skill_name
        if candidate.exists():
            skill_path = candidate
            break
        # Try .md extension
        for ext in ["", ".md"]:
            candidate = base / f"{skill_name}{ext}"
            if candidate.exists():
                skill_path = candidate
                break

    if not skill_path:
        print(f"[calibrate] Skill '{skill_name}' not found.")
        return 1

    skill_text = skill_path.read_text()
    # Build degraded body: remove every 3rd paragraph
    paragraphs = skill_text.split("\n\n")
    degraded = "\n\n".join(p for i, p in enumerate(paragraphs) if (i % 3) != 2)
    if len(degraded) < len(skill_text) * 0.5:
        print(f"[calibrate] Skill '{skill_name}' too short to degrade meaningfully.")
        return 1

    # Generate 20 synthetic test tasks (simple placeholder tasks)
    tasks = [
        {
            "task_input": f"Test task {i+1} for skill {skill_name}",
            "expected_behavior": f"Correct execution of skill {skill_name} for test case {i+1}",
        }
        for i in range(20)
    ]

    result = runner.run(
        skill_body=skill_text,
        degraded_body=degraded,
        tasks=tasks,
        model="minimax/minimax-m2.7",
    )
    print(result.format())
    return 0 if result.is_acceptable() else 1


def cmd_appeals(args) -> int:
    """Run Tier-2 appeals audit (Phase 2)."""
    from evolution.core.observatory.logger import JudgeAuditLogger as JAL
    from evolution.core.observatory.appeals import Tier2Sampler
    db_path = Path(args.db_path) if args.db_path else None
    logger = JAL(db_path=db_path) if db_path else JAL()
    sampler = Tier2Sampler(logger)
    result = sampler.audit_skill(skill_name=args.skill)
    print(f"[appeals] skill={result.skill_name} sampled={result.n_sampled} "
          f"kappa={result.kappa:.4f} agreement={result.agreement_rate:.4f} "
          f"tier1_mean={result.tier1_mean:.4f} tier2_mean={result.tier2_mean:.4f}")
    print(f"  {result.message}")
    return 0 if result.sufficient else 1


def cmd_roi(args) -> int:
    """Check ROI circuit breaker status (Phase 3)."""
    from evolution.core.observatory.roi_circuit import ROICircuitBreaker
    breaker = ROICircuitBreaker()
    is_open, msg = breaker.check(args.skill)
    status = breaker.status(args.skill)
    print(f"[ROI] skill={args.skill} circuit_open={is_open}")
    print(f"  {msg}")
    print(f"  Total runs: {status['total_runs']}")
    print(f"  Recent improvements: {status['recent_improvements']}")
    print(f"  Recent costs: {status['recent_costs']}")
    return 0


def cmd_override(args) -> int:
    """Override ROI circuit breaker for a skill."""
    from evolution.core.observatory.roi_circuit import ROICircuitBreaker
    breaker = ROICircuitBreaker()
    breaker.override(args.skill, args.reason)
    print(f"[override] Circuit breaker overridden for {args.skill}")
    print(f"  Reason: {args.reason}")
    is_open, msg = breaker.check(args.skill)
    print(f"  New status: {msg}")
    return 0


def _format_health_report(report: HealthReport, db_path: Path) -> str:
    """Format a HealthReport as a readable string."""
    lines = [
        "=" * 60,
        "GEPA OBSERVATORY — Judge Health Report",
        "=" * 60,
        f"  Generations      : {report.generations}",
        f"  Total judge calls: {report.total_calls:>8}",
        f"  Error calls      : {report.error_calls:>8} ({report.error_rate:.2%})",
        f"  Score mean       : {report.mean_score:>8.4f}" if report.mean_score is not None else "  Score mean       : N/A",
        f"  Score std-dev    : {report.std_score:>8.4f}" if report.std_score is not None else "  Score std-dev   : N/A",
        f"  Dead-zone fract. : {report.dead_zone_fraction:>8.2%}",
        f"  Total cost       : ${report.total_cost:>8.4f}",
        "",
    ]

    if report.alerts:
        lines.append(f"  ALERTS ({len(report.alerts)})")
        lines.append("-" * 40)
        for alert in report.alerts:
            severity = "!" if alert.severity == "critical" else "*"
            lines.append(f"  {severity} [{alert.severity:<10}] {alert.code}: {alert.message}")
            lines.append(f"      generations={alert.generations_affected}, value={alert.current_value:.4f}, threshold={alert.threshold}")
        lines.append("")
    else:
        lines.append("  [OK] No active alerts")
        lines.append("")

    if report.per_generation:
        lines.append("  Per-generation breakdown:")
        lines.append(f"  {'gen':>4} | {'calls':>6} | {'mean':>7} | {'std':>7} | {'error%':>7}")
        lines.append("  " + "-" * 42)
        for g, s in sorted(report.per_generation.items()):
            mean_str = f"{s['mean_score']:.4f}" if s.get('mean_score') is not None else "N/A"
            std_str = f"{s['std_score']:.4f}" if s.get('std_score') is not None else "N/A"
            err_str = f"{s['error_rate']:.2%}" if s.get('error_rate') is not None else "N/A"
            lines.append(f"  {g:>4} | {s.get('total_calls', 0):>6} | {mean_str:>7} | {std_str:>7} | {err_str:>7}")
        lines.append("")

    lines.append(f"  Audit log: {db_path}")
    if db_path and db_path.exists():
        lines[-1] += f" ({db_path.stat().st_size:,} bytes)"
    lines.append("=" * 60)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gepa-observatory",
        description="GEPA Observatory — judge audit logging and health monitoring.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to judge_audit_log.db (default: auto-discovered via GEPA_OUTPUT_DIR or ./output/).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # health
    p_health = sub.add_parser("health", help="Run judge health report and alert check.")
    p_health.add_argument("--skill", default=None, help="Filter by skill name.")
    p_health.add_argument("--generation", type=int, default=None, help="Filter by generation number.")
    p_health.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    p_health.set_defaults(func=cmd_health)

    # stats
    p_stats = sub.add_parser("stats", help="Per-skill, per-generation score statistics.")
    p_stats.add_argument("--skill", default=None, help="Filter by skill name.")
    p_stats.add_argument("--generation", type=int, default=None, help="Filter by generation number.")
    p_stats.set_defaults(func=cmd_stats)

    # log
    p_log = sub.add_parser("log", help="Show recent judge call log entries.")
    p_log.add_argument("--limit", type=int, default=20, help="Number of entries to show.")
    p_log.set_defaults(func=cmd_log)

    # calibrate (Phase 2)
    p_cal = sub.add_parser("calibrate", help="Run pre-run calibration batch (Phase 2).")
    p_cal.add_argument("--skill", required=True, help="Skill name to calibrate.")
    p_cal.set_defaults(func=cmd_calibrate)

    # appeals (Phase 2)
    p_ap = sub.add_parser("appeals", help="Run Tier-2 appeals audit (Phase 2).")
    p_ap.add_argument("--skill", required=True, help="Skill name to audit.")
    p_ap.set_defaults(func=cmd_appeals)

    # roi (Phase 3)
    p_roi = sub.add_parser("roi", help="Check ROI circuit breaker status (Phase 3).")
    p_roi.add_argument("--skill", required=True, help="Skill name to check.")
    p_roi.set_defaults(func=cmd_roi)

    # override (Phase 3)
    p_override = sub.add_parser("override", help="Override ROI circuit breaker for a skill.")
    p_override.add_argument("--skill", required=True, help="Skill name to override.")
    p_override.add_argument("--reason", default="manual override", help="Reason for override.")
    p_override.set_defaults(func=cmd_override)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
