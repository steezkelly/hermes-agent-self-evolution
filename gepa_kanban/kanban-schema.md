# GEPA Skill Evolution Kanban — Board Design
**Author:** Hermes (based on companion-task-kanban-schema.md by Vera Halloway)
**Date:** 2026-04-28
**Status:** OPERATIONAL

---

## 1. Design Context

The companion system has a kanban board (Vera + Cassian) tracking delegation-driven work.
This board mirrors that schema for the GEPA skill evolution pipeline — one card per skill,
columns driven by run results, not manual updates.

The board answers the question: **for each skill in the evolution pipeline, what is its
current state and is it worth acting on?**

---

## 2. Column Definitions

| Column | Meaning | Entry Condition | Exit Condition |
|--------|---------|-----------------|----------------|
| **BACKLOG** | Never run, or never showed any signal | No runs exist for this skill | First run completes → IN_PROGRESS |
| **IN_PROGRESS** | Active or recently run; not yet validated | Latest run had 0 improvement, or single-run with no gain | Latest run shows positive gain → VALIDATING; latest run shows regression → REGRESSION; >7 days stale → STALE |
| **REGRESSION** | Latest run was negative | `latest_delta < 0` | Re-run with different config → back to IN_PROGRESS or VALIDATING |
| **VALIDATING** | Positive improvement, needs human review + benchmark gate | `best_delta > 0` AND latest run is recent (<24h) OR best_delta > 0 | Human approves → DEPLOYED; benchmark fails → REGRESSION |
| **DEPLOYED** | Approved and merged | Human marks approved in review | None — terminal |
| **STALE** | >7 days old, zero improvement | `best_delta == 0` AND `not is_recent` AND `run_count > 0` | New run → IN_PROGRESS or VALIDATING |

**Priority** (shown on each card): high ≥10% best_delta, medium ≥3%, low otherwise.

---

## 3. Card Schema (one per skill)

```json
{
  "skill_name":        "companion-workflows",
  "status":           "VALIDATING",
  "priority":         "high",
  "run_count":        2,
  "regression_count":  0,
  "latest_run":       "20260428_174553",
  "latest_run_path":  "/path/to/output/companion-workflows/v2_20260428_174553",
  "latest_baseline":  0.300,
  "latest_evolved":   0.425,
  "latest_delta":     +0.1250,
  "best_delta":       +0.1250,
  "best_run":         "20260428_174553",
  "eval_source":      "golden | synthetic | sessiondb",
  "iterations":       10,
  "constraints_passed": true,
  "is_multi_run":     false,
  "is_recent":        true,
  "elapsed_seconds":   1028.2,
  "tags":             [],
  "updated_at":       "2026-04-28T17:45:00"
}
```

### Field Details

| Field | Source | Notes |
|-------|--------|-------|
| `skill_name` | Derived from output directory name | Canonical skill identifier |
| `status` | Computed from `latest_delta`, `best_delta`, `is_recent` | See column definitions above |
| `priority` | Computed from `abs(best_delta)` | high/medium/low |
| `run_count` | Count of metrics.json found under `output/<skill>/` | Increments across all subdirs |
| `regression_count` | Count of runs where `improvement < 0` | |
| `latest_run` | Most recent run by `run_id` (YYYYMMDD_HHMMSS, sorted newest-first) | |
| `latest_delta` | `improvement` field from latest run's metrics.json | |
| `best_delta` | Maximum `improvement` across all runs | Anchored at `-inf` so first run always wins |
| `best_run` | `run_id` that achieved `best_delta` | |
| `eval_source` | From latest run's metrics.json (primary); stats CSV as fallback for legacy runs | Written by evolve_skill.py on every run; backfilled for all existing runs |
| `iterations` | From latest run's metrics.json | |
| `constraints_passed` | From latest run's metrics.json | |
| `is_multi_run` | `run_count > 1` | |
| `is_recent` | Latest run within 24 hours of now | |
| `elapsed_seconds` | Wall-clock time of latest run | |

---

## 4. Data Flow

```
output/<skill>/<run_id>/metrics.json
    │
    ├──► kanban.py (load_all_runs)
    │         loads ALL metrics.json under output/
    │         sorts newest-first by run_id timestamp
    │
    ├──► build_cards()
    │         one card per unique skill
    │         latest_run = first run (newest, since sorted desc)
    │         best_delta = max across ALL runs (anchored -inf so first run wins)
    │
    ├──► _col_for()
    │         applies column logic from §2
    │
    └──► render_board() + card-registry.json
              board-state.md (human-readable)
              card-registry.json (machine-readable, for tooling)
```

