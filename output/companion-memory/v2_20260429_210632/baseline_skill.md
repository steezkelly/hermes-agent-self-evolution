---
name: companion-memory
description: 3-layer memory architecture for the companion system. Covers Hermes memory stack, Mnemosyne BEAM integration, wiki backing store, and critical constraints. Load when designing memory systems or debugging memory issues.
version: 1.0.0
metadata:
  hermes:
    tags: [companion, memory, mnemosyne, architecture, wiki]
    related_skills: [companion-system-orchestration, companion-safety, mnemosyne-maintenance]
---

# Companion Memory Architecture

## Three-Layer Stack

### Layer 1: Foundation (Immutable)

- Files: `~/.hermes/memories/MEMORY.md` (2,200 chars) + `USER.md` (1,375 chars)
- Status: **Always active, cannot be replaced by any provider**
- Injected as frozen snapshot at session start
- Agent self-manages via `memory` tool (add/replace/remove)

### Layer 2: Native Provider (Currently Active)

- Config key: `memory.provider` in `~/.hermes/config.yaml`
- **Current: `mnemosyne`** (BEAM model — working/episodic/archival tiers, SQLite-backed at `~/.hermes/mnemosyne/data/mnemosyne.db`)
- Provides structured capture + retrieval ON TOP of the foundation layer
- Tool schemas: `mnemosyne_remember`, `mnemosyne_recall`, `mnemosyne_sleep`, `mnemosyne_stats`, `mnemosyne_triple_add`, `mnemosyne_triple_query`
- Hermes ships with built-in providers: holographic, mnemosyne, honcho, openviking, mem0, hindsight, retaindb, byterover, supermemory

### Layer 3: External/Standalone (Optional)

- Example: Obsidian vault at `~/wiki/` (human-auditable backing store)
- NOT wired into Hermes' native memory pipeline
- Connected only via skills, cron jobs, or bridge scripts
- Psychologist output goes here: `~/wiki/sessions/<session_id>-psychology.md`

---

## CRITICAL CONSTRAINT: Single External Provider Only

Hermes' `MemoryManager` **explicitly REJECTS registration of a second external provider.** Attempting to run two providers simultaneously will fail at runtime.

**Implications:**
- You CANNOT layer Mnemosyne on top of holographic as a "L2 cache"
- Migration means **switching** providers, not **stacking** them
- External providers SUPPLEMENT the foundation (MEMORY.md/USER.md) but REPLACE each other
- Wiki remains independent of any provider — always human-auditable

**Current state:**
- `memory.provider: mnemosyne` in `~/.hermes/config.yaml`
- Mnemosyne is the native provider (BEAM working/episodic/archival)
- Wiki at `~/wiki/` is the external backing store

---

## Detecting Current State

```bash
hermes memory status
hermes plugins list
# Check what provider is active (shows mnemosyne if current, honcho if previously used)
cat ~/.hermes/config.yaml | grep -A5 "^memory:"
```

**Decision matrix:**

| State | `memory.provider` | Mnemosyne plugin | Meaning |
|-------|-------------------|-------------------|---------|
| Active | `mnemosyne` | Installed at `~/.hermes/plugins/mnemosyne` | Mnemosyne is native provider |
| Inactive | `holographic` or other | Not installed | Other provider active |

---

## Mnemosyne BEAM Tiers (Current: Apr 2026)

Mnemosyne uses a BEAM (Background, Episodic, Active, Markov) inspired tier system:

| Tier | Count | Description |
|------|-------|-------------|
| **Working** | 192 items | Active session context, fast retrieval |
| **Episodic** | 181 items | Compressed session summaries, medium retrieval |
| **Knowledge Triples** | 238 facts | Temporal structured relationships |
| **Total Embeddings** | 356 (100% coverage) | BAAI/bge-small-en-v1.5, no orphans |

**Embedding Architecture:** Both working and episodic memories are indexed by vector embeddings. Coverage must be 100% — any drift below that signals a backfill issue. The embedding model is BAAI/bge-small-en-v1.5, running locally via fastembed in the mnemosyne-venv.

**Consolidation:** Old working memories get compressed into episodic summaries via `mnemosyne_sleep()`. Call after long sessions or when memory feels stale. Consolidation does NOT affect embedding coverage — it compresses content, not indices.

**Knowledge Graph:** Temporal triples (subject, predicate, object) via `mnemosyne_triple_add` and `mnemosyne_triple_query`. Use for structured relationships that change over time (e.g., user preferences, project milestones). Triples are immune to consolidation.

**DB Size:** ~6.1 MB at `~/.hermes/mnemosyne/data/mnemosyne.db`.

