---
name: mnemosyne-self-evolution-tools
description: Build standalone diagnostic tools for Mnemosyne using Python stdlib only — snapshot-based trend tracking, quality scoring, and comprehensive test suites. Use when creating tools that monitor, report on, or evolve the Mnemosyne memory system.
tags: [mnemosyne, python, diagnostics, testing, self-evolution]
category: companion-system
---

# Mnemosyne Self-Evolution Tools

Build standalone Python diagnostic tools for Mnemosyne. Zero dependencies (stdlib only), single-file, zero-config.

## When to Use

- Creating tools that analyze Mnemosyne DB health
- Building snapshot-based trend tracking for any metric
- Writing comprehensive test suites for standalone scripts
- Any "self-evolution" pattern — the system monitoring itself

## Constraints (Self-Imposed)

1. **No new dependencies** — Python stdlib only (sqlite3, json, datetime, pathlib, collections, textwrap, sys, os)
2. **Single-file, zero-config** — reads directly from `~/.hermes/mnemosyne/data/mnemosyne.db`, prints to stdout
3. **Three output modes** — full dashboard, compact (--compact), JSON (--json)

## Architecture Pattern: Snapshot + Trends

### Snapshot Structure
```python
{
    "timestamp": "2026-04-25T23:45:12.123456",  # microsecond precision
    "version": 1,
    "metrics": {
        "working_memory_count": 675,
        "noise_ratio": 0.351,
        "quality_score": 4,
        # ... whatever you're tracking
    }
}
```

### Filename Convention
```python
f"snap_{dt.strftime('%Y%m%d_%H%M%S_%f')}.json"
# Microsecond timestamps prevent collision on rapid consecutive runs
```

### Trend Calculation
```python
def load_trends(stats_dir: Path, lookback: int = 2) -> dict:
    snapshots = sorted(stats_dir.glob("snap_*.json"), reverse=True)
    valid = []
    for s in snapshots[:lookback + 1]:
        try:
            data = json.loads(s.read_text())
            if "metrics" in data:
                valid.append(data)
        except (json.JSONDecodeError, KeyError):
            continue  # Skip corrupted snapshots
    if len(valid) < 2:
        return {}
    current, previous = valid[0], valid[1]
    # Calculate deltas and percent changes
    trends = {}
    for key in current["metrics"]:
        if key in previous["metrics"]:
            cur, prev = current["metrics"][key], previous["metrics"][key]
            if prev != 0:
                pct = ((cur - prev) / abs(prev)) * 100
                trends[key] = {"current": cur, "previous": prev, "delta": cur - prev, "pct_change": pct}
    return trends
```

### Auto-Snapshot on Full Run
```python
if not args.compact and not args.json_only:
    save_snapshot(stats_dir, metrics_dict)  # Save after full dashboard
```

## Quality Score Framework (0-7)

Aligned with `mnemosyne-stats.py` quality checks:

| Point | Check | Pass Criteria |
|-------|-------|---------------|
| 1 | Low Noise | noise_pct < 30% |
| 2 | Recall Coverage | never_recalled_pct < 70% |
| 3 | Global Scope | global_count > 5% of total |
| 4 | Embeddings | embedding_count > 0 OR wm_total == 0 |
| 5 | Consolidation | consolidations_count > 0 |
| 6 | Dreamer Active | dreamer_runs > 0 |
| 7 | Wiki Integration | wiki_pages > 10 |

Letter grade: A (7), B (5-6), C (3-4), D (1-2), F (0)

**IMPORTANT:** Keep this aligned with `mnemosyne-stats.py`. When adding new checks, update BOTH files.

## Testing Pattern

### Test Structure (5 groups, 35+ tests)
```python
class TestNormalOperation(unittest.TestCase):    # Happy path
class TestEdgeCases(unittest.TestCase):          # Missing files, invalid input
class TestIntegration(unittest.TestCase):        # Verify against real DB
class TestStress(unittest.TestCase):             # Performance, rapid calls
class TestDataIntegrity(unittest.TestCase):      # Cross-check metrics
```

### Key Test Categories

**Group 1: Normal Operation** — full run, compact, JSON, save-snapshot, trends, health score, recommendations

**Group 2: Edge Cases** — invalid flags, missing DB, corrupted snapshots, empty directories, special characters, output size, concurrent access

**Group 3: Integration** — wiki count matches actual files, WM/episodic/triples/consolidation counts match DB queries

**Group 4: Stress** — rapid fire (10+ consecutive runs), JSON pipeable, UTF-8 encoding, performance (<5s)

**Group 5: Data Integrity** — distributions sum to total, percentages accurate, quality score correct

