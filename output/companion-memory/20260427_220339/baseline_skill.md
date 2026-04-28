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

## Mnemosyne BEAM Tiers

Mnemosyne uses a BEAM (Background, Episodic, Active, Markov) inspired tier system:

- **Working** — Active session context, fast retrieval
- **Episodic** — Compressed session summaries, medium retrieval
- **Archival** — Long-term storage, slower but persistent

**Consolidation:** Old working memories get compressed into episodic summaries via `mnemosyne_sleep()`. Call after long sessions or when memory feels stale.

**Knowledge Graph:** Temporal triples (subject, predicate, object) via `mnemosyne_triple_add` and `mnemosyne_triple_query`. Use for structured relationships that change over time.

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
