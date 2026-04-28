---
name: companion-memory-tiers
description: 4-tier memory architecture for the companion system. Manages memory lifecycle from creation through sacred status or graceful expiry. Includes tier manager, provenance logger, bulk seeder, query CLI, and TTL checker.
tags: [companion-system, memory, tiers, provenance, implementation]
related_skills: [companion-system-orchestration, companion-memory, mnemosyne-maintenance, companion-safety]
---

# Companion Memory Tiers

## When to Use

- Managing memory lifecycle (creation → tier assignment → promotion/demotion → expiry)
- Querying memories by tier, role, or relevance
- Checking TTL expiry on dormant memories
- Seeding Mnemosyne memories into the tier system
- Auditing memory provenance chains

## The 4 Tiers

| Tier | Name | Behavior | Decay | Protection |
|------|------|----------|-------|------------|
| 0 | Sacred | Never passively decayed. Reviewable via deliberate ceremony. | None | Sacred |
| 1 | Active | Maintained through use. Stays in working context. | None | Standard |
| 2 | Suspended | Consent-paused. Decay clock frozen by user request. | None (paused) | Standard |
| 3 | Re-engagement | Dormant but retrievable. System invites revisit. | TTL: 90 days | Minimal |

### Classification Rules (for bulk seeding)

- **Tier 0**: importance >= 0.9 OR core identity keywords (Navy, Steve, DOB, family, values)
- **Tier 1**: importance >= 0.7 OR source = insight/preference
- **Tier 2**: importance >= 0.5 OR source = fact/decision
- **Tier 3**: everything else (conversation, task, low importance)

## Tools

All at `~/hermes0/scripts/`:

```
memory-tier-manager.py   — Tier DB management (add/promote/demote/stats)
memory-provenance.py     — Append-only audit trail with hash chain
memory-bridge.py         — Integration glue (tag/wiki-log/daily-check/seed/sync-stats)
memory-ttl-check.py      — Daily TTL checker (cron-ready)
memory-bulk-seed.py      — Bulk classify Mnemosyne memories into tiers
memory-query.py          — Ranked retrieval with provenance chains
```

Data at `~/hermes0/companion-system/`:

```
memory-metadata-schema.json  — JSON Schema definition
memory-metadata.json         — Tier database (362+ entries)
provenance-log.jsonl         — Append-only audit log
```

## Quick Commands

```bash
# Initialize
python3 memory-tier-manager.py init

# Seed all Mnemosyne memories
python3 memory-bulk-seed.py
python3 memory-bulk-seed.py --dry-run  # preview first

# Query memories
python3 memory-query.py "Navy service"
python3 memory-query.py "trust" --tier 0 --verbose

# Tag a specific memory
python3 memory-bridge.py tag <memory_id> --tier 0 --role steve

# Check TTL
python3 memory-ttl-check.py
python3 memory-ttl-check.py --verbose

# Full dashboard
python3 memory-bridge.py sync-stats

# Verify provenance integrity
python3 memory-provenance.py verify
```

## Tier Lifecycle

```
Creation → Tier 1 (Active) by default
  ↓ (importance >= 0.9 or core keywords)
Tier 0 (Sacred) — never decays
  ↓ (consent pause)
Tier 2 (Suspended) — decay frozen
  ↓ (no activity for window)
Tier 3 (Re-engagement) — TTL starts
  ↓ (user re-engages)
Back to Tier 1 (Active)
  ↓ (TTL expires, no re-engagement)
Soft-delete → 30-day grace → Hard-delete
```

## Provenance Fields

Every memory entry carries:
- `memory_id`: links to Mnemosyne
- `tier`: 0-3
- `source_role`: which role created it
- `timestamp`: ISO 8601
- `influence_chain`: array of related memory IDs
- `confidence`: 0.0-1.0
- `consent_status`: active/implied/deferred
- `ttl_expiry`: Tier 3 only

## Integration Points

- **Mnemosyne**: `memory-bulk-seed.py` reads SQLite directly
- **Wiki**: `memory-bridge.py wiki-log` logs provenance on page edits
- **Cron**: `memory-ttl-check.py` runs daily for Tier 3 expiry checks

## Key Design Decisions

