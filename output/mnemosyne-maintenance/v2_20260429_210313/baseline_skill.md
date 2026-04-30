---
name: mnemosyne-maintenance
description: Routine maintenance tasks for the Mnemosyne BEAM memory provider. Trigger BEAM consolidation, purge session noise, manage knowledge graph triples.
trigger: |
  When starting a new session with Steve, or when the user asks about memory health, or when session count exceeds 50 working memories.
  Also when Silas Vane's audit report is stale (monthly).
related_skills: [companion-system-orchestration, companion-memory, companion-memory-tiers, mnemosyne-self-evolution-tools]
---

# Mnemosyne Maintenance

## Health Quality Score Framework (0-7)

The dashboard (`mnemosyne-stats.py`) scores memory health 0-7 with letter grades:

| Point | Check | Pass Criteria |
|-------|-------|---------------|
| 1 | Consolidation | consolidations_count > 0 |
| 2 | Wiki Integration | wiki_pages > 50 |
| 3 | Dreamer Active | dreamer_runs > 5 AND proposals > 3 |
| 4 | Low Noise | noise_ratio < 30% |
| 5 | Recall Coverage | recall_ratio > 30% |
| 6 | Embedding Pipeline | embedding_vector_count > 100 |
| 7 | Temporal Awareness | triples > 10 AND last_24h > 0 |

Grade: A (7), B (5-6), C (3-4), D (1-2), F (0)

## Diagnosis → Fix → Verify Workflow

When health score is below target (A), run this sequence:

1. **Diagnose:** `python3 ~/hermes0/scripts/mnemosyne-stats.py` — identify failing checks
2. **Fix noise:** Delete oldest conversation items with `importance < 0.3 AND recall_count = 0` (see section 2)
3. **Fix embeddings:** Backfill `memory_embeddings` and `vec_episodes` (see section 6)
4. **Re-verify:** Run dashboard again, confirm all checks pass
5. **Save snapshot:** `python3 ~/hermes0/scripts/mnemosyne-stats.py --save-snapshot` for trend tracking

Removing noise items fixes BOTH noise ratio AND recall coverage simultaneously (fewer total items, fewer never-recalled items).

## Deep Investigation: Tracing Root Causes Through Code

When the dashboard shows a metric problem (high never-recalled, low Dreamer output, high noise) but the standard fix steps don't address the root cause, investigate the code that generates the data.

### Pattern: Trace metrics to their source code

Never trust a metric alone — ask "what code produces this data?" before deciding on a fix. The most common root cause of Mnemosyne metric issues is a mismatch between what the dashboard measures and what upstream code generates.

### Diagnosis 1: "Never-recalled items are high" but noise cleanup only fixes the surface

**Root cause may be upstream code, not volume.** The plugin's `sync_turn()` in `~/.hermes/plugins/mnemosyne/__init__.py` stores every conversation turn as two working memory entries:

```python
# In sync_turn():
self._beam.remember(content=f"[USER] {user_content[:500]}", source="conversation", importance=0.3)
self._beam.remember(content=f"[ASSISTANT] {assistant_content[:800]}", source="conversation", importance=0.2)
```

Over ~157 turns of a heavy session, that's ~314 "conversation" source items at importance 0.2-0.3. These are NOT noise by the strict definition (importance=0.3 hits the threshold boundary), so the noise ratio stays low (~9%) while never-recalled is high (~69%).

**Investigation steps:**
```python
import sqlite3
db = sqlite3.connect(os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db'))
c = db.cursor()

# 1. Categorize never-recalled by source
c.execute("""
    SELECT source, COUNT(*) as cnt, ROUND(AVG(importance),2) as avg_imp,
           ROUND(MIN(importance),2) as min_imp, ROUND(MAX(importance),2) as max_imp
    FROM working_memory WHERE recall_count = 0
    GROUP BY source ORDER BY cnt DESC
""")
# This reveals how many are genuine noise vs genuinely valuable but invisible

# 2. Check importance tiers (never-recalled items with high importance are problems)
c.execute("""
    SELECT
        CASE
            WHEN importance >= 0.8 THEN 'high (0.8+)'
            WHEN importance >= 0.6 THEN 'med (0.6-0.8)'
            WHEN importance >= 0.4 THEN 'low-med'
            ELSE 'low (<0.4)'
        END as tier,
        COUNT(*) as cnt
    FROM working_memory WHERE recall_count = 0
    GROUP BY tier ORDER BY cnt DESC
""")

# 3. Read the plugin source to understand the data generation
# ~/.hermes/plugins/mnemosyne/__init__.py — look for sync_turn() method
```

