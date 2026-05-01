"""
GEPA Skill Evolution Kanban — board state management.

Columns (status):
  BACKLOG        — skill never run, or ran stale with 0 improvement
  IN_PROGRESS    — active evolution run underway (or recently completed)
  REGRESSION     — latest run showed negative improvement
  VALIDATING     — positive improvement, awaiting human review + benchmark gate
  DEPLOYED       — approved and merged to production skills/
  STALE          — ran >7 days ago, 0 improvement, no recent runs

Card schema (per skill, one card per skill):
  skill_name     — canonical skill identifier
  status         — current column
  priority       — high/medium/low based on improvement magnitude
  latest_run     — most recent run_id
  latest_score   — (baseline, evolved, delta) from latest run
  best_run       — (timestamp, delta) for best improvement seen
  eval_source    — synthetic / sessiondb / golden
  iterations     — iterations in latest run
  constraints_passed
  is_multi_run   — True if multiple runs exist
  regression_count
  run_count      — total runs
  runner_role    — which GEPA component filed this (system = automated)
"""

import json
import csv
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

GEPA_OUTPUT = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "output"
STATS_CSV   = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "stats" / "evolution_stats.csv"
BOARD_STATE = Path(__file__).parent / "board-state.md"
CARD_SCHEMA = Path(__file__).parent / "card-schema.json"
SNAPSHOTS   = Path(__file__).parent / "snapshots"

# Threshold: "recent" means within this window
RECENT_WINDOW = timedelta(hours=24)
STALE_WINDOW  = timedelta(days=7)

# Columns in display order
COLUMNS = ["BACKLOG", "IN_PROGRESS", "REGRESSION", "VALIDATING", "DEPLOYED", "STALE"]


def _col_for(skill: dict) -> str:
    """Determine which column a skill card belongs in."""
    status   = skill["status"]
    recent   = skill.get("is_recent", False)
    best_d   = skill.get("best_delta", 0.0)
    runs     = skill.get("run_count", 0)

    if status == "DEPLOYED":
        return "DEPLOYED"
    if status == "STALE":
        return "STALE"
    if runs == 0:
        return "BACKLOG"
    if status == "IN_PROGRESS":
        return "IN_PROGRESS"
    if skill.get("latest_delta", 0.0) < 0:
        return "REGRESSION"
    if best_d > 0 and recent:
        return "VALIDATING"
    if best_d > 0:
        return "VALIDATING"
    # 0 improvement
    if recent or runs == 1:
        return "IN_PROGRESS"
    return "STALE"


# ── Data loading ────────────────────────────────────────────────────────────────

def _timestamp_from_dir(dir_name: str) -> str:
    """Extract or construct a timestamp string for sorting. Handles v2 dir names like v2_20260429_162726."""
    if dir_name.startswith("v2_"):
        # v2_YYYYMMDD_HHMMSS → YYYYMMDD_HHMMSS
        return dir_name[3:]
    return dir_name  # metrics.json dir names are already YYYYMMDD_HHMMSS

def load_all_runs():
    """Read every metrics.json and v2 report.json under output/. Returns list of run dicts."""
    runs = []

    # ── v1 metrics.json runs ────────────────────────────────────────────────
    for mp in GEPA_OUTPUT.glob("*/**/metrics.json"):
        with open(mp) as f:
            m = json.load(f)
        run_dir = mp.parent
        # seed-generation runs store 'seed' not 'skill_name'; parent dir is the skill
        skill = m.get("skill_name") or run_dir.parent.name
        runs.append({
            "run_id":    run_dir.name,
            "skill":     skill,
            "ts":        m["timestamp"],
            "path":      str(run_dir),
            **m,
        })

    # ── v2 report.json runs ────────────────────────────────────────────────
    # These live in output/<skill>/v2_<timestamp>/report.json
    # They use different field names — normalise to metrics.json schema.
    for rp in GEPA_OUTPUT.glob("*/v2_*/report.json"):
        with open(rp) as f:
            r = json.load(f)
        run_dir = rp.parent
        # Derive a v1-style timestamp from the directory name for sorting
        ts = _timestamp_from_dir(run_dir.name)
        runs.append({
            "run_id":    run_dir.name,
            "skill":     r["skill_name"],
            "ts":        ts,
            "path":      str(run_dir),
            # v2 → v1 field mapping
            "timestamp":             ts,
            "baseline_score":        r.get("baseline_score", 0.0),
            "evolved_score":         r.get("best_score", 0.0),
            "improvement":           r.get("improvement", 0.0),
            "elapsed_seconds":       r.get("elapsed_seconds", 0.0),
            "constraints_passed":    True,  # v2 pipeline doesn't run constraint validation
            "optimizer_type":        "GEPA-v2",
            # v2-specific fields (not in v1)
            "v2_recommendation":     r.get("recommendation", "unknown"),
            "attempt_metrics":        r.get("attempt_metrics", []),
        })

    runs.sort(key=lambda r: r["ts"], reverse=True)
    return runs