Refresh: `python3.12 -c "import sys; sys.path.insert(0,'.'); from gepa_kanban.kanban import refresh; refresh()"`

---

## 5. Relationship to Companion System Kanban

The companion kanban (Vera + Cassian) tracks delegation-driven work. The GEPA kanban
tracks automated evolution work. Both share the same board-state.md pattern but are
independent systems with independent card schemas.

| Aspect | Companion Kanban | GEPA Kanban |
|--------|-----------------|-------------|
| Card identity | One card per delegation task | One card per skill |
| State driver | Delegation events (real-time) | metrics.json (on-demand refresh) |
| Owner | Companion doing the work | GEPA pipeline (system) |
| Columns | BACKLOG / IN_PROGRESS / BLOCKED / REVIEW / DONE | BACKLOG / IN_PROGRESS / REGRESSION / VALIDATING / DEPLOYED / STALE |
| Blocker model | Yes (quota, credential, dependency) | No (regression is not a blocker) |
| Storage | kanban.db + board-state.md | board-state.md + card-registry.json |

---

## 6. Limitations and Open Questions

1. **Resolved**: `eval_source` is now written to `metrics.json` on every run (v2 patch at
   `evolution/skills/evolve_skill.py:351`) and all 29 existing runs have been backfilled.
   Stats CSV remains available as a fallback.

2. **No benchmark gate in schema**: The VALIDATING → DEPLOYED transition requires a TBLite
   benchmark run to confirm no regression. This is a human step not yet tracked on the
   board.

3. **Board refresh is manual**: Unlike the companion kanban (event-driven), this board
   requires running `kanban.py refresh()`. A cron job could automate this.

4. **IN_PROGRESS showing `—`**: For skills with a single run that had 0 improvement and
   0 eval examples (companion-roundtable, companion-personas, etc.), `best_delta` may
   remain at `-inf` and renders as `—`. This is a display bug to fix.

5. **hermes-agent shows `best=+0.1348` but `latest=0.0`**: The best result was from an
   earlier run; the most recent run showed no gain. The card correctly lands in
   VALIDATING because best_delta > 0, but the gap between best and latest is not
   surfaced on the board.

---

## 7. Query Tool — `kanban_query.py`

A CLI tool for querying both boards with filters and sorts. Lives at `gepa_kanban/kanban_query.py`.

```bash
# Run as module
python3.12 -m gepa_kanban.kanban_query [options]

# Or invoke directly
python3.12 gepa_kanban/kanban_query.py [options]
```

### Examples

```bash
# All VALIDATING skills sorted by improvement
python3.12 -m gepa_kanban.kanban_query --board gepa --status VALIDATING --sort best_delta

# High-priority REGRESSION
python3.12 -m gepa_kanban.kanban_query --board gepa --status REGRESSION --priority high

# Skills older than 72h (stale)
python3.12 -m gepa_kanban.kanban_query --board gepa --stale

# Golden dataset skills with 5%+ improvement
python3.12 -m gepa_kanban.kanban_query --board gepa --eval-source golden --delta-min 0.05

# Companion BLOCKED cards
python3.12 -m gepa_kanban.kanban_query --board companion --status BLOCKED

# JSON output for scripting
python3.12 -m gepa_kanban.kanban_query --board all --format json | jq '.[] | select(.status == "VALIDATING")'

# Count only
python3.12 -m gepa_kanban.kanban_query --board gepa --status REGRESSION --format count
```

### Available Filters

| Flag | What it does |
|------|-------------|
| `--board` | `gepa`, `companion`, or `all` (default) |
| `--status` | Column name(s), comma-separated |
| `--priority` | `high`, `medium`, `low` |
| `--delta-min` / `--delta-max` | Filter by `best_delta` range |
| `--age-hours N` | Cards older than N hours |
| `--stale` | Only stale cards |
| `--eval-source` | `synthetic`, `golden`, `sessiondb` |
| `--multi-run` | Only skills with 2+ runs |
| `--search` | Free-text in skill_name / title / owner |

### Output Formats

- **`markdown`** (default) — grouped by status, human-readable
- **`json`** — full card objects for scripting
- **`count`** — just the matching card count