**Key insight:** The 314 conversation echoes are a feature of how sync_turn works, not a bug. They're harmless — they just inflate the "never-recalled" percentage. The real concern is the ~15-20 genuinely high-value items (insight, fact, task at importance 0.7-0.95) that sit alongside them invisible.

**Fix:** Prune conversation echoes (source='conversation', importance<0.4, recall=0). This immediately drops never-recalled from ~69% to ~8%, revealing the valuable items underneath.

### Diagnosis 2: "Dreamer output is low" (few proposals per run)

**Root cause is data scope, not algorithm tuning.** The Dreamer's memory query (`get_all_active_memories()` in `~/hermes0/scripts/dreamer.py`) only scans `episodic_memory`:

```python
def get_all_active_memories(db_path: Path, limit: int = 200) -> list[dict]:
    """Get all non-superseded episodic memories."""
    # Queries ONLY episodic_memory, NOT working_memory
    cur.execute("""
        SELECT id, content, source, timestamp, session_id, importance, ...
        FROM episodic_memory
        WHERE superseded_by IS NULL
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,))
```

If episodic memory has only 30 items but working memory has 508 (including 39 high-importance gems), the Dreamer is starving on a tiny dataset. With 30 items at clustering threshold 0.7, it finds at most 2-3 tiny clusters per run.

**Investigation steps:**
```python
import sqlite3
db = sqlite3.connect(os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db'))
c = db.cursor()

# 1. Check data source counts
c.execute("SELECT COUNT(*) FROM episodic_memory")  # 30 items
c.execute("SELECT COUNT(*) FROM working_memory")    # 508 items
# Ratio reveals the starvation

# 2. Check Dreamer run stats
c.execute("SELECT memories_scanned, proposals_generated FROM dreamer_runs")
# If memories_scanned consistently matches episodic count, not working count

# 3. Read the Dreamer script's data retrieval function
# ~/hermes0/scripts/dreamer.py — look at get_all_active_memories()
```

**Fix options (choose based on context):**
- A: Add a UNION with working_memory to Dreamer's scan (highest impact — jumps scan from 30 to 508)
- B: Lower clustering threshold from 0.7 to 0.6 (more clusters in sparse data)
- C: Consolidate working memory first, then run Dreamer (lets BEAM promote items before Dreamer scans)
- D: Increase default limit from 50 to 200

### Diagnosis 4: "Dreamer proposals don't have variety"

If the Dreamer only generates consolidation proposals (never surprise or contradiction_question), the data scope fix (Diagnosis 2) + threshold fix (option B above) may be needed together.

**Dreamer has 3 reasoning types:**

| Type | What it does | Found when |
|---|---|---|
| **Consolidation** | Merge duplicate/related memories into one episodic summary | Always — most common type |
| **Surprise** | Pattern appearing across 3+ different session contexts signals importance | After scanning 110+ items |
| **Contradiction Question** | Frames opposing memories as an invitation to reflect ("You said X and also Y — has your thinking shifted?") | After finding high-confidence opposing facts |
| **Supersession** | Cosine sim > 0.85 → older memory marked as superseded_by newer one (audit trail preserved, not deleted) | After threshold drop to 0.6 |

**Proposals go to a staging table (`dreamer_staging`)**, not auto-approved. A human-in-the-loop reviews them with `dreamer.py review list`:

```bash
cd ~/hermes0/scripts && python3 dreamer.py review list   # See pending proposals
cd ~/hermes0/scripts && python3 dreamer.py review stats   # Stats: approved, pending, total
cd ~/hermes0/scripts && python3 dreamer.py review approve <id>  # Approve a proposal
cd ~/hermes0/scripts && python3 dreamer.py review reject <id>   # Reject a proposal
```

**Validated results (post-patch, April 2026):**

| Metric | Before patches | After patches |
|---|---|---|
| Memories scanned | 30 (episodic only) | 110 (episodic + high-imp working) |
| Clustering threshold | 0.7 | 0.6 |
| Supersession conflicts found | 0 | 4 |
| Proposal types produced | consolidations only | consolidation + surprise + contradiction_question |
| Distinct proposals per run | 2-3 | 4+ reasoning lines |