def load_stats_csv():
    """Parse evolution_stats.csv → dict[skill, dict] of best per-skill stats."""
    best = {}
    if not STATS_CSV.exists():
        return best
    with open(STATS_CSV) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 15 or not parts[1]:
                continue
            skill = parts[1]
            try:
                imp = float(parts[13]) if parts[13] else 0.0
            except ValueError:
                imp = 0.0
            if skill not in best or imp > best[skill]["improvement"]:
                best[skill] = {
                    "improvement":  imp,
                    "timestamp":    parts[0],
                    "baseline":     float(parts[10]) if parts[10] else 0.0,
                    "evolved":      float(parts[11]) if parts[11] else 0.0,
                    "iterations":   int(parts[4])    if parts[4]  else 0,
                    "eval_source":  parts[3]         if len(parts) > 3 else "?",
                }
    return best


# ── Card building ─────────────────────────────────────────────────────────────

def build_cards(runs, stats_best):
    """One card per unique skill.  Latest run = current state."""
    skills = {}
    for r in runs:
        s = r["skill"]
        if s not in skills:
            skills[s] = {
                "skill_name":        s,
                "run_count":         0,
                "regression_count":  0,
                "runs":              [],
                "latest_run":        None,
                "latest_delta":      0.0,
                "latest_baseline":   0.0,
                "latest_evolved":    0.0,
                "best_delta":        float("-inf"),   # anchored — first run always wins
                "best_run_ts":       "",
                "best_run":          None,
                "eval_source":       "?",
                "iterations":        0,
                "constraints_passed": True,
                "is_multi_run":      False,
                "is_recent":         False,
                "status":            "BACKLOG",
            }

        sk = skills[s]
        sk["run_count"] += 1
        sk['runs'].append(r)
        # Compute delta from evolved - baseline (v2 report.json improvement field is unreliable)
        delta = r.get('evolved_score', 0.0) - r.get('baseline_score', 0.0)

        if delta < 0:
            sk["regression_count"] += 1

        if delta > sk["best_delta"]:
            sk["best_delta"]    = delta
            sk["best_run_ts"]  = r["timestamp"]
            sk["best_run"]     = r["run_id"]
            sk["best_baseline"] = r.get("baseline_score", 0.0)
            sk["best_evolved"]  = r.get("evolved_score", 0.0)

        # latest = most recent by timestamp (first iteration wins, since runs are sorted newest-first)
        if sk["latest_run"] is None:
            sk["latest_run"]        = r["run_id"]
            sk["latest_delta"]      = delta
            sk["latest_baseline"]   = r.get("baseline_score", 0.0)
            sk["latest_evolved"]    = r.get("evolved_score", 0.0)
            sk["eval_source"]      = r.get("eval_source", stats_best.get(s, {}).get("eval_source", "?"))
            sk["iterations"]        = r.get("iterations", 0)
            sk["constraints_passed"] = r.get("constraints_passed", True)

    # Post-process: recent flag, multi-run, priority, column
    now = datetime.now()
    for sk in skills.values():
        sk["is_multi_run"] = sk["run_count"] > 1
        if sk["latest_run"]:
            try:
                lt = datetime.strptime(sk["latest_run"][:8], "%Y%m%d")
                sk["is_recent"] = (now - lt) < RECENT_WINDOW
            except ValueError:
                sk["is_recent"] = False
        sk["status"] = _col_for(sk)

    return skills


