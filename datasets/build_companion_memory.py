#!/usr/bin/env python3
"""
Build expanded companion-memory evaluation dataset.
Generates 50 train / 15 val / 15 holdout = 80 curated examples.
"""
import json, random, os

random.seed(42)

# ============================================================
# Example template: (task_input, expected_output, difficulty, category, split)
# task_input = realistic user scenario requiring skill reasoning
# expected_output = key knowledge the skill should surface
# ============================================================

EXAMPLES = [
    # ── ARCHITECTURE UNDERSTANDING ──────────────────────────
    {
        "task_input": "A new developer asks: 'I see references to MEMORY.md, Mnemosyne, and wiki in the codebase. How do these three systems relate to each other? Do they compete or complement?'",
        "expected_output": "They form a three-layer stack. Layer 1 (Foundation): MEMORY.md and USER.md are always active, immutable, injected as frozen snapshots — agent self-manages via the memory tool. Layer 2 (Native Provider): currently mnemosyne with BEAM working/episodic/archival tiers. Layer 3 (External): the wiki at ~/wiki/ is a human-auditable backing store, NOT wired into Hermes' native memory pipeline, connected only via skills/cron jobs. They complement each other — Mnemosyne captures session insights automatically, the wiki stores curated knowledge manually, no sync needed.",
        "difficulty": "medium",
        "category": "architecture_understanding",
        "split": "train"
    },
    {
        "task_input": "User asks: 'I want to understand the BEAM tier system. What are working, episodic, and archival memories? How do they differ in size, purpose, and retrieval speed?'",
        "expected_output": "Working memory has ~525 items — active session context, fastest retrieval, used for immediate task context. Episodic memory has ~204 items — compressed session summaries, medium retrieval, created by consolidation. Knowledge Triples store ~238 structured temporal facts immune to consolidation. All are vector-indexed via BAAI/bge-small-en-v1.5 (dim=384, int8) using sqlite-vec. Coverage must be 100%. The BEAM model uses Background/Episodic/Active/Markov-inspired tier management.",
        "difficulty": "medium",
        "category": "architecture_understanding",
        "split": "train"
    },
    {
        "task_input": "A companion developer wants to understand what each layer of the memory stack CAN and CANNOT do. Specifically: can the foundation layer be replaced? Can the wiki serve as a native provider?",
        "expected_output": "The foundation layer (MEMORY.md/USER.md) is always active and CANNOT be replaced by any provider. It's injected as a frozen snapshot at session start. The native provider (Layer 2) can be switched — Hermes ships with holographic, mnemosyne, honcho, openviking, mem0, hindsight, retaindb, byterover, supermemory — but only one can be active at a time because MemoryManager rejects registering a second external provider. The wiki (Layer 3) is NOT wired into Hermes' native memory pipeline — it's an external standalone that cannot serve as a native provider.",
        "difficulty": "hard",
        "category": "architecture_understanding",
        "split": "train"
    },
    {
        "task_input": "A user sees the companion's memory stats say 'Working: 525 items, Episodic: 204 items, Triples: 238 facts'. They ask: 'Why is working memory so much larger than episodic if episodic is supposed to be the compressed format?'",
        "expected_output": "Working memory accumulates across all active sessions. When it becomes cluttered, mnemosyne_sleep() compresses old working memories into episodic summaries. At 525 vs 204 items, either consolidation hasn't run recently, or the user has many short sessions that each create small working entries but don't trigger compression. Run mnemosyne_sleep() with scope='global' to consolidate. The episodic count should increase after consolidation while working count decreases.",
        "difficulty": "hard",
        "category": "architecture_understanding",
        "split": "val"
    },
    {
        "task_input": "An architect asks: 'How does the embedding system work for memory retrieval? What model, dimension, and database is used?'",
        "expected_output": "BAAI/bge-small-en-v1.5 with 384 dimensions, stored as int8 in sqlite-vec. Both working and episodic memories are indexed. The extension is vec0.so at ~/.hermes/mnemosyne-venv/lib/python3.11/site-packages/sqlite_vec/vec0.so. Coverage must be 100% — if below, run the backfill procedure using the mnemosyne-venv Python (not system python, because of numpy version conflicts). The hybrid scoring in recall() uses configurable weights: vec_weight, fts_weight, importance_weight, temporal_weight, temporal_halflife. A tanh function prevents FTS score runaway.",
        "difficulty": "medium",
        "category": "architecture_understanding",
        "split": "train"
    },
    {
        "task_input": 'User says: \'I notice we reference both "BEAM tiers" and "working/episodic/semantic memory" in the docs. Are these the same thing? How do architectural vs semantic triples fit in?\'',
        "expected_output": "Yes — working/episodic/archival ARE the BEAM memory tiers. Additionally there's the Knowledge Graph storing temporal triples (subject, predicate, object) via mnemosyne_triple_add/query. Triples are immune to consolidation. 'Semantic' in the Mnemosyne context refers to the knowledge graph triples, not a separate tier. The BEAM model uses Background/Episodic/Active/Markov as its conceptual inspiration, mapped to working (active context), episodic (session summaries), and knowledge triples (structured facts).",
        "difficulty": "hard",
        "category": "architecture_understanding",
        "split": "holdout"
    },
    {
        "task_input": "A system integrator asks: 'If I switch memory providers from mnemosyne to honcho, what happens to my existing memory data? Is migration supported?'",
        "expected_output": "Migration means SWITCHING providers, not STACKING them. Change memory.provider in config.yaml from 'mnemosyne' to 'honcho'. The foundation layer (MEMORY.md/USER.md) remains intact. However, Mnemosyne's BEAM data at ~/.hermes/mnemosyne/data/mnemosyne.db would become inactive — Honcho would build its own store from scratch. There is NO automatic migration path between providers. The wiki backing store is independent and survives any provider change.",
        "difficulty": "hard",
        "category": "architecture_understanding",
        "split": "train"
    },
    # ── TOOL USAGE ──────────────────────────────────────────
    {
        "task_input": "A companion agent says: 'I need to remember that Steve prefers dark mode in his editor. This preference shouldn't change often. What's the right Mnemosyne tool call to store this?'",
        "expected_output": "Use mnemosyne_remember with content='Steve prefers dark mode in his editor', importance=0.7, source='user', scope='global'. Setting scope='global' ensures it survives session boundaries and memory consolidation. Importance=0.7 means it surfaces more often. Source='user' tags it as direct testimony. No valid_until needed since this is a stable preference.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User asks: 'I'm running a research session and need to find everything we've discussed about the EvoPrompt paper. What tool should I use and what parameters?'",
        "expected_output": "Use mnemosyne_recall with query='EvoPrompt paper', limit=10. This performs a hybrid search using vector similarity (50%), FTS5 text rank (30%), and importance (20%). To boost recency, add temporal_weight=0.3. For fuzzy entity matching, ensure extract_entities=True was set when the memories were stored. If nothing comes back, try broader queries like 'evolutionary prompt optimization' or 'genetic algorithm prompts'.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "It's end of a long session. The user has been working on system design for 3 hours. They ask: 'My working memory feels cluttered — can you clean it up?'",
        "expected_output": "Run mnemosyne_sleep(). This compresses old working memories into episodic summaries. In v2.0.0, sleep(aggregated_scope='global') defaults to global scope. Call it after long sessions or when memory feels stale. After consolidation, verify with mnemosyne_stats() to confirm working count dropped and episodic count increased.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User wants to check memory system health quickly. 'Show me my memory stats right now' — what command/tool returns this?",
        "expected_output": "mnemosyne_stats(). Returns working count (~525), episodic count (~204), and knowledge triple count (~238 facts). Also shows DB size at ~/.hermes/mnemosyne/data/mnemosyne.db (~12.5 MB). For detailed health check, use get_stats() from the mnemosyne module directly: 'from mnemosyne import get_stats; s = get_stats()'.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "A user wants to store a structured relationship: 'Alice reports to Bob in the engineering org.' They're asking which tool handles relationships between entities.",
        "expected_output": "Use mnemosyne_triple_add with subject='Alice', predicate='reports_to', object='Bob', valid_from='2026-04-01'. Temporal triples are stored in a knowledge graph separate from working/episodic memory. They are immune to consolidation and can be queried with mnemosyne_triple_query. This is the right tool for structured relationships between entities, while mnemosyne_remember is for unstructured text facts.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "val"
    },
    {
        "task_input": "A researcher wants to find all memories about 'Project Hermes' but also needs to know when those memories were stored and their confidence level.",
        "expected_output": "Use mnemosyne_recall(query='Project Hermes', limit=10). For temporal boosting add temporal_weight=0.3. The results include importance (0.0-1.0) and source tags. Memories with importance near 1.0 are 'sacred' and should not be consolidated. For time-bounded queries, store memories with valid_until dates and query with temporal_weight to prioritize recent entries.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User deployed a new session and wants to know what the current memory state looks like before starting work. What's the fastest diagnostic?",
        "expected_output": "Run mnemosyne_stats() for a quick overview: working count, episodic count, triple count, DB size. If working count seems high (>800), run mnemosyne_sleep(). If coverage appears low, run the backfill procedure using mnemosyne-venv Python. If anything looks corrupted, run the official test suite: ~/.hermes/mnemosyne-venv/bin/python ~/.hermes/scripts/mnemosyne_v2_test_suite.py — expected 57/57 PASS.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "holdout"
    },
    # ── HEALTH CHECK ────────────────────────────────────────
    {
        "task_input": "The embedding coverage check shows episodic coverage at 95% instead of 100%. The user is worried some memories won't be retrievable. What caused this and how to fix?",
        "expected_output": "Coverage below 100% means some episodic or working memories lack vector embeddings. The v2.0.0 backfill procedure handles this: connect to ~/.hermes/mnemosyne/data/mnemosyne.db, use fastembed (BAAI/bge-small-en-v1.5 via mnemosyne-venv Python, NOT system python) to generate embeddings for orphaned rows, insert into memory_embeddings table. Then clean any orphaned embeddings (WHERE memory_id NOT IN episodic_memory NOR working_memory). If coverage drops again regularly, check if the Embedding Backfill cron job (175920b5f28a, runs every 6 hours) is failing.",
        "difficulty": "hard",
        "category": "health_check",
        "split": "train"
    },
    {
        "task_input": "The Mnemosyne Guardian cron job (0be08565bda4) failed this morning. The user asks: 'What are the implications? Should I panic?'",
        "expected_output": "The Guardian runs daily at 9AM and reports health check results. A single failure isn't critical — run the health check manually: ~/.hermes/mnemosyne-venv/bin/python ~/.hermes/scripts/mnemosyne_v2_test_suite.py (expect 57/57 PASS). Check the Guardian's last output with cronjob action='list' to find the job_id, then 'log' to see error details. Common failures: path issues with vec0.so extension, numpy version conflicts (use mnemosyne-venv, not system python), or disk space issues on ~/.hermes/mnemosyne/data/mnemosyne.db (~12.5 MB).",
        "difficulty": "hard",
        "category": "health_check",
        "split": "train"
    },
    {
        "task_input": "User just upgraded Mnemosyne to v2.0.0. They run the health check and get 52/57 PASS. What's the recommended next step?",
        "expected_output": "5 failing tests in the official suite is a regression. Check which tests failed — likely related to API changes in v2.0.0: get_stats() is now a module-level import (from mnemosyne import get_stats), BeamMemory.__init__ takes (session_id, db_path) with no 'bank' param, sqlite-vec extension is vec0.so (not libsqlite_vec.so), and for bank-scoped stats use from mnemosyne.core.banks import get_bank_stats. Also verify the extension path at ~/.hermes/mnemosyne-venv/lib/python3.11/site-packages/sqlite_vec/vec0.so exists. Run with more verbose output to see which 5 tests fail.",
        "difficulty": "hard",
        "category": "health_check",
        "split": "val"
    },
    {
        "task_input": "A user runs mnemosyne_stats() and sees: Working: 525, Episodic: 204, Triples: 238, DB: 12.5 MB. They ask: 'Is this healthy? What should the numbers look like at minimum?'",
        "expected_output": "Yes, these numbers look healthy for an active companion system. Minimum thresholds: Working count should not exceed ~1000 (run sleep() if so). Episodic should grow proportionally as sessions are consolidated. Triples are structured knowledge — no minimum, but 238 is good. DB size at 12.5 MB is fine for SQLite. Critical things to verify: embedding coverage must be 100% (run the backfill if not), and the Embedding Backfill cron job should be active (175920b5f28a every 6h).",
        "difficulty": "medium",
        "category": "health_check",
        "split": "train"
    },
    {
        "task_input": "User: 'I can't find anything with mnemosyne_recall anymore. It returns empty results even for topics I know we discussed. What's wrong?'",
        "expected_output": "Most likely embedding coverage dropped below 100% — memories exist but aren't vector-indexed so recall can't find them. Run mnemosyne_stats() to check counts, then run the backfill procedure using mnemosyne-venv Python: batch-process missing embeddings in memory_embeddings table using fastembed (BAAI/bge-small-en-v1.5). Alternative cause: the hybrid scoring weights may be misconfigured — check config for vec_weight/fts_weight settings. If coverage is 100% and weights are correct, test with a simple query first before assuming data loss.",
        "difficulty": "hard",
        "category": "health_check",
        "split": "holdout"
    },
    {
        "task_input": "A user runs the backfill procedure and gets 'ModuleNotFoundError: No module named fastembed'. The DB Python is system python. What's the fix?",
        "expected_output": "The backfill must use the mnemosyne-venv Python, NOT system python. The path is ~/.hermes/mnemosyne-venv/bin/python3. System python has conflicting numpy versions. Run: ~/.hermes/mnemosyne-venv/bin/python3 -c \"[backfill code]\". Also verify fastembed is installed in the venv: ~/.hermes/mnemosyne-venv/bin/pip list | grep fastembed. If missing, install: ~/.hermes/mnemosyne-venv/bin/pip install fastembed.",
        "difficulty": "medium",
        "category": "health_check",
        "split": "train"
    },
    # ── TROUBLESHOOTING ─────────────────────────────────────
    {
        "task_input": "Error: 'sqlite3.OperationalError: no such module: vec0'. User just migrated from old Mnemosyne v1.x and this happens on every memory operation.",
        "expected_output": "v2.0.0 changed the sqlite-vec extension name from libsqlite_vec.so to vec0.so. The extension should be at ~/.hermes/mnemosyne-venv/lib/python3.11/site-packages/sqlite_vec/vec0.so. If it's missing, reinstall sqlite-vec in the mnemosyne-venv. Also verify the SQLite connection in code loads the extension: conn.enable_load_extension(True); conn.load_extension('vec0_path'). If the old extension path is still hardcoded somewhere, update to vec0.so.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "A user notices memory_embeddings table has 342 rows but episodic_memory has only 204 rows. They ask: 'Are these orphans? Is this a problem?'",
        "expected_output": "Yes, that indicates orphaned embeddings — memory_embeddings entries whose memory_id doesn't exist in either episodic_memory or working_memory. This happens when memories are deleted but their embeddings persist. Run: DELETE FROM memory_embeddings WHERE memory_id NOT IN (SELECT id FROM episodic_memory) AND memory_id NOT IN (SELECT id FROM working_memory). Then verify with SELECT COUNT(*) FROM memory_embeddings. After cleanup, coverage should be 100% or backfill as needed.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "After upgrading Mnemosyne, get_stats() throws 'TypeError: get_stats() got an unexpected keyword argument bank'. What changed?",
        "expected_output": "v2.0.0 made get_stats() a module-level import: from mnemosyne import get_stats (not from mnemosyne.core.something). The 'bank' parameter was removed. For bank-scoped stats, use: from mnemosyne.core.banks import get_bank_stats. The BeamMemory.__init__ signature changed to (session_id, db_path) with no 'bank' param. Update your import statement and function call.",
        "difficulty": "medium",
        "category": "troubleshooting",
        "split": "val"
    },
    {
        "task_input": "User: 'Daily cron job failed — the Mnemosyne Guardian says it can't find vec0.so. I confirmed the file exists at the expected path. What else could be wrong?'",
        "expected_output": "File existing but failing to load suggests a permission issue or a path mismatch in the Python script that loads it. The cron job runs under a different environment than interactive sessions — confirm the cron job's Python is ~/.hermes/mnemosyne-venv/bin/python3, not system python. The extension loading code should use an absolute path: conn.load_extension(os.path.expanduser('~/.hermes/mnemosyne-venv/lib/python3.11/site-packages/sqlite_vec/vec0.so')). Also check ld_library_path for shared library dependencies.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "holdout"
    },
    {
        "task_input": "A user tries to enable both holographic and Mnemosyne simultaneously: 'I want Mnemosyne for structured recall and holographic for fuzzy pattern matching.' They add both to config.yaml. What happens?",
        "expected_output": "Hermes' MemoryManager explicitly REJECTS registration of a second external provider. The second one will fail at runtime with a registration error. You CANNOT layer providers as 'L2 caches' or run them in parallel for different purposes. Only ONE external provider can be active at any time. The foundation layer (MEMORY.md/USER.md) supplements whatever provider is active, but providers replace each other. Choose one provider per config.",
        "difficulty": "medium",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "A mnemosyne_recall call returns results with suspiciously high FTS scores that drown out the vector similarity component. The user asks how to tune this.",
        "expected_output": "v2.0.0 recall() uses configurable hybrid weights. The tanh function applied to FTS scores prevents keyword weight runaway. To tune: adjust fts_weight lower (default is part of hybrid weights: vec_weight, fts_weight, importance_weight, temporal_weight). Set temporal_halflife for time-decay behavior. If FTS is still dominant even with tanh, reduce fts_weight to 0.1-0.3 and increase vec_weight to 0.5-0.7. You may need to restart the session after config changes.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    # ── DESIGN PRINCIPLES ───────────────────────────────────
    {
        "task_input": "A user stores a fact about their medical allergy: 'severe peanut allergy — anaphylactic risk'. They want this to NEVER be consolidated or lost. What parameters should they use?",
        "expected_output": "This is a sacred memory. Use mnemosyne_remember with importance=1.0, source='user', scope='global'. The importance=1.0 marks it as immutable core knowledge that should never be consolidated or expired. Also consider storing it in the foundation layer via the memory tool: memory(action='add', target='user', content='...'). The foundation layer (MEMORY.md) is always active, injected at session start, and survives any provider change. This dual-store approach ensures the allergy info persists even across provider migrations.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "train"
    },
    {
        "task_input": "A developer asks: 'What's the difference between confidence scoring and importance in the memory system? They seem similar.'",
        "expected_output": "Confidence scoring (0.0-1.0) is about the reliability of the information — was it directly observed (source='user'), inferred (source='inference'), or scraped from the web (source='web-scrape')? Higher confidence = more likely true. Importance (0.0-1.0) is about relevance and retrieval priority — higher importance surfaces the memory more often in recall. A fact can be high-importance but low-confidence (e.g., 'user might prefer Java' stored as inference) or low-importance but high-confidence (e.g., confirmed but trivial fact).",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "train"
    },
    {
        "task_input": "User: 'I want to store a piece of time-sensitive information — a coupon code that expires in 30 days. How do I ensure it doesn't appear in queries after it expires?'",
        "expected_output": "Store with valid_until set to the expiration date: mnemosyne_remember(content='Coupon SAVE20 expires June 1', importance=0.3, source='user', scope='global', valid_until='2026-05-29'). The system checks valid_until dates and deprioritizes or excludes expired facts from results. This is 'graceful expiry' — stale data doesn't pollute the system. For truly hard deadlines, set up a cron job to clean up expired entries.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "val"
    },
    {
        "task_input": "A user stored a fact using mnemosyne_remember but can't tell where the information originally came from. They stored: 'Steve's favorite color is blue' with source='user'. Later they realize Steve said 'I like blue' years ago and his preference may have changed. What's the provenance issue?",
        "expected_output": "The provenance tracking shows source='user' (direct testimony from Steve), but there's no timestamp to distinguish 'Steve said this years ago' from 'Steve said this today'. Best practice: also store context in the content itself, or use multiple memories: one for the original observation with valid_until, and a follow-up if reconfirmed. Confidence scoring should reflect staleness — a memory from years ago should have lower effective confidence than one from today, even if both are source='user'. To update, store a new memory with higher importance and invalidate the old one.",
        "difficulty": "hard",
        "category": "design_principles",
        "split": "holdout"
    },
    {
        "task_input": "Companion designer asks: 'My companion is storing everything — every minor detail from every session. The working memory is growing fast. What memory design principle addresses this?'",
        "expected_output": "'Capture broadly, curate narrowly' — let Mnemosyne capture everything automatically, but only promote important items to the wiki or high-importance memories. Use mnemosyne_sleep() regularly to consolidate working → episodic. Low-importance memories (0.1-0.3) are natural candidates for eventual eviction. High-importance (0.7-1.0) memories are protected. The wiki is for deep research and persistent articles. Not every session detail needs to survive — the system is designed to forget trivial things gracefully.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "train"
    },
    # ── CONSTRAINT ENFORCEMENT ──────────────────────────────
    {
        "task_input": "User says: 'I want to add Mem0 as a supplementary provider on top of Mnemosyne. Mem0 would handle long-term memory while Mnemosyne handles short-term.' Tech lead says this is impossible. Why?",
        "expected_output": "Because Hermes' MemoryManager EXPLICITLY rejects registration of a second external provider. Running two providers simultaneously fails at runtime. The phrase 'supplementary provider' is a common misunderstanding — external providers SUPPLEMENT the foundation layer (MEMORY.md/USER.md) but REPLACE each other. You cannot route short-term to one provider and long-term to another. The correct approach is to choose ONE native provider (currently mnemosyne) and use its built-in tier system (working/episodic/archival) to handle different retention durations.",
        "difficulty": "hard",
        "category": "constraint_enforcement",
        "split": "train"
    },
    {
        "task_input": "Developer asks: 'Can I delete MEMORY.md and USER.md to start fresh with Mnemosyne? I want a clean foundation.'",
        "expected_output": "NO — deleting the foundation files is not recommended. MEMORY.md/USER.md are the always-active foundation layer. Even if Mnemosyne is the active provider, the foundation is injected as a frozen snapshot at session start. If you want to 'clean' the foundation, use the memory tool: memory(action='remove', target='memory', old_text='...') to remove specific entries, or memory(action='replace') to update them. The files themselves should never be manually deleted — they're managed by the agent through tool calls.",
        "difficulty": "medium",
        "category": "constraint_enforcement",
        "split": "train"
    },
    {
        "task_input": "User: 'I saw that holographic was the default provider before we switched to mnemosyne. Can I just add memory.provider: both to get the benefits of both systems?'",
        "expected_output": "No — config value 'both' would be rejected at startup. The memory.provider field accepts only a single provider name (mnemosyne, holographic, honcho, etc.). Hermes' MemoryManager explicitly rejects registering a second provider. If you add 'both', Hermes will try to register the second one and fail with an error. The single-provider constraint is fundamental to the architecture — choose the provider whose strengths you need most and configure its tiers accordingly.",
        "difficulty": "medium",
        "category": "constraint_enforcement",
        "split": "train"
    },
    {
        "task_input": "A new contributor suggests adding a 'memory bridge' that syncs Mnemosyne facts into the wiki automatically for human auditing. Is this feasible given the architecture?",
        "expected_output": "Yes, this is feasible — but it requires a bridge script or cron job, NOT a native provider connection. The wiki is Layer 3 (External/Standalone), deliberately NOT wired into Hermes' native memory pipeline. You can write a script that reads from Mnemosyne's SQLite DB at ~/.hermes/mnemosyne/data/mnemosyne.db and writes wiki pages to ~/wiki/. This would be a separate process, not a provider registration. The single-provider constraint only applies to native providers — external bridges are fine.",
        "difficulty": "hard",
        "category": "constraint_enforcement",
        "split": "val"
    },
    # ── INTEGRATION PATTERNS ────────────────────────────────
    {
        "task_input": "A psychologist companion role wants to save session analysis to the wiki. The current configuration has Mnemosyne as the native provider. How should the psychologist's output be routed?",
        "expected_output": "The psychologist writes to the wiki at ~/wiki/sessions/<session_id>-psychology.md using wiki tools (write_file or Obsidian skills). This is Layer 3 (External/Standalone), independent of the memory provider. Mnemosyne captures session insights automatically via its BEAM system, while the wiki stores curated analysis. No sync needed — Mnemosyne handles operational recall, the wiki handles human-auditable output. The psychologist should do both: let Mnemosyne capture the session naturally, and explicitly write curated analysis to the wiki.",
        "difficulty": "hard",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "User sets up a daily cron job that runs mnemosyne_stats() and emails the report. They ask: 'Should I also run mnemosyne_sleep() daily, or is that automatic?'",
        "expected_output": "mnemosyne_sleep() is NOT automatic — it must be called explicitly. The Mnemosyne Guardian cron job (0be08565bda4, daily at 9AM) handles health checks, but consolidation requires an explicit trigger. Best practice: add mnemosyne_sleep() to the same cron job after the stats report, or configure it to run after long sessions. The Embedding Backfill job (175920b5f28a, every 6h) is separate and handles vector coverage, not consolidation.",
        "difficulty": "medium",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "User has installed a new memory provider (retaindb) and wants to migrate. They ask: 'What's the exact procedure to switch from Mnemosyne to retaindb without losing everything?'",
        "expected_output": "Step 1: Manually export any critical high-importance memories from Mnemosyne (query with mnemosyne_recall, save important ones). Step 2: Change memory.provider in ~/.hermes/config.yaml from 'mnemosyne' to 'retaindb'. Step 3: Restart Hermes. The foundation layer (MEMORY.md/USER.md) survives automatically. There's NO automatic migration between providers — Mnemosyne's BEAM data stays in its SQLite DB but becomes inactive. This is a known architecture limitation. Manual export is the only migration path.",
        "difficulty": "hard",
        "category": "integration",
        "split": "holdout"
    },
    {
        "task_input": "User: 'The wiki has pages I created manually, and Mnemosyne has captured session memories. How do I check if there's overlap or contradiction between the two systems?'",
        "expected_output": "There's no built-in overlap check — Mnemosyne and the wiki serve different purposes and are 'no sync needed'. To detect contradictions manually: query Mnemosyne via mnemosyne_recall for a topic, then grep the wiki via search_files for the same topic. For ongoing reconciliation, consider a bridge script that reads both and flags discrepancies. Design principle: Mnemosyne captures broadly (high recall, lower precision), wiki curates narrowly (high precision, intentful curation). Some overlap is expected and healthy.",
        "difficulty": "hard",
        "category": "integration",
        "split": "val"
    },
    # ── More TRAIN examples to reach 50 ─────────────────────
    {
        "task_input": "A user wants to know if there's a way to tag memories with custom metadata beyond the built-in fields (importance, source, scope).",
        "expected_output": "The core memory fields are importance, source, scope, valid_until, and extract_entities. For custom metadata, embed it in the content text — e.g., '[project:hermes] [type:architecture] Discussion about BEAM tiers' — then use text search (FTS) to find it. Knowledge triples (mnemosyne_triple_add) offer structured predicates for relationships. There's no custom metadata field currently, but content-embedded tags work with FTS retrieval.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "Multiple sessions ago, a user mentioned their birthday is in December. Now they ask: 'Did I ever tell you when my birthday is?' The memory should be findable but it's old.",
        "expected_output": "Use mnemosyne_recall with query='birthday December', limit=10. If memory was stored with extract_entities=True at the time, fuzzy matching should find it even with partial queries. If nothing comes back, try broader queries like 'birthday date month'. If the memory was stored in an old session before the current Mnemosyne was configured, it may be in a different database or only in SessionDB. The memory consolidation system should protect high-importance preferences from being summarized away.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "A user's memory system seems to be returning wrong or outdated information. 'It says my favorite language is Java, but I switched to Rust 6 months ago.' How should the companion handle fact correction?",
        "expected_output": "This is a confidence/provenance issue. The old 'Java' memory may have high importance from being stored earlier. Correct it: (1) mnemosyne_invalidate(memory_id=<old_id>) to mark it as superseded, (2) mnemosyne_remember with updated content='Steve prefers Rust', importance=0.7, source='user', scope='global'. The old fact will be downgraded in retrieval priority. For important facts that evolve over time, store with valid_until dates so old versions automatically expire.",
        "difficulty": "hard",
        "category": "design_principles",
        "split": "train"
    },
    {
        "task_input": "A beginner user asks: 'I see there's mnemosyne_remember and mnemosyne_triple_add. When should I use one vs the other? Give an example of a fact appropriate for each.'",
        "expected_output": "mnemosyne_remember is for unstructured text facts — preferences, observations, summaries. Example: 'Steve uses Neovim with a dark theme.' mnemosyne_triple_add is for structured entity relationships. Example: ('Steve', 'uses_editor', 'Neovim'). The triple goes into the knowledge graph and is immune to consolidation, making it ideal for entity-relationship data you want to preserve permanently. For the same fact, you might use BOTH: triple for the structured relationship and remember for the contextual details.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User migrated from Mnemosyne v1.x to v2.0.0 and the old v1.x tests pass but v2 tests fail with 'ImportError: cannot import name BeamMemory from mnemosyne'. What's wrong?",
        "expected_output": "v2.0.0 changed the API: get_stats() is now a module-level import: from mnemosyne import get_stats (not from a submodule). BeamMemory.__init__ signature changed to (session_id, db_path) with no 'bank' param. The old import paths from v1.x are gone. Check if there's a stub or compatibility layer. If tests still import from the old path, update imports. The bank-scoped stats are now at from mnemosyne.core.banks import get_bank_stats.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "A user runs the backfill script but gets 'sqlite3.OperationalError: no such table: memory_embeddings'. They're sure the database path is correct.",
        "expected_output": "The memory_embeddings table is created during the v2.0.0 migration/init. If it doesn't exist, the database was either not migrated from v1.x, or Mnemosyne hasn't initialized its schema yet. Run the health check suite: ~/.hermes/mnemosyne-venv/bin/python ~/.hermes/scripts/mnemosyne_v2_test_suite.py — this initializes the schema if needed. If still missing, check that ~/.hermes/mnemosyne/data/mnemosyne.db is the correct database and not a stale copy. The sqlite-vec extension requires manual table creation for the embeddings.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "User: 'My semi-annual review of companions — I want to check how much memory we've accumulated and whether we need more aggressive consolidation. What metrics should I look at?'",
        "expected_output": "Run mnemosyne_stats() for current state. Key metrics: (1) Working count — if >800, consolidation is overdue. (2) Episodic-to-working ratio — ideally 0.3-0.5, low ratio means too much raw working memory. (3) Triple count — stable, structured knowledge that should grow slowly. (4) DB size growth rate — ~12.5 MB is fine but track over time. (5) Embedding coverage — must be 100%. For trend analysis, set up a cron job that logs stats daily and compares week-over-week growth.",
        "difficulty": "hard",
        "category": "health_check",
        "split": "train"
    },
    {
        "task_input": "A user deliberately stored the same fact twice with different importance levels. 'mnemosyne_recall now returns both versions with different scores. Which one does the system prefer?'",
        "expected_output": "The recall query returns both but the higher-importance version receives a higher score in the hybrid ranking (importance_weight contributes 20% by default). The system doesn't deduplicate by content — it's up to the agent or user to resolve conflicts. Best practice: if you need to update a fact, use mnemosyne_invalidate on the old memory_id first, then store the new version. This chains old→new so recall returns the current version.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User tries to use mnemosyne_triple_add to store a complex multi-fact description: ('Steve', 'has_properties', 'likes dark mode, uses neovim, prefers Rust'). The query tool can't parse this. What's the right approach?",
        "expected_output": "Triples are for simple atomic relationships. Store each fact as a separate triple: ('Steve', 'prefers', 'dark_mode'), ('Steve', 'uses_editor', 'Neovim'), ('Steve', 'prefers_language', 'Rust'). The predicate should be a simple verb or short phrase, and the object should be a single entity or value. For complex descriptions, use mnemosyne_remember for the unstructured text and triples for the structured relationships.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "A user is diagnosing slow memory recall. 'mnemosyne_recall takes 5-10 seconds. The DB is only 12 MB. What could be slow?'",
        "expected_output": "Potential bottlenecks: (1) Embedding generation in fastembed for vector search is CPU-bound — bge-small-en-v1.5 runs locally. (2) Large working memory (525+ items) means more FTS + vector comparisons. (3) The hybrid scoring ranks all candidates before returning top-k. Optimization ideas: reduce limit parameter to 5, ensure coverage is 100% (orphaned rows waste compute), check if a consolidation is overdue (run mnemosyne_sleep()). If recall speed is critical, consider adjusting near to reduce candidate pool size.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "A developer from the team: 'I want to add a new memory provider to Hermes. What interface does my provider need to implement to be compatible with the MemoryManager?'",
        "expected_output": "The provider must implement the MemoryProvider interface that Hermes' MemoryManager expects. Key requirements: the provider registers itself via the plugin system (in ~/.hermes/plugins/), implements the standard tool schemas (remember, recall, stats, etc.), and can be activated by setting memory.provider in config.yaml. Only ONE external provider can be active at a time — MemoryManager rejects registration of a second. The foundation layer (MEMORY.md/USER.md) is independent and always active.",
        "difficulty": "hard",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "User: 'I want my companion to remember project-specific context across sessions but forget generic noise. How do I configure importance thresholds so noise decays naturally?'",
        "expected_output": "Use importance scoring strategically: (1) store critical project context with importance=0.7-1.0 — these resist consolidation. (2) Store routine observations with importance=0.2-0.4 — these are candidates for consolidation. (3) Trivial notes at importance=0.1 — naturally decay. The system doesn't have an automatic 'forget' mechanism for low-importance items, but mnemosyne_sleep() compresses working to episodic, and low-importance details get summarized away. For hard forgetting, use valid_until dates.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "train"
    },
    {
        "task_input": "A user runs the test suite and gets 57/57 PASS. A week later they get 57/57 PASS again. They ask: 'Is the test suite changing to cover new features, or is it static?'",
        "expected_output": "The test suite should be updated as features evolve. Currently at 57 tests, it covers core Mnemosyne operations (remember, recall, sleep, stats, triples, backfill, embedding). If the test suite hasn't grown, it means new features (custom metadata fields, new provider integrations, cross-provider sync) may lack test coverage. Monitor the test count — it should increase with new functionality. If the suite hasn't been updated in weeks, request a review.",
        "difficulty": "easy",
        "category": "health_check",
        "split": "train"
    },
    {
        "task_input": "User: 'I set up a new Hermes instance on a different machine. Can I copy my Mnemosyne DB over to carry my memory state across machines?'",
        "expected_output": "Technically yes — copy ~/.hermes/mnemosyne/data/mnemosyne.db (~12.5 MB) to the new machine. But check: (1) The sqlite-vec extension (vec0.so) must be installed at the same path. (2) The fastembed cache at ~/.hermes/cache/fastembed should also be copied for performance. (3) MEMORY.md and USER.md must be copied separately (they're foundation layer, not part of Mnemosyne). (4) The memory.provider config must match. Not a designed-for scenario but should work with care.",
        "difficulty": "medium",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "User stored a memory with scope='session' but now can't find it in a different session. They thought all memories were global. What's the difference?",
        "expected_output": "memories stored with scope='session' are only retrievable within the same session — they expire or become inaccessible when the session ends. scope='global' memories persist across all sessions. The default is scope='session'. For important cross-session facts (preferences, knowledge, decisions), always use scope='global'. Session-scoped memories are ideal for temporary context like 'the file we were just editing' or 'the current task status'.",
        "difficulty": "easy",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User: 'My working memory has 900+ items. I run mnemosyne_sleep but it only consolidates a handful. What's wrong?'",
        "expected_output": "mnemosyne_sleep() compresses old working memories into episodic summaries, but it may have thresholds for how many it processes per call. If 900+ items are not consolidating effectively, check: (1) Are many of them marked as high-importance (0.8+) or sacred (1.0)? Those are exempt from consolidation. (2) The sleep function may have a batch size limit. (3) Run sleep() multiple times with scope='global'. (4) If items have valid_until dates in the far future, they may be kept. Worst case: manually prune using mnemosyne_invalidate on clearly ephemeral items.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "User adds a new memory: 'Steve's birthday is Dec 15.' Later a different user asks: 'When is Steve's birthday?' The recall finds no results. The original memory used extract_entities=False. Is that the issue?",
        "expected_output": "extract_entities=False means fuzzy entity matching wasn't applied — the memory relies on FTS keyword matching. 'birthday Dec 15' should match 'Steve's birthday is Dec 15' via FTS unless the query wording differs significantly. Try broader queries: 'birthday December', 'Steve birthday', 'Dec 15'. extract_entities=True would have extracted 'Steve' and 'birthday' as entities for fuzzy recall, making it more resilient to slight wording changes. This is a good argument for default extract_entities=True on identity-related memories.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User: 'I'm building an integration where a Node.js service needs to query the memory system. Is there an API endpoint or does it require Python interop?'",
        "expected_output": "Mnemosyne is a Python-native library with no REST API. To query from Node.js: (1) Spawn a Python subprocess that imports mnemosyne and returns JSON via stdout. (2) Or, connect directly to the SQLite DB at ~/.hermes/mnemosyne/data/mnemosyne.db — but you'd need to replicate the embedding logic (BAAI/bge-small-en-v1.5) and hybrid scoring. Neither is straightforward. Option (1) is recommended: create a simple Python CLI wrapper script that the Node service can call with JSON input/output.",
        "difficulty": "hard",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "A user has 3 companions running simultaneously and each has its own Mnemosyne instance. They ask: 'Can I merge their memory databases into one?'",
        "expected_output": "Not trivially. Mnemosyne instances have separate SQLite databases with auto-increment IDs. Merging them would cause ID conflicts in episodic_memory, working_memory, and memory_embeddings tables. The knowledge triples table might also conflict. Approach: (1) Export memories from each as JSON, (2) Create a fresh DB, (3) Re-import with new IDs. This is a one-time manual process, not a designed feature. Consider whether merging is necessary — separate companions may benefit from separate memory contexts.",
        "difficulty": "hard",
        "category": "integration",
        "split": "train"
    },
    {
        "task_input": "User: 'I used mnemosyne_triple_add to store relationships about our project architecture. Now I want to find all relationships involving a specific component. What's the query pattern?'",
        "expected_output": "Use mnemosyne_triple_query with the component name as either subject or object. Example: mnemosyne_triple_query(subject='DatabaseModule') returns all triples where DatabaseModule is the subject. mnemosyne_triple_query(object='DatabaseModule') returns all triples where it's the object. For flexible search across both, run two queries and merge. The trend knowledge graph supports temporal queries — store with valid_from dates to track how relationships evolved over time.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User crosses session boundaries and expects to find memories from another companion's sessions. They're confused why memories from companion-A's sessions don't appear when companion-B queries. Is this a bug?",
        "expected_output": "It depends on scope. If memories were stored with scope='session', they're confined to that session and invisible to any companion, including the same one in a new session. If stored with scope='global', they should be visible across companions within the same Hermes instance. If companion-A and companion-B are separate Hermes instances (different configs), they have separate Mnemosyne databases. In that case, there's no cross-instance memory sharing — they're completely isolated.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "A user stores a comprehensive system design document in Mnemosyne as a single remember call. The recall for specific details (e.g., 'what database did we choose for the event store?') doesn't find the information even though it's in the stored content. Why?",
        "expected_output": "Large memories stored as a single blob get truncated at 512 chars for embedding generation (fastembed's truncation limit). So the embedding vector only captures the first 512 chars, not the database choice detail buried later. The detail IS searchable via FTS text search, but the FTS weight is only 30% of the hybrid score. Solution: either (a) break the design document into smaller memories by topic, or (b) ensure critical details are in the first 512 chars, or (c) adjust FTS weight higher than default.",
        "difficulty": "hard",
        "category": "design_principles",
        "split": "train"
    },
    {
        "task_input": "User: 'I often quote academic papers verbatim. Can Mnemosyne handle storing long paper excerpts, or is there a size limit?'",
        "expected_output": "There's no hard size limit on the content field, but practical constraints apply: (1) only the first 512 chars are embedded for vector search, (2) recall returns the full stored text even if only the first part was embedded, (3) FTS searches the entire text. Best practice: store paper excerpts as multiple memories (one per key section) with appropriate category tags in the content for FTS discoverability. Use mnemosyne_triple_add for citation metadata: ('PaperTitle', 'cites', 'AnotherPaper').",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "train"
    },
    {
        "task_input": "User runs the official test suite and gets 55/57 PASS — two tests fail. The failing tests are about embedding backfill. They haven't modified anything. What's the likely cause?",
        "expected_output": "Two embedding backfill tests failing without changes suggests either: (1) The vec0.so extension path changed or is missing — verify it exists at ~/.hermes/mnemosyne-venv/lib/python3.11/site-packages/sqlite_vec/vec0.so. (2) The fastembed model cache was cleared — embeddings still work but backfill uses a fresh model download which could fail if network is restricted. Re-run the full health check after ensuring the extension path is correct. If tests still fail, there may be a regression from a recent update.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "train"
    },
    {
        "task_input": "User: 'I need to store temporarily sensitive information — API keys for a short-lived demo environment. I want them to auto-expire after the demo ends tomorrow.'",
        "expected_output": "Store with valid_until set to tomorrow's date and low importance: mnemosyne_remember(content='Demo API key: sk-demo-xxx', importance=0.1, source='user', scope='global', valid_until='2026-04-30'). The low importance ensures it's ranked low in results. After valid_until passes, the system deprioritizes it. For truly sensitive data, DON'T store in Mnemosyne at all — use environment variables or a secure vault. Mnemosyne is not designed for secrets management.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "train"
    },
        # ── More VAL examples ───────────────────────────────────
    {
        "task_input": "User: 'I accidentally stored a memory with source=\"inference\" but it was actually confirmed by the user directly. Can I change the source after the fact, or do I need to delete and re-store?'",
        "expected_output": "You cannot modify a stored memory's metadata after creation. You must use mnemosyne_invalidate(memory_id=<old_id>) to mark it as superseded, then store a new memory with the corrected source='user'. The old memory gets deprioritized in recall. This design is intentional — immutability ensures a reliable audit trail of what was known when, with what confidence.",
        "difficulty": "medium",
        "category": "design_principles",
        "split": "val"
    },
    {
        "task_input": "User ran the health check and got: 'MemoryManager registered providers: [mnemosyne]'. They ask: 'Shouldn't the foundation layer appear here too? Is MEMORY.md not registered?'",
        "expected_output": "The foundation layer (MEMORY.md/USER.md) is NOT registered as a provider — it's injected as a frozen snapshot at session start, independent of the MemoryManager's provider system. That's why it doesn't appear in registered providers. It's always active, always loaded, and cannot be replaced. The provider list only shows external providers that implement the tool-based interface. This is correct behavior.",
        "difficulty": "medium",
        "category": "architecture_understanding",
        "split": "val"
    },
    {
        "task_input": "User: 'I want to use mnemosyne_triple_query to find all facts where Steve is involved in any way — as subject or object. Can I query both directions at once?'",
        "expected_output": "Not in a single call. mnemosyne_triple_query requires you to specify either subject, predicate, or object (or any combination). To find all facts about Steve across both roles, run two queries: mnemosyne_triple_query(subject='Steve') and mnemosyne_triple_query(object='Steve'), then merge results. There's no OR operator across fields. Consider using a broader pattern like querying with just predicate='' to see all triples, then filtering client-side.",
        "difficulty": "medium",
        "category": "tool_usage",
        "split": "val"
    },
    {
        "task_input": "The Embedding Backfill cron job (175920b5f28a) has been running every 6 hours but hasn't reported any changes in days. The user asks: 'Is it still needed? Can I disable it?'",
        "expected_output": "The backfill job ensures new memories get embeddings if they weren't generated at creation time. If it reports no changes for days, it means coverage is 100% and no new memories are missing embeddings — that's a healthy state. Don't disable it unless you have monitoring that alerts on coverage drops. The job is a safety net — you want it there for when something goes wrong (schema migration, model change, batch insert without embedding).",
        "difficulty": "medium",
        "category": "health_check",
        "split": "val"
    },
    {
        "task_input": "User: 'When I migrated to v2.0.0, my old memories from v1.x seem to still be there but mnemosyne_stats shows very different counts than before. Did I lose data?'",
        "expected_output": "Unlikely to have lost data — more likely the counting logic changed between v1.x and v2.0.0. v2 uses get_stats() as a module-level import (from mnemosyne import get_stats) rather than from a submodule. The bank param was removed. Bank-scoped stats now use from mnemosyne.core.banks import get_bank_stats. Compare raw SQLite counts: SELECT COUNT(*) FROM working_memory and episodic_memory. If the raw counts match your expectations, stats display is the issue, not data loss.",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "val"
    },
    {
        "task_input": "User wants to know if they can configure Mnemosyne to auto-sync specific high-importance memories to the wiki as wiki pages. They're thinking of a 'write-through cache' pattern.",
        "expected_output": "There's no built-in sync from Mnemosyne to wiki. But you could build a bridge script: (1) Write a Python script that queries Mnemosyne for memories with importance >= 0.9, (2) Writes them as markdown files to ~/wiki/mnemosyne-sync/. (3) Set it as a cron job. The script would need access to the Mnemosyne DB at ~/.hermes/mnemosyne/data/mnemosyne.db and use the mnemosyne-venv Python. The wiki remains independent of any memory provider — this bridge is a convenience, not an architecture requirement.",
        "difficulty": "hard",
        "category": "integration",
        "split": "val"
    },
    {
        "task_input": "User: 'I set extract_entities=True on an important memory but some entities weren't extracted. Is there a way to manually add entities after the fact?'",
        "expected_output": "No — entity extraction happens at storage time. You cannot re-extract later. The extracted entities are stored with the memory entry and used for fuzzy matching in recall. If entities were missed, invalidate the old memory and re-store with the missing entities spelled out more explicitly in the content text (entity extraction is LLM-based, so clearer phrasing helps). For critical entities, consider storing a parallel triple via mnemosyne_triple_add for reliable structured retrieval.",
        "difficulty": "hard",
        "category": "tool_usage",
        "split": "val"
    },
    {
        "task_input": "User deployed a companion that needs to 'remember everything about project X between sessions'. The companion stores all data with scope='global' but after a week, some details seem to be 'forgotten' — they don't appear in recall anymore.",
        "expected_output": "This is likely consolidation — mnemosyne_sleep() compresses old working memories into episodic summaries, and details that weren't high-importance get summarized away. If every detail must persist: (1) store critical details with importance >= 0.7, (2) use mnemosyne_triple_add for structured project data (immune to consolidation), (3) run sleep() with purpose rather than on a fixed schedule, (4) check if the consolidation is too aggressive by examining episodic summary quality. For truly persistent project memory, write a project wiki page.",
        "difficulty": "hard",
        "category": "design_principles",
        "split": "val"
    },
    # ── Additional HOLD OUT examples ────────────────────────
    {
        "task_input": "A user is designing a system where one companion does research (generating many working memories) and another companion synthesizes research (using episodic memories). They ask: 'Will the researcher's working memories be visible to the synthesizer after consolidation?'",
        "expected_output": "If both companions share the same Hermes instance and use global-scope memories, then yes — the researcher's working memories, after consolidation via mnemosyne_sleep(), become episodic summaries findable by the synthesizer. The key requirements: both companions must use scope='global' for their memories, and consolidation must actually run (not automatic — trigger via sleep()). If companions are separate Hermes instances, they have separate databases and no sharing occurs.",
        "difficulty": "hard",
        "category": "integration",
        "split": "holdout"
    },
    {
        "task_input": "User: 'I have embeddings stored but I'm not sure if the model is still bge-small-en-v1.5 or if it was changed during an upgrade. How do I verify which embedding model my existing vectors use?'",
        "expected_output": "Query the memory_embeddings table directly: SELECT DISTINCT model FROM memory_embeddings. This returns the model name stored when the embeddings were created — should be 'BAAI/bge-small-en-v1.5'. If it returns a different model, or multiple models, that indicates embeddings were generated with different models at different times, which degrades vector search quality (different models produce incompatible vector spaces). In that case, regenerate all embeddings with a single consistent model.",
        "difficulty": "hard",
        "category": "health_check",
        "split": "holdout"
    },
    {
        "task_input": "A companion manager wants to set up automated quality monitoring: 'Every morning I want a report showing: new memories added, consolidation status, embedding coverage, and any errors from the past 24 hours.'",
        "expected_output": "Set up a cron job that runs: (1) mnemosyne_stats() for current state, (2) check cron obe08565bda4 output for Guardian report, (3) check cron 175920b5f28a status for Embedding Backfill, (4) compare stats with previous day's baseline. The Guardian already runs daily at 9AM — augment it to include 24-hour delta tracking. For error monitoring, grep the Guardian's output for 'FAIL' or 'ERROR'. Automate this as a hermes cron job with delivery='origin' so it reports back to the companion.",
        "difficulty": "hard",
        "category": "integration",
        "split": "holdout"
    },
    {
        "task_input": "After a major refactor, the Mnemosyne schema has changed but the old data was not migrated. The user asks: 'Will I lose old memories if I run sleep()? Is consolidation destructive?'",
        "expected_output": "mnemosyne_sleep() compresses WORKING memory into new EPISODIC entries. It does NOT delete old data unless explicitly configured to. The consolidated episodic entries are ADDITIVE — old working memories remain unless explicitly cleaned up. Consolidation is NOT destructive by design. However, if a schema migration happened incompletely, the old data may be in a different format or table. Run the test suite (57/57 PASS expected) to verify schema compatibility before running sleep().",
        "difficulty": "hard",
        "category": "troubleshooting",
        "split": "holdout"
    },
    {
        "task_input": "User asks: 'If I set temporal_weight=0.8 in a recall query, will I ONLY get recent memories, or will old high-importance memories still show up?'",
        "expected_output": "Both. temporal_weight controls the recency boost (default 0.0), not a hard filter. With temporal_weight=0.8, recent memories get a strong boost but old high-importance memories still surface because importance contributes to the hybrid score independently. The total score is: 0.5*vec + 0.3*FTS + 0.2*importance + temporal_boost. A high-importance (1.0) old memory still scores well. There's no 'recency-only' mode — for that, you'd need to filter results post-query.",
        "difficulty": "hard",
        "category": "tool_usage",
        "split": "holdout"
    },
]

# ── Split into train/val/holdout ──────────────────────────
# Count by split
split_counts = {}
for ex in EXAMPLES:
    split = ex["split"]
    split_counts[split] = split_counts.get(split, 0) + 1

print(f"Total examples: {len(EXAMPLES)}")
print(f"  train: {split_counts.get('train', 0)}")
print(f"  val: {split_counts.get('val', 0)}")
print(f"  holdout: {split_counts.get('holdout', 0)}")

# Check coverage
from collections import Counter
for split_name in ["train", "val", "holdout"]:
    split_exs = [e for e in EXAMPLES if e["split"] == split_name]
    cats = Counter(e["category"] for e in split_exs)
    diffs = Counter(e["difficulty"] for e in split_exs)
    print(f"\n{split_name} ({len(split_exs)} exs):")
    print(f"  Categories: {dict(cats)}")
    print(f"  Difficulty: {dict(diffs)}")

# Write
base = os.path.expanduser("~/hermes0/hermes-agent-self-evolution/datasets/skills/companion-memory")
os.makedirs(base, exist_ok=True)

for split_name in ["train", "val", "holdout"]:
    split_exs = [e for e in EXAMPLES if e["split"] == split_name]
    path = os.path.join(base, f"{split_name}.jsonl")
    with open(path, "w") as f:
        for ex in split_exs:
            d = {"task_input": ex["task_input"], "expected_output": ex["expected_output"],
                 "difficulty": ex["difficulty"], "category": ex["category"]}
            f.write(json.dumps(d) + "\n")
    print(f"\nWrote {len(split_exs)} examples to {path}")

print("\nDone!")