**Key insight:** The Dreamer's creative variety (surprise, contradiction_question) only emerges when it has enough data to surface unexpected connections. Narrow data scope = boring Dreamer. Fix data scope first, then tune thresholds.

### Staging Review Workflow

When proposals are pending, walk through each type with this rubric:

**Consolidation** — Strongest proposals. Check if the source count is genuinely 5+ related items on the same topic. If yes, approve. These are the Dreamer doing its primary job. Verify the proposed summary captures the essence without hallucinating content not in the source items.

**Surprise** — Often paired with a consolidation from the same cluster (same source IDs). If the consolidation was already approved, the surprise is redundant but harmless — approve it as a pattern flag, or reject if you prefer one episodic memory per cluster. If it's a standalone surprise (not overlapping with a consolidation), it's a genuine signal that a topic appeared across 3+ separate contexts.

**Contradiction Question** — These require judgment. Two subtypes:
- *Genuine meta-insight:* Same principle applied across domains (e.g., "primary > secondary" in both OSINT and academic research). Approve as a reflective note.
- *False positive:* Unrelated activities paired by proximity (e.g., SSH troubleshooting next to a script creation). Reject. False positives become rarer after consolidations remove fragmented clusters.

**Decision flow:**
1. Query each proposal's full content from the DB for context — the CLI `list` truncates
2. Check source_ids to see which memories are being linked
3. Apply the rubric, approve/reject
4. Add review_notes explaining the reasoning (helps future Dreamer runs learn from your decisions)

**Known bug — reject handler (fixed April 2026):** The `cli_review()` reject function at `dreamer.py:~811` used `WHERE id = proposal_id` (short prefix) instead of `WHERE id = proposal["id"]` (full UUID from SELECT). The SELECT found the row (uses LIKE), printed "Rejected", but the UPDATE silently missed. Fix: change the parameter in the UPDATE's `WHERE id = ?` from `proposal_id` to `proposal["id"]`.

### Diagnosis 3: "Noise ratio is high" but you've already pruned conversation items

**Root cause may be the noise definition itself.** The dashboard defines noise as `importance < 0.3 AND recall_count = 0`. But conversation items are stored at importance=0.3 (exactly at threshold), so they don't count as "noise" — they're just never recalled. Check for items that are JUST above the noise floor but equally useless.

```python
c.execute("""
    SELECT COUNT(*) FROM working_memory
    WHERE importance < 0.4 AND recall_count = 0 AND source = 'conversation'
""")  # Items functionally identical to noise but just above the definition boundary
```

### General principle for all investigations

1. **Read the code that produces the data** — the plugin's sync_turn, the Dreamer's data retrieval, the dashboard's metric definitions
2. **Query the DB directly** — categorize items by source, importance, recall_count to understand the real distribution
3. **Cross-reference metric failures with data sources** — e.g., "Dreamer only has 3 proposals" isn't a tuning problem, it's a data scope problem (scanning 30 items instead of 508)
4. **Distinguish surface fixes from root causes** — pruning noise is a surface fix; changing the Dreamer's data retrieval is a root cause fix

## Routine Checks

### 0. Automated Guardian (Recommended)

The `mnemosyne-guardian.py` script automates health checks, noise cleanup, and embedding backfill in one run. Runs daily via cron at 9 AM.

```bash
python3 ~/hermes0/scripts/mnemosyne-guardian.py           # Full run: check + fix + snapshot
python3 ~/hermes0/scripts/mnemosyne-guardian.py --check   # Health check only (no fixes)
python3 ~/hermes0/scripts/mnemosyne-guardian.py --dry-run # Show what would be fixed
python3 ~/hermes0/scripts/mnemosyne-guardian.py --report  # Trend report from snapshots
```

Features:
- Auto-prunes noise when ratio > 30% (backs up DB first)
- Auto-backfills missing embeddings using fastembed
- Saves snapshots for trend tracking
- Prints quality score (0-7) with letter grade
- Aligns with mnemosyne-stats.py quality checks

Cron jobs:
- `Mnemosyne Guardian — Daily Health Check` (0 9 * * *)
- `Mnemosyne — Embedding Backfill` (every 6h)