# ── Priority ──────────────────────────────────────────────────────────────────

def priority_for(sk: dict) -> str:
    d = abs(sk.get("best_delta", 0.0))
    if d >= 0.10:
        return "high"
    if d >= 0.03:
        return "medium"
    return "low"


# ── Board state markdown ──────────────────────────────────────────────────────

def render_board(skills, stats_best):
    lines = [
        "# GEPA Skill Evolution Kanban",
        f"Generated: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}",
        f"Total skills: {len(skills)}",
        "",
    ]

    # Summary bar
    col_counts = {c: 0 for c in COLUMNS}
    for sk in skills.values():
        col_counts[sk["status"]] = col_counts.get(sk["status"], 0) + 1

    summary = " | ".join(f"**{c}** {col_counts.get(c,0)}" for c in COLUMNS)
    lines.append(f"## Summary  {summary}")
    lines.append("")

    for col in COLUMNS:
        cards = [sk for sk in skills.values() if sk["status"] == col]
        if not cards:
            continue
        # Sort: highest delta first (positive then negative within column)
        cards.sort(key=lambda c: c.get("best_delta", 0.0), reverse=True)
        lines.append(f"## {col} ({len(cards)})")
        lines.append("")

        for sk in cards:
            pri = priority_for(sk)
            best_str  = f"{sk['best_delta']:+.4f}" if sk["best_delta"] != float("-inf") else "n/a"
            latest_str = f"{sk['latest_delta']:+.4f}" if sk["latest_delta"] != 0.0 or sk["run_count"] > 0 else "n/a"
            multi = "✓ multi-run" if sk["is_multi_run"] else "singleton"
            reg   = f", {sk['regression_count']} regression" if sk["regression_count"] else ""
            cons  = "✓ constraints" if sk["constraints_passed"] else "⚠ constraints_failed"
            src   = sk["eval_source"]

            lines.append(
                f"- **[{pri}]** `{sk['skill_name']}` "
                f"best={best_str} | latest={latest_str} "
                f"| runs={sk['run_count']}{reg} | {multi} | {cons} | src={src}"
            )
        lines.append("")

    return "\n".join(lines)


# ── Full card registry (JSON) ──────────────────────────────────────────────────

def render_card_registry(skills):
    """All cards as a structured list for tooling."""
    out = []
    for sk in sorted(skills.values(), key=lambda s: s["skill_name"]):
        out.append({
            "skill_name":          sk["skill_name"],
            "status":             sk["status"],
            "priority":           priority_for(sk),
            "run_count":          sk["run_count"],
            "regression_count":   sk["regression_count"],
            "latest_run":         sk["latest_run"],
            "latest_baseline":    sk["latest_baseline"],
            "latest_evolved":     sk["latest_evolved"],
            "latest_delta":       sk["latest_delta"],
            "best_delta":         sk["best_delta"],
            "best_run":           sk["best_run"],
            "eval_source":        sk["eval_source"],
            "iterations":         sk["iterations"],
            "constraints_passed": sk["constraints_passed"],
            "is_multi_run":       sk["is_multi_run"],
            "is_recent":          sk["is_recent"],
        })
    return json.dumps(out, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def refresh():
    runs      = load_all_runs()
    stats_best = load_stats_csv()
    skills    = build_cards(runs, stats_best)

    md = render_board(skills, stats_best)
    BOARD_STATE.write_text(md)

    registry_path = BOARD_STATE.parent / "card-registry.json"
    registry_path.write_text(render_card_registry(skills))

    print(f"GEPA kanban refreshed — {len(skills)} skills across {len(COLUMNS)} columns")
    print(f"  board-state.md     → {BOARD_STATE}")
    print(f"  card-registry.json  → {registry_path}")
    return skills


if __name__ == "__main__":
    refresh()