### Common Bugs Found During Testing

1. **Corrupted snapshot crash** — `load_trends()` must try/except around each snapshot file, skip invalid ones
2. **Filename collision** — second-level timestamps collide on rapid runs; use microseconds
3. **Stale read_file cache** — use `open()` directly in execute_code for fresh reads before rebuilding
4. **fastembed numpy ABI mismatch** — system Python 3.12 can't import fastembed from venv (3.11). Shell out to venv Python instead.
5. **Dry-run saves snapshots** — check `dry_run` flag before calling `save_snapshot()`. Dry-run should have zero side effects.
6. **"STALE" label for new jobs** — cron jobs that never ran shouldn't show as stale. Distinguish "never run" from "stale (>48h)".

## DB Path

```
~/.hermes/mnemosyne/data/mnemosyne.db
```

Key tables: `working_memory`, `episodic_memory`, `vec_episodes`, `triples`, `consolidation_log`, `dreamer_runs`, `dreamer_staging`, `memory_embeddings`

## Example: mnemosyne-stats.py

The reference implementation is at `~/hermes0/scripts/mnemosyne-stats.py` (301 lines). Run with:
```bash
python3 ~/hermes0/scripts/mnemosyne-stats.py           # Full dashboard
python3 ~/hermes0/scripts/mnemosyne-stats.py --compact  # One-liner
python3 ~/hermes0/scripts/mnemosyne-stats.py --json     # Pipeable
python3 ~/hermes0/scripts/mnemosyne-stats.py --trends   # Compare snapshots
python3 ~/hermes0/scripts/mnemosyne-stats.py --save-snapshot  # Save without dashboard
```

Test suite: `~/hermes0/scripts/test-mnemosyne-stats.py` (35 tests)

## Guardian Scripts (Self-Healing Automation)

Three guardian scripts extend the pattern to other subsystems:

| Script | What it monitors | Score | Auto-fixes? |
|--------|-----------------|-------|-------------|
| `mnemosyne-guardian.py` | Memory health (noise, recall, embeddings) | 0-7 (A-F) | Yes |
| `wiki-guardian.py` | Wiki health (pages, links, orphans) | 0-5 (A-F) | No |
| `cron-guardian.py` | Cron job health (success, staleness) | 0-4 (A-F) | No |

All save snapshots to `~/.hermes/mnemosyne/stats/` with prefix (`snap_`, `wiki_`, `cron_`).

### mnemosyne-guardian.py Features
- Auto-prunes noise when ratio > 30% (backs up DB first)
- Auto-backfills missing embeddings via venv Python
- Three modes: `--check` (read-only), `--dry-run` (show what would change), default (fix + snapshot)
- `--report` for trend analysis from accumulated snapshots

### CRITICAL: Python Version Gotcha for Embeddings

fastembed + numpy are installed in the mnemosyne venv (Python 3.11), but the system Python may be 3.12. Importing fastembed from system Python causes numpy ABI mismatch errors. The guardian handles this by shelling out to the venv Python:

```python
venv_python = os.path.expanduser("~/.hermes/mnemosyne-venv/bin/python3")
subprocess.run([venv_python, tmp_script_path], ...)
```

**Always use the venv Python for embedding operations.** Never try to import fastembed from system Python.

### Cron Automation Setup

```python
# Daily health check at 9 AM
cronjob(action='create', schedule='0 9 * * *',
        prompt='Run: python3 ~/hermes0/scripts/mnemosyne-guardian.py',
        name='Mnemosyne Guardian — Daily Health Check',
        deliver='local', enabled_toolsets=['terminal'])

# Embedding backfill every 6 hours
cronjob(action='create', schedule='every 6h',
        prompt='Backfill missing embeddings...',  # inline script
        name='Mnemosyne — Embedding Backfill',
        deliver='local', enabled_toolsets=['terminal'])
```

### Creating a New Guardian

To add a guardian for a new subsystem:

1. **Define quality checks** — 3-7 binary checks, each with clear pass criteria
2. **Collect metrics** — query the data source (DB, API, filesystem)
3. **Score** — sum of passed checks, letter grade
4. **Snapshot** — save metrics JSON with microsecond timestamp
5. **Trends** — load previous snapshots, compute deltas
6. **Report** — human-readable output with grade, checks, trends, recommendations
7. **Modes** — `--check` (no side effects), `--dry-run` (preview), default (fix + snapshot)
8. **Auto-fix** (optional) — back up DB first, apply fixes, verify improvement
9. **Cron** — schedule periodic runs, use `deliver='local'` for silent execution