### 1. Run Statistics Dashboard (Manual)
```bash
cd ~/hermes0/scripts && python3 mnemosyne-stats.py          # Full dashboard + auto-snapshot
cd ~/hermes0/scripts && python3 mnemosyne-stats.py --compact # Summary only
cd ~/hermes0/scripts && python3 mnemosyne-stats.py --json    # JSON for piping
cd ~/hermes0/scripts && python3 mnemosyne-stats.py --trends  # Show trend data
cd ~/hermes0/scripts && python3 mnemosyne-stats.py --save-snapshot  # Save + show trends
```
Snapshots auto-save to `~/.hermes/mnemosyne/stats/` for trend tracking.
Health score (0-7) with letter grade. Shows: noise ratio, recall coverage,
consolidation history, dreamer efficiency, wiki integration, actionable recs.

### 1. Check Memory Health
```
mnemosyne_stats()  # Check working/episodic counts
mnemosyne_triple_query(...)  # Check knowledge graph
```

### 1.5 Preventive TTL Cleanup (Alternative to Manual Deletion)

**New strategy:** Instead of manually pruning conversation echoes after they accumulate, add a TTL (time-to-live) to `sync_turn()` so they auto-expire. This is a preventive approach vs. reactive SQL cleanup.

**How it works:**

In `sync_turn()` (at `~/.hermes/plugins/mnemosyne/__init__.py`), add a `valid_until` to conversation turn echoes:

```python
valid_until = (datetime.now() + timedelta(hours=1)).isoformat()
self._beam.remember(
    content=f"[USER] {user_content[:500]}",
    source="conversation", importance=0.3,
    valid_until=valid_until  # auto-expire after 1 hour
)
```

Then wire a cleanup method into `_maybe_auto_sleep()`:

```python
def _cleanup_expired(self):
    """Delete working memory items past their valid_until timestamp."""
    now = datetime.now().isoformat()
    self._beam._execute("DELETE FROM working_memory WHERE valid_until IS NOT NULL AND valid_until < ?", (now,))
    self._beam._execute("DELETE FROM memory_embeddings WHERE memory_id NOT IN (SELECT id FROM working_memory)")
    # Rebuild FTS index
    self._beam._execute("INSERT INTO fts_working(fts_working) VALUES('rebuild')")
```

**Trade-off:** TTL of 1 hour preserves echoes long enough for in-session prefetch (~25 recent turns) but prevents the 300+ item accumulation seen in heavy sessions. The cleanup runs on every auto-sleep trigger, not continuously.

**When to use TTL vs manual cleanup:**
- **TTL** — When you've already done a bulk cleanup and want to prevent recurrence
- **Manual SQL** — When the DB is already dirty and needs a one-time purge
- **Both** — Clean up first, then add TTL to keep it clean

### 2. Noise Cleanup (Comprehensive)

Working memory accumulates auto-generated content that degrades quality metrics. The dashboard's **noise ratio** = `COUNT(importance < 0.3 AND recall_count = 0) / total * 100`. Target: < 30%.

**Quick diagnosis:**
```python
import sqlite3
db = sqlite3.connect(os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db'))
c = db.cursor()
c.execute('SELECT COUNT(*) FROM working_memory WHERE importance < 0.3 AND recall_count = 0')
noise = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM working_memory')
total = c.fetchone()[0]
print(f"Noise: {noise}/{total} = {noise/total*100:.1f}%")
```

**Primary noise source:** `"conversation"` source items — auto-stored assistant response fragments with importance=0.25 and zero recall. These are NOT user memories; they're session transcript echoes. They typically make up 80%+ of the DB.

**SQL cleanup (fast, bulk):**
```python
# Delete oldest conversation noise items (imp<0.3, recall=0, source='conversation')
# FIRST: backup the DB
import shutil
shutil.copy2(db_path, db_path + '.backup_cleanup')

# Calculate how many to delete: N > (total - recalled/0.30) for recall fix
# And N > (noise - 0.30*total) / 0.70 for noise fix
c.execute('''
    DELETE FROM working_memory 
    WHERE id IN (
        SELECT id FROM working_memory 
        WHERE importance < 0.3 AND recall_count = 0 AND source = 'conversation'
        ORDER BY created_at ASC
        LIMIT 210  -- adjust based on diagnosis
    )
''')
db.commit()
# Rebuild FTS index
db.execute("INSERT INTO fts_working(fts_working) VALUES('rebuild')")
db.commit()
```