1. **Provenance is append-only** — hash chain (SHA256) makes tampering detectable
2. **Tier 3 uses re-engagement, not deletion** — "invitation, not punishment"
3. **Retrieval-based strength** — track `last_retrieved` and `retrieval_count`, not creation date
4. **Memory as 10th participant** — has its own sacred memories (meta-patterns)
5. **Tiers classify; they don't rank** — A/B test proved flat scoring beats tiered (p=0.0004). Use tiers for management (TTL, lifecycle, provenance), NOT for search ranking. Query tool uses relevance × recency only.

## A/B Test Finding (2026-04-25)

Tested tiered retrieval vs flat retrieval on 362 memories. Result: **FLAT BEATS TIERED** (p=0.0004, Wilcoxon signed-rank).

**Why:** 70% of memories are in Tier 3 (weight 0.4). The tier weights penalize most memories instead of boosting important ones.

**Implication:** Tiers are a MANAGEMENT tool (organizing, TTL, provenance), not a RETRIEVAL tool (scoring, ranking). The query tool now uses flat scoring (relevance × recency) with tier as optional filter only.

**ADR:** "Tiers classify; they don't rank." Revisit only if the auto-classifier improves beyond 70% Tier 3 skew.

## Success Metrics

Defined in `~/hermes0/companion-system/success-metrics.md`:
1. Query latency: ≤500ms median
2. Retrieval relevance: MRR ≥0.8
3. Tier classification accuracy: ≥85% overall
4. Discovery efficiency: ≤2 queries to find target
5. Provenance completeness: 100% coverage

## Dreamer — Nightly Consolidation Agent

The Dreamer (`~/hermes0/scripts/dreamer.py`) implements sleep-inspired memory consolidation grounded in research (SleepGate, CraniMem, Larimar, SCM).

### Pipeline
1. **Supersession detection** — cosine similarity on embeddings flags outdated memories
2. **Utility scoring** — 4 dimensions: novelty, emotional, task_relevance, repetition
3. **Retention scoring** — importance + recency decay (SCM formula)
4. **Cluster detection** — find related memories via embedding similarity
5. **Proposal generation** — consolidation, surprise, contradiction questions
6. **Staging** — all proposals written to `dreamer_staging` table for human review

### Commands
```bash
# Full run
python3 dreamer.py

# Dry run (preview only)
python3 dreamer.py --dry-run --verbose

# Review proposals
python3 dreamer.py review list           # Show pending
python3 dreamer.py review approve <id>   # Approve → creates new episodic memory
python3 dreamer.py review approve <id> --tier 0  # Override tier
python3 dreamer.py review reject <id>    # Reject proposal
python3 dreamer.py review stats          # Show staging + run stats
```

### Schema (added to Mnemosyne DB)
- `dreamer_staging` — proposals awaiting review (status: pending/approved/rejected/expired)
- `dreamer_runs` — run log with status, counts, errors
- `contradiction_questions` — contradiction detection results
- episodic_memory extensions: `reasoning_type`, `source_ids`, `source_count`, `retention_score`

### Key Design Decisions
- **Contradictions → questions, not classifications** (Thales' insight)
- **Soft biasing, not hard deletion** (SleepGate)
- **3+ source memories required for synthesis** (prevents obvious summaries)
- **1 contradiction question max per run** (prevents surveillance feeling)
- **Dreamer proposes, Steve decides** (human-in-the-loop)

### Current State
- 6 episodic memories (no embeddings yet — pipeline was just fixed)
- Schema migrated, first run logged
- Will become useful once embedding backfill runs and episodic memory grows

## Pitfalls

- Bulk seeder classifies by keyword match — review Tier 0 entries for false positives
- 70% of auto-classified memories end up in Tier 3 (too conservative) — classifier needs tuning
- Provenance log grows fast — 346 entries from one seed run
- TTL checker needs the tier DB to exist — run `init` first
- MiniMax API may be unavailable — use mimo-v2.5 as fallback for delegation
- A/B test script (memory-ab-test.py) still uses OLD tier-weighted scoring — run it to verify flat is better, then trust the query tool's flat scoring
- Dreamer needs embeddings to detect supersessions and clusters — run embedding backfill first
- Dreamer with 6 memories produces no proposals (below cluster threshold) — normal, will improve as memory grows