---

## Health Check

Run this when diagnosing memory issues or after upgrades:

```bash
# Quick stats
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db')
conn = sqlite3.connect(db)
c = conn.cursor()

# Coverage
ep_w = c.execute('SELECT COUNT(*) FROM memory_embeddings me JOIN episodic_memory em ON me.memory_id = em.id').fetchone()[0]
ep_t = c.execute('SELECT COUNT(*) FROM episodic_memory').fetchone()[0]
wm_w = c.execute('SELECT COUNT(*) FROM memory_embeddings me JOIN working_memory wm ON me.memory_id = wm.id').fetchone()[0]
wm_t = c.execute('SELECT COUNT(*) FROM working_memory').fetchone()[0]
orp = c.execute('SELECT COUNT(*) FROM memory_embeddings me LEFT JOIN episodic_memory em ON me.memory_id = em.id LEFT JOIN working_memory wm ON me.memory_id = wm.id WHERE em.id IS NULL AND wm.id IS NULL').fetchone()[0]
tri = c.execute('SELECT COUNT(*) FROM triples').fetchone()[0]

print(f'Working: {wm_t} | Episodic: {ep_t} | Triples: {tri}')
print(f'Coverage: episodic {ep_w}/{ep_t} ({100*ep_w//ep_t}%), working {wm_w}/{wm_t} ({100*wm_w//wm_t}%)')
print(f'Orphans: {orp}')
print(f'DB: {os.path.getsize(db)/1048576:.1f} MB')
conn.close()
"
```

### Backfill Procedure

If coverage is below 100%, run the backfill. Uses the mnemosyne-venv for fastembed — do NOT use system python (numpy version conflict):

```bash
# Backfill missing episodic embeddings
~/.hermes/mnemosyne-venv/bin/python3 -c "
import sqlite3, json, os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/mnemosyne-venv/lib/python3.11/site-packages'))
from fastembed import TextEmbedding

db = os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db')
conn = sqlite3.connect(db)
c = conn.cursor()

for table in ['episodic_memory', 'working_memory']:
    c.execute(f'SELECT {table}.id, {table}.content FROM {table} LEFT JOIN memory_embeddings me ON {table}.id = me.memory_id WHERE me.memory_id IS NULL')
    rows = c.fetchall()
    if not rows:
        print(f'{table}: 0 missing')
        continue
    model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5')
    for i in range(0, len(rows), 32):
        batch = rows[i:i+32]
        ids = [r[0] for r in batch]
        texts = [r[1][:512] if r[1] else '' for r in batch]
        vectors = list(model.embed(texts))
        for mem_id, vec in zip(ids, vectors):
            c.execute('INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding_json, model, created_at) VALUES (?, ?, ?, datetime(\'now\'))',
                      (mem_id, json.dumps(vec.tolist()), 'BAAI/bge-small-en-v1.5'))
        conn.commit()
        print(f'{table}: batch {i//32+1} done')
    print(f'{table}: {len(rows)} backfilled')

# Clean orphans
c.execute('DELETE FROM memory_embeddings WHERE memory_id NOT IN (SELECT id FROM episodic_memory) AND memory_id NOT IN (SELECT id FROM working_memory)')
conn.commit()
print(f'Orphans cleaned: {c.execute(\"SELECT changes()\").fetchone()[0]}')
conn.close()
"
```

### Cron-Job Integration

The Mnemosyne Guardian (`cron job 0be08565bda4`) runs daily at 9AM and reports health check results. The Embedding Backfill job (`175920b5f28a`) runs every 6 hours. If either fails, investigate manually.

---

## Wiki as Backing Store

The wiki (`~/wiki/`) is the human-auditable layer that persists independently of any memory provider:

- **Mnemosyne** captures session insights automatically
- **Wiki** stores verified, curated knowledge manually
- **No sync needed** — they serve different purposes

| System | Role | Persistence |
|--------|------|-------------|
| Mnemosyne | Fast operational memory for active sessions | BEAM tiers, auto-consolidation |
| Wiki | Deep research, source compilation, persistent articles | Manual curation, human-auditable |

---

## Memory Design Principles

1. **Capture broadly, curate narrowly** — let Mnemosyne capture everything, promote important items to wiki
2. **Confidence scoring** — every fact has a confidence level (0.0-1.0) and source tag
3. **Provenance tracking** — know where every fact came from (direct-testimony, web-scrape, inference)
4. **Graceful expiry** — facts can have `valid_until` dates; stale data doesn't pollute the system
5. **Sacred memories** — some facts are marked as immutable core knowledge (importance 1.0)