**Known noise patterns found empirically:**
- `"Review the conversation"` with source="conversation" — auto-generated stubs, NOT user-initiated reviews
- `"Nothing to save."` generic placeholder responses (importance 0.1-0.3)
- Model-switch notifications like `"Switched to model X"` (importance 0.2-0.4)
- `"Operation interrupted"` responses
- `[ASSISTANT]` prefixed conversation fragments — assistant response echoes stored as memories

**Schema:** `working_memory` table: `id` (TEXT PK), `content`, `source`, `importance` (float), `created_at` (timestamp), `scope` (text), `recall_count` (int). Also `memory_embeddings` table for vector data. DB path: `~/.hermes/mnemosyne/data/mnemosyne.db`

**Scripts used for cleanup:**
- `~/hermes0/scripts/cleanup-mnemosyne.py`
- `~/hermes0/scripts/cleanup-mnemosyne2.py`
- `~/hermes0/scripts/check-review.py` (debug: verify content encoding)
- `~/hermes0/scripts/check-remaining.py` (debug: count remaining items)

### 3. Trigger BEAM consolidation
```
mnemosyne_sleep()
```
Check `mnemosyne_stats` after — if episodic stays at 0, working memory items lack
promotable importance (need scope='global' and importance>=0.8).

**BEAM never fires if working memory is dominated by stubs:** In a dirty DB with ~50 working
memory items where 51 were "[USER] Review the conversation" auto-generated stubs, consolidation
never triggered despite multiple sessions. After SQL cleanup (removed 26 low-value items, kept
32 higher-importance ones), BEAM promotion has a clean slate. This is the expected state:
only items with scope='global' AND importance>=0.8 get promoted to episodic memory.

### 4. Promote durable facts to global scope
For facts that should persist across sessions:
```
mnemosyne_remember(content="...", importance=0.8, scope="global", source="fact")
```

### 5. Maintain knowledge graph
```
mnemosyne_triple_add(subject="...", predicate="...", object="...")
```

## Important Caveats

1. **Running Hermes process caches credentials** — to use updated config, spawn fresh CLI process
2. **Compound scoring** — working memory items below 0.6 importance won't surface in recall
3. **triples.db is separate** from mnemosyne.db at `~/.hermes/mnemosyne/data/triples.db`
4. **Serialization note** — `mnemosyne_sleep()` may output `id=??` pairs; these are internal IDs, not errors

## Companion Agent Spawning

When spawning companion agents via separate terminal processes:

```python
# Keep queries SHORT (under 200 chars) to avoid CLI hangs
terminal(background=True, command='hermes chat -q "Short task description" | tail -80')
```

Short query example that worked:
```
hermes chat -q "Audit the Mnemosyne database and catalog results."
```

Long query that hung:
```
hermes chat -q "You ARE Riven Cael... [~400 chars of instructions] ...be thorough."
```

### 6. Embedding Backfill (After Noise Cleanup or First-Time Setup)

When `mnemosyne-stats.py` shows `Embeddings: 0` or `memory_embeddings` is empty, the legacy embedding pipeline hasn't run. Fastembed (BAAI/bge-small-en-v1.5, 384-dim) generates vectors stored in `memory_embeddings` for hybrid recall.

**CRITICAL: These scripts MUST run via the mnemosyne venv python.** Fastembed depends on numpy C extensions compiled for the venv's Python 3.11. Running with system python3 (3.12) will fail with `ImportError: numpy C-extensions failed`. Always use `~/.hermes/mnemosyne-venv/bin/python3`, NOT `python3` or `/usr/bin/python3`.

**Recommended approach (verified working):** Write a standalone worker script to a temp file, then execute it with the venv python. This avoids triple-quote escaping issues and keeps the backfill logic clean:

```bash
cat > /tmp/_backfill_episodic_worker.py << 'PYEOF'
import sqlite3, json, os, sys
sys.path.insert(0, os.path.expanduser('~/.hermes/mnemosyne-venv/lib/python3.11/site-packages'))
from fastembed import TextEmbedding

MNEMOSYNE_DB = os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db')
conn = sqlite3.connect(MNEMOSYNE_DB)
c = conn.cursor()

# Find episodic items missing embeddings
c.execute("SELECT em.id, em.content FROM episodic_memory em "
          "LEFT JOIN memory_embeddings me ON em.id = me.memory_id "
          "WHERE me.memory_id IS NULL")
rows = c.fetchall()
print("Episodic items missing embeddings: " + str(len(rows)))

if rows:
    model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5')
    for i in range(0, len(rows), 32):
        batch = rows[i:i+32]
        ids = [r[0] for r in batch]
        texts = [r[1][:512] if r[1] else '' for r in batch]
        vectors = list(model.embed(texts))
        for mem_id, vec in zip(ids, vectors):
            c.execute("INSERT OR REPLACE INTO memory_embeddings "
                      "(memory_id, embedding_json, model, created_at) "
                      "VALUES (?, ?, 'BAAI/bge-small-en-v1.5', datetime('now'))",
                      (mem_id, json.dumps(vec.tolist())))
        conn.commit()
    print("Done: " + str(len(rows)) + " episodic embeddings")

# Also backfill working items missing embeddings
c.execute("SELECT wm.id, wm.content FROM working_memory wm "
          "LEFT JOIN memory_embeddings me ON wm.id = me.memory_id "
          "WHERE me.memory_id IS NULL")
rows = c.fetchall()
if rows:
    ids = [r[0] for r in rows]
    texts = [r[1][:512] if r[1] else '' for r in rows]
    vectors = list(model.embed(texts))
    for mem_id, vec in zip(ids, vectors):
        c.execute("INSERT OR REPLACE INTO memory_embeddings "
                  "(memory_id, embedding_json, model, created_at) "
                  "VALUES (?, ?, 'BAAI/bge-small-en-v1.5', datetime('now'))",
                  (mem_id, json.dumps(vec.tolist())))
    conn.commit()
    print("Backfilled " + str(len(rows)) + " working embeddings")

conn.close()

# Verify
conn = sqlite3.connect(MNEMOSYNE_DB)
ep_w = conn.execute("SELECT COUNT(*) FROM memory_embeddings me "
                    "JOIN episodic_memory em ON me.memory_id = em.id").fetchone()[0]
ep_t = conn.execute("SELECT COUNT(*) FROM episodic_memory").fetchone()[0]
wm_w = conn.execute("SELECT COUNT(*) FROM memory_embeddings me "
                    "JOIN working_memory wm ON me.memory_id = wm.id").fetchone()[0]
wm_t = conn.execute("SELECT COUNT(*) FROM working_memory").fetchone()[0]
orp = conn.execute("SELECT COUNT(*) FROM memory_embeddings me "
                   "LEFT JOIN episodic_memory em ON me.memory_id = em.id "
                   "LEFT JOIN working_memory wm ON me.memory_id = wm.id "
                   "WHERE em.id IS NULL AND wm.id IS NULL").fetchone()[0]
print("Episodic coverage: " + str(ep_w) + "/" + str(ep_t))
print("Working coverage: " + str(wm_w) + "/" + str(wm_t))
print("Orphans: " + str(orp))
conn.close()
PYEOF
~/.hermes/mnemosyne-venv/bin/python3 /tmp/_backfill_episodic_worker.py
rm /tmp/_backfill_episodic_worker.py
```

This single-shot script backfills BOTH episodic and working memory embeddings in one pass, then verifies coverage and checks for orphaned embeddings.

**Note on `mnemosyne_stats()` episodic.vectors vs memory_embeddings count:** The `mnemosyne_stats()` API reports `episodic.vectors` as the count of int8-quantized vectors in `vec_episodes` (for fast similarity search). The `memory_embeddings` table stores full float32 vectors (384-dim) for hybrid recall. These are separate stores. A healthy backfill will show higher numbers in `memory_embeddings` than in `episodic.vectors`. The goal is all episodic + working items have entries in `memory_embeddings`.

**Check status:**
```python
import sqlite3
db = sqlite3.connect(os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db'))
c = db.cursor()
c.execute('SELECT COUNT(*) FROM memory_embeddings')
print(f"Embeddings: {c.fetchone()[0]}")
c.execute('SELECT COUNT(*) FROM working_memory')
print(f"Working memories: {c.fetchone()[0]}")
```

**Backfill working memories (fastembed, ~34 embeddings/sec):**
```python
import sqlite3, json, os, time
from fastembed import TextEmbedding

db = os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db')
conn = sqlite3.connect(db)
c = conn.cursor()

c.execute('''
    SELECT wm.id, wm.content FROM working_memory wm
    LEFT JOIN memory_embeddings me ON wm.id = me.memory_id
    WHERE me.memory_id IS NULL
''')
missing = c.fetchall()
print(f"Missing embeddings: {len(missing)}")

model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5')
BATCH_SIZE = 32
start = time.time()

for i in range(0, len(missing), BATCH_SIZE):
    batch = missing[i:i+BATCH_SIZE]
    ids = [r[0] for r in batch]
    texts = [r[1][:512] for r in batch]  # Truncate long texts
    vectors = list(model.embed(texts))
    for mem_id, vec in zip(ids, vectors):
        c.execute('''
            INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding_json, model, created_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (mem_id, json.dumps(vec.tolist()), 'BAAI/bge-small-en-v1.5'))
    conn.commit()

print(f"Embedded {len(missing)} in {time.time()-start:.1f}s")
```

**Backfill episodic memories (vec_episodes, int8 quantized):**
```python
import sqlite3, sqlite_vec, numpy as np
from fastembed import TextEmbedding

db = os.path.expanduser('~/.hermes/mnemosyne/data/mnemosyne.db')
conn = sqlite3.connect(db)
conn.enable_load_extension(True)
sqlite_vec.load(conn)
c = conn.cursor()

c.execute('''
    SELECT em.rowid, em.content FROM episodic_memory em
    WHERE em.rowid NOT IN (SELECT rowid FROM vec_episodes)
''')
missing = c.fetchall()

if missing:
    model = TextEmbedding(model_name='BAAI/bge-small-en-v1.5')
    for rowid, content in missing:
        vec = list(model.embed([content[:512]]))[0].astype(np.float32)
        c.execute('INSERT INTO vec_episodes(rowid, embedding) VALUES (?, vec_quantize_int8(?, "unit"))',
                  (rowid, vec.tobytes()))
    conn.commit()
```

**Important:** The vec_episodes table uses int8 quantized vectors, NOT float32. Use `vec_quantize_int8()` when inserting. The fastembed model must be loaded via the mnemosyne venv (`~/.hermes/mnemosyne-venv/bin/python3`).

## Wiki Maturation Pipeline

Periodically run the maturation script to surface Mnemosyne items ready for wiki promotion:

### Step 1: Run dry-run
```bash
cd ~/hermes0/scripts && python3 wiki-mnemosyne-maturation.py --dry-run
```
This lists candidates with importance scores and recall counts.

### Step 2: Categorize candidates
Sort into actionable buckets:
- **SKIP — Already in wiki:** Interview answers (in sessions/), roundtable completions, config snapshots
- **SKIP — Transient:** Model hierarchy changes, delegation config updates, API key status
- **PROMOTE — Preferences:** Steve's traits, decision-making style, philosophical concepts → `memories/`
- **PROMOTE — Knowledge:** Technical findings, business info → `concepts/` or `entities/`
- **PURGE — Duplicates:** Multiple copies of same fact (e.g., DOB x4) → keep 1, delete rest

### Step 3: Purge duplicates from SQLite
```python
import sqlite3
db = sqlite3.connect('/home/steve/.hermes/mnemosyne/data/mnemosyne.db')
# Find duplicates
rows = db.execute("SELECT id, content FROM working_memory WHERE content LIKE '%pattern%'").fetchall()
# Keep first, delete rest
for mid in [r[0] for r in rows[1:]]:
    db.execute("DELETE FROM working_memory WHERE id=?", (mid,))
    db.execute("DELETE FROM memory_embeddings WHERE memory_id=?", (mid,))
db.commit()
```

### Step 4: Create wiki pages
For each promoted item, create a wiki page with proper frontmatter:
```yaml
---
title: "Memory Title"
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: memory
tags: [tag1, tag2]

category: preference  # or fact, principle, etc.
confidence: high
memory_tier: semantic
---
```
## Available Guardian Scripts

| Script | What it monitors | Score | Auto-fixes? |
|--------|-----------------|-------|-------------|
| `mnemosyne-guardian.py` | Memory health (noise, recall, embeddings) | 0-7 (A-F) | Yes |
| `wiki-guardian.py` | Wiki health (pages, links, orphans) | 0-5 (A-F) | No |
| `cron-guardian.py` | Cron job health (success, staleness) | 0-4 (A-F) | No |

All save snapshots to `~/.hermes/mnemosyne/stats/` for trend tracking.
Run `*guardian.py --report` for trend analysis.

### Step 5: Update index.md
Add new pages to the correct section in `~/wiki/index.md` and update section counts.

### Step 6: Run wiki-lint
```bash
cd ~/hermes0/scripts && python3 wiki-lint.py
```
Fix any orphan pages, broken links, or missing index entries.
