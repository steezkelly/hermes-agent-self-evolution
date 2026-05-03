# Phase 5 Ingest Loop Gap Analysis

**Date:** 2026-05-03
**Audited by:** Autonomous agent, read-only investigation
**Scope:** `evolution/tools/ingest_captured.py`, `evolution/core/dataset_builder.py`, and capture data schema (from commit b05af91 Part A description)

---

## 1. Executive Summary

The ingest pipeline (Part B) is **fully implemented** but has **6 critical gaps** that prevent it from closing the flywheel. The capture plugin (Part A) is **completely missing** from the repository — the b05af91 commit message describes it in detail but only committed the ingest-side files.

**Bottom line:** Even if the capture plugin existed and wrote candidates to `~/.hermes/captured/`, the current `ingest_captured.py` would:
- Destroy holdout integrity (identical examples in all 3 splits)
- Overwrite existing synthetic datasets with captured-only data
- Feed raw skill body prefixes (~500 chars) as evaluation rubrics instead of structured behavioral expectations
- Append the same candidate multiple times if re-run (no dedup)
- Never invoke `SyntheticDatasetBuilder` to generate additional diverse test cases from the captured skill

The ingest-to-flywheel handoff is broken at every layer.

---

## Design Decisions (Locked 2026-05-03)

These three decisions close all ambiguous design choices in the spec. Implementation may proceed without revisiting them.

### D1: Capture Trigger
**Decision: Option B — 3+ tool calls**
Rationale: Trivial sessions (one-liners, quick lookups) add noise. Three tool calls is a reliable proxy for "Hermes actually did something worth learning from."
Impact: `is_capturable` heuristic in `capture.py` — count unique tool calls in the session. No slash command required. No user intervention.

### D2: Rubric Generation (Gap C)
**Decision: Option A — Rule-based (first post-frontmatter section)**
Rationale: LLM rubric generation adds cost and latency to every capture. The first section after frontmatter (usually "When to Use" or "Steps") is good enough to unblock the flywheel. Upgrade to LLM rubrics later once the loop is verified.
Impact: `CapturedExampleEnricher` extracts the first `## ` or `### ` heading and its body paragraph as the rubric. No model call. No cost per capture.

### D3: Capture Failure Mode
**Decision: Option A — Silent failure with error logging**
Rationale: The capture plugin must never interrupt a live Hermes session. Eval data is valuable but not worth breaking the agent the user is actively talking to.
Impact: `capture.py` wraps all I/O in `try/except`, logs to `~/.hermes/capture_errors/YYYY-MM-DD.jsonl`, never raises. Session continues regardless.

---

## 2. Current Data Flow (As-Is)

### 2.1 Capture Plugin Schema (from b05af91 commit message — Part A)

The plugin (had it been committed) would save `.json` files to `~/.hermes/captured/<name>.json`:

```json
{
  "session_id": "uuid",
  "task": "user's original task description",
  "captured_at": "2026-03-29T...",
  "status": "pending",
  "domain_tags": ["github", "pr-review"],
  "total_tool_calls": 5,
  "skill_body": "# Heading\nThe full markdown body of the generated skill...",
  "tool_sequence": ["web_search", "browser_click", "..."],
  "success_pattern": "pattern description",
  "overlapping_skills": []
}
```

**Key observation:** `skill_body` is the **full generated skill markdown** (body section, not just a rubric). This is rich content — headings, instructions, examples, tool references.

### 2.2 Ingest Pipeline (`ingest_captured.py`)

```
~/.hermes/captured/*.json
    |
    v
[list_candidates]  → summary table (no mutation)
    |
    v
[validate_candidate] → checks body_length (>50), structure (frontmatter or heading),
                       task_length (>10), overlap (Jaccard > 0.5 blocks)
    |
    v
[deploy_candidate]  → writes ~/.hermes/skills/<name>/SKILL.md with frontmatter
    |                → calls save_as_sessiondb_example()
    v
[save_as_sessiondb_example] → loads EvalDataset (or creates empty)
    |                       → creates ONE EvalExample
    |                       → APPENDS SAME example to train, val, holdout
    |                       → calls EvalDataset.save() → overwrites jsonl files
    v
datasets/skills/<name>/{train,val,holdout}.jsonl
```

### 2.3 Dataset Builder (`dataset_builder.py`)

- `EvalDataset` class: holds train/val/holdout lists of `EvalExample`
- `EvalDataset.save()` — **overwrites** jsonl files (not append, not merge)
- `EvalDataset.load()` — reads jsonl files back
- `SyntheticDatasetBuilder.generate()` — LLM-based generation, produces fresh eval examples from skill text, returns stratified splits
- **No `merge()` or `append()` methods exist**

---

## 3. Gap-by-Gap Analysis

### GAP A — Capture Plugin Does Not Exist (SOURCE FAILURE)

| | |
|---|---|
| **Severity** | P0 — source dry-up |
| **Evidence** | `~/.hermes/captured/` = 0 files; b05af91 only touched 3 ingest-side files |
| **Root cause** | Commit message describes Part A (gateway plugin) but diff only contains Part B (ingest CLI) |
| **Impact** | No candidates → empty pipeline → zero feedback signal |
| **Fix needed** | Build `capture.py` + `plugin.yaml` in `~/.hermes/hermes-agent/src/captured/` using b05af91 commit message as the architecture spec. Commit message describes `is_capturable` heuristics, tool sequence extraction, domain tagging, skill body generation, overlap detection (Jaccard), and slash commands (`/captured`). |
| **Est. effort** | 1–2 days |

---

### GAP B — Data Leakage: Identical Example Added to All 3 Splits

| | |
|---|---|
| **Severity** | P0 — corrupts evaluation |
| **Line** | `ingest_captured.py:save_as_sessiondb_example()` lines ~185–190 |
| **Current code** | `dataset.train.append(example); dataset.val.append(example); dataset.holdout.append(example)` |
| **Root cause** | "Append to all three splits for maximum signal" — a comment that misunderstands holdout purpose |
| **Impact** | Holdout is not holdout. Subsequent evolution runs evaluate on data they trained on → overfit metrics look good, real generalization unknown |
| **Fix needed** | Assign captured examples to **only one split** based on deterministic hash of `task_input` (ensures stable assignment across runs): `split = hash(task_input) % 3 → [train, val, holdout]` |
| **Est. effort** | 2 hours |

---

### GAP C — Rubric Mismatch: `expected_behavior` Is Raw Body Prefix

| | |
|---|---|
| **Severity** | P0 — evaluation is meaningless |
| **Line** | `ingest_captured.py:save_as_sessiondb_example()` — `expected_behavior=body[:500]` |
| **Current behavior** | First 500 characters of the skill markdown body → DSPy Example expected_behavior |
| **Root cause** | No rubric extraction step. The raw body text is instructions for an agent, not a behavioral rubric for judging responses. |
| **Impact** | LLM-as-judge scores `skill_evolved(task_input)` against `expected_behavior=body[:500]`. If the skill's own body is the rubric, the judge measures similarity to source text, not task-completion quality. |
| **Fix needed** | Implement `CapturedExampleEnricher` that parses the skill body and extracts:
1. Task objective (from first heading or task field)
2. Expected tool sequence (from `tool_sequence` in capture data)
3. Success criteria (heuristic: "should use `<tools>` and produce `<output>`")
4. Or: use LLM to generate a proper behavioral rubric from the skill body + task |
| **Est. effort** | 1 day (rule-based MVP) or 2 days (LLM-based full) |

---

### GAP D — Dataset Save Destroys Existing Data (No Merge)

| | |
|---|---|
| **Severity** | P0 — data loss |
| **Line** | `dataset_builder.py:EvalDataset.save()` — opens files with `"w"` mode; `ingest_captured.py` loads then saves |
| **Current behavior** | `EvalDataset.save()` writes all 3 jsonl files from scratch. If a dataset was previously generated by `SyntheticDatasetBuilder` (could be 10–20 examples), and one captured example is deployed, `save_as_sessiondb_example()` loads the old dataset (correct), appends the new example, then calls `.save()` which **correctly** writes all examples including old + new. |
| **Wait — is this actually broken?** | Let me re-read... `save_as_sessiondb_example` does `dataset = EvalDataset.load(output_dir) if output_dir.exists() else EvalDataset()` then appends and calls `EvalDataset.save(dataset, output_dir)`. The `.save()` does overwrite but writes the full in-memory list. **Actually, this is okay for a single append.** But if two processes/threads write simultaneously, or if there's a crash between load and save, data is lost. More critically: there's no `merge_into_dataset()` that handles deduplication or structural upgrades. |
| **Real problem** | No dedup: if `auto` is run twice on the same pending candidate, it appends again. No atomicity. No `merge()` for combining captured + synthetic datasets. |
| **Fix needed** | Add `EvalDataset.merge(other)` that deduplicates by `task_input` hash. Add `merge_into_dataset()` that combines a newly captured example set with an existing dataset without overwriting unrelated splits. |
| **Est. effort** | 2 hours (merge + dedup), 4 hours (atomic file ops) |

---

### GAP E — Never Invokes `SyntheticDatasetBuilder`

| | |
|---|---|
| **Severity** | P1 — limits signal diversity |
| **Current behavior** | Captured skill → 1 eval example (from the capture itself) → all splits (after Gap B fix: 1 split) |
| **Missing** | The captured skill is deployed as a SKILL.md. `SyntheticDatasetBuilder` could read that skill and generate 10–20 diverse eval examples from it. The flywheel should enrich the dataset, not just append a single raw capture. |
| **Impact** | Single-example splits → noisy eval scores → unreliable evolution signal |
| **Fix needed** | After deploying a captured skill, optionally run `SyntheticDatasetBuilder.generate()` on the deployed SKILL.md to produce a full N-example dataset, then merge it with existing datasets. This should be triggered by `ingest_captured auto --enrich` or always-on once capture volume is high enough. |
| **Est. effort** | 1 day |

---

### GAP F — Capture Data → EvalExample Field Mapping Is Lossy

| Capture field | How used in EvalExample | Loss |
|---------------|------------------------|------|
| `task` | `task_input` | ✓ retained |
| `skill_body` | `expected_behavior=body[:500]` | ✗ rubric quality lost |
| `domain_tags[0]` | `category` | ✓ retained (first tag only) |
| `total_tool_calls` | **NOT USED** | ✗ complexity signal lost |
| `tool_sequence` | **NOT USED** | ✗ expected tool sequence lost |
| `success_pattern` | **NOT USED** | ✗ behavioral criteria lost |
| `captured_at` | **NOT USED** | ✗ temporal signal lost |
| `session_id` | stored in SKILL.md metadata | ✓ retained (metadata) |

**Rich capture data → impoverished eval example.** The current mapping throws away everything that could make evaluation nuanced.

| **Fix needed** | Extend `EvalExample` with optional fields: `tool_sequence`, `complexity_score`, `session_id`, `success_pattern`. Modify `to_dict`/`from_dict` to include them. Map capture fields 1:1. |
| **Est. effort** | 4 hours |

---

## 4. Minimum Wiring Spec to Close the Flywheel

The following spec is the **smallest set of changes** that makes a captured session flow end-to-end into the evolution loop's dataset.

### 4.1 Phase 5 Flywheel: Desired Flow

```
[1] Session completes (3+ tool calls) → capture plugin writes ~/.hermes/captured/<name>.json
                                              
[2] Cron or manual: python -m evolution.tools.ingest_captured auto --enrich
                                              
    [2a] validate_candidate() → check structure, overlap
    [2b] deploy_candidate() → write ~/.hermes/skills/<name>/SKILL.md
    [2c] enrich_captured_example() → generate behavioral rubric from body + task + tool_sequence
    [2d] assign_split() → deterministic hash(task_input) → exactly ONE of train/val/holdout
    [2e] SyntheticDatasetBuilder.generate(SKILL.md) → produce 10 diverse examples
    [2f] merge_into_dataset() → dedup by task_input, append new, preserve old
                                              
[3] v2 evolution pipeline reads datasets/skills/<name>/{train,val,holdout}.jsonl
    → scores against real + synthetic eval examples
    → produces improvement signal
                                              
[4] Router decides: deploy / review / reject
    → if deploy: skill is updated, next session uses improved skill
    → if review: human reviews evolved version
                                              
[5] Next session runs → (loop back to [1])
```

### 4.2 New / Modified Components

| Component | Type | Purpose |
|-----------|------|---------|
| `capture.py` + `plugin.yaml` | **New** | Hermes Agent gateway plugin. `on_session_end` hook: 3+ tool calls → extract task, tool sequence, domain tags, success pattern → write `~/.hermes/captured/<name>.json`. Slash command `/captured` for listing/stats. |
| `ingest_captured.py:auto --enrich` | **Modify** | Add `--enrich` flag. When set, after deploy, invoke `SyntheticDatasetBuilder.generate()` on the deployed skill. |
| `save_as_sessiondb_example()` | **Rewrite** | Replace with `enrich_and_merge()`:
1. Parse `skill_body` to extract behavioral rubric (MVP: rule-based from headings + tool_sequence; v2: LLM)
2. Hash `task_input` → assign to exactly one split
3. Load existing EvalDataset
4. Deduplicate (skip if same task_input already exists)
5. Append new example
6. Save atomically (write temp → rename) |
| `EvalDataset.merge()` | **New method** | `dataset.merge(other: EvalDataset)` — dedup by `task_input`, append new, preserve order. Return merge stats. |
| `EvalDataset.save()` | **Modify** | Atomic write: write to `.tmp` file, then `os.rename()`. Preserve old file as `.jsonl.bak` until next successful write. |
| `EvalExample` | **Extend** | Add optional fields: `tool_sequence: list[str]`, `complexity_score: int`, `session_id: str`, `success_pattern: str`. Update `to_dict`/`from_dict`. |
| `SyntheticDatasetBuilder.generate()` | **Reuse (no change)** | Already reads SKILL.md and produces stratified splits. Just need to call it from ingest. |

### 4.3 Data Schema: Capture → EvalExample Mapping (Proposed)

```python
# From capture JSON
{
    "session_id": "uuid",
    "task": "Explain Jaccard similarity for text overlap detection",
    "skill_body": "# Jaccard Text Overlap\n\nUse Jaccard similarity to detect overlap between a candidate skill body and existing skills.",
    "tool_sequence": ["web_search", "search_files"],
    "domain_tags": ["ml", "text-similarity"],
    "total_tool_calls": 4,
    "success_pattern": "Found 3 similar skills, highest J=0.35",
}

# To EvalExample (after enrichment)
EvalExample(
    task_input="Explain Jaccard similarity for text overlap detection",
    expected_behavior="When asked to review a PR for security:\n"
                     "1. Search the codebase for related files\n"
                     "2. Navigate to the PR diff\n"
                     "3. Use vision to inspect the diff visually\n"
                     "4. Report specific vulnerabilities with file:line references\n"
                     "5. Suggest concrete fixes",
    difficulty="medium",  # derived from total_tool_calls: 1-2=easy, 3-5=medium, 6+=hard
    category="github",    # first domain tag
    source="captured",
    tool_sequence=["web_search", "search_files"],
    complexity_score=4,
    session_id="uuid",
    success_pattern="Found 3 similar skills, highest J=0.35",
)
```

---

## 5. Estimated Timeline

| Priority | Gap | Fix | Est. Effort | Cumulative |
|----------|-----|-----|-------------|------------|
| P0 | A | Build capture plugin from b05af91 spec | 1–2 days | Day 2 |
| P0 | B | Split assignment by hash (one split only) | 2 hours | Day 2 |
| P0 | C | Rubric extraction (MVP rule-based) | 1 day | Day 3 |
| P0 | D | Merge + dedup + atomic save | 4 hours | Day 3.5 |
| P1 | E | Invoke SyntheticDatasetBuilder after deploy | 1 day | Day 4.5 |
| P1 | F | Extend EvalExample with capture metadata | 4 hours | Day 5 |
| P2 | — | LLM-based rubric generation (replaces rule-based C) | 1 day | Day 6 |

**Minimum viable flywheel: 3.5 days** (P0 items only, rule-based rubrics)
**Full-featured flywheel: 6 days** (all gaps, LLM rubrics, enrichment)

---

## 6. Files to Modify / Create

### Modify
| File | Changes |
|------|---------|
| `evolution/tools/ingest_captured.py` | Rewrite `save_as_sessiondb_example()` → `enrich_and_merge()`; add `assign_split()`: add `--enrich` flag to auto; add `CapturedExampleEnricher` class |
| `evolution/core/dataset_builder.py` | Add `EvalDataset.merge()`; add optional fields to `EvalExample`; make `save()` atomic |

### Create
| File | Purpose |
|------|---------|
| `~/.hermes/hermes-agent/src/captured/plugin.yaml` | Hermes Agent plugin manifest |
| `~/.hermes/hermes-agent/src/captured/capture.py` | `on_session_end` hook logic (from b05af91 spec) |
| `~/.hermes/hermes-agent/src/captured/__init__.py` | Slash commands (`/captured`) |
| `tests/tools/test_merge_dedup.py` | Test merge + dedup logic |
| `tests/tools/test_rubric_extraction.py` | Test captured → rubric conversion |

---

## 7. Do NOT Proceed With Until This Audit Is Addressed

- **ContentEvolver redesign** — the design of section-level rewriting depends on knowing what real session data looks like once captured. The schema in b05af91 is the starting point, but real data may reveal richer or different fields.
- **Seed density fix** — if captured sessions produce high-quality single examples but SyntheticDatasetBuilder doesn't enrich them, the density problem is in the enrichment layer, not the generator.
- **Any roadmap planning beyond Phase 4** — the ingest loop is the gate. Until one real candidate flows through validation → deploy → dataset → evaluation → improvement signal, estimates for Phases 6+ are guesses.

---

## 8. Quick Verification Script (Post-Implementation)

```python
# After P0 fixes, this should succeed end-to-end:
from evolution.tools.ingest_captured import validate_candidate, deploy_candidate
from evolution.core.dataset_builder import EvalDataset
from pathlib import Path

# 1. Create a fake captured candidate (simulating what the plugin would produce)
candidate = {
    "session_id": "test-123",
    "task": "Explain Jaccard similarity for text overlap detection",
    "captured_at": "2026-05-03T00:00:00Z",
    "status": "pending",
    "domain_tags": ["ml", "text-similarity"],
    "total_tool_calls": 4,
    "skill_body": "# Jaccard Text Overlap\n\nUse Jaccard similarity to detect overlap between a candidate skill body and existing skills.",
    "tool_sequence": ["web_search", "search_files"],
    "success_pattern": "Found 3 similar skills, highest J=0.35",
    "overlapping_skills": []
}
candidate_path = Path.home() / ".hermes" / "captured" / "test-jaccard.json"
candidate_path.write_text(json.dumps(candidate, indent=2))

# 2. Validate → should pass
valid, reason, checks = validate_candidate(candidate_path)
assert valid, reason

# 3. Deploy → should create skill dir + update dataset
ok, msg = deploy_candidate(candidate_path)
assert ok, msg

# 4. Verify dataset integrity
ds = EvalDataset.load(Path("datasets/skills/jaccard-text-overlap"))
assert len(ds.train) + len(ds.val) + len(ds.holdout) == 1  # exactly one split
assert sum(len(s) for s in [ds.train, ds.val, ds.holdout]) == 1  # NOT in all 3

# 5. Verify rubric quality (not raw body prefix)
example = (ds.train or ds.val or ds.holdout)[0]
assert len(example.expected_behavior) < 1000  # concise rubric, not 500-char body dump
assert "tool" in example.expected_behavior.lower() or "should" in example.expected_behavior.lower()
```

If this script passes, the Phase 5 flywheel is closed.

---

## 9. Session Importer Context (Commits 3fb26f1, 4693c8f)

The session importers referenced in the user's request provide additional context about how session data is currently handled in the self-evolution pipeline.

### 9.1 What Those Commits Actually Built

**`external_importers.py`** — "external session importers" for three sources:
- **Claude Code**: `~/.claude/history.jsonl` (user-only text)
- **GitHub Copilot**: `~/.copilot/session-state/*/events.jsonl` (user+assistant, no tool context)
- **Hermes Agent**: `~/.hermes/sessions/*.json` (OpenAI-format message list with user/assistant/tool)

**HermesSessionImporter** reads `~/.hermes/sessions/*.json` files containing OpenAI-format `messages` arrays with `role`, `content`, `session_id`. It pairs user messages with the next assistant response (skipping tool messages in between) and produces:
```python
{
    "source": "hermes",
    "task_input": user_text,
    "assistant_response": assistant_text,
    "session_id": session_id,
}
```

These are then fed through a `RelevanceFilter` (keyword heuristic + LLM-as-judge via DSPy) to score how well each session pair matches a target skill. Results are used as `--eval-source sessiondb` in `evolve_skill.py`.

### 9.2 Key Difference: SessionDB vs. Capture Flywheel

| | SessionDB importer | Capture plugin (Part A of Phase 5) |
|---|---|---|
| **Data source** | Raw session transcripts (`~/.hermes/sessions/*.json`) | Curated skill candidates (`~/.hermes/captured/*.json`) |
| **Format** | OpenAI message list | Custom capture schema (task, skill_body, tool_sequence, domain_tags, success_pattern) |
| **Purpose** | Mine eval signal from past usage | Capture deployable skills for evolution |
| **Output** | EvalExamples used directly as judge training data | SKILL.md deployed to skills dir + enrichsynthetic dataset |
| **Wired to** | `evolve_skill.py --eval-source sessiondb` | `ingest_captured.py` → `dataset_builder.py` |

**The session importers are NOT the capture plugin.** They mine raw usage data for evaluation. The capture plugin is a separate upstream component that creates deployable skill artifacts from session completion patterns. Both feed into the eval pipeline but at different stages:

```
Raw sessions       →  RelevanceFilter  →  eval dataset  (sessiondb, for judge training)
      |
      v
capture plugin  →  candidate .json  →  ingest + enrich  →  skill dataset  (for evolution)
```

This confirms the capture plugin is an independent piece of infrastructure, not a variation of the session importers.

### 9.3 Session Data Schema (from HermesSessionImporter)

```json
{
  "session_id": "uuid",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "content": "..."},
    ...
  ],
  "metadata": {...}
}
```

The **capture plugin** would build on this by watching `on_session_end`, counting tool calls, extracting the **tool sequence** (ordered list of `tool_calls[].function.name`), generating a **skill body** from the assistant's response pattern, and tagging domains via heuristics (which Hermes modules/tools were invoked).


---

## 10. Handoff Mapping: Data Flow Breakdown

This section explicitly maps what the ingest pipeline currently does and where it diverges from what the next evolution cycle needs.

### 10.1 Current Production Flow (`ingest_captured.py`)

```
Step 1: list_candidates()
  Input:  ~/.hermes/captured/*.json
  Output: List of dicts with limited fields (task truncated to 100 chars)
  Status: READ ONLY — no mutation, no downstream effect
  Gap:    Uses truncated task for display; full task available in file

Step 2: validate_candidate(path)
  Input:  single .json file
  Output: (bool is_valid, str reason, dict checks)
  Verifies: body_length > 50, frontmatter/heading structure, task > 10 chars, overlap J > 0.5 blocks
  Gap:    Does NOT validate required fields for EvalDataset (tool_sequence, domain_tags lossy)
  Gap:    Overlap check is Jaccard on raw text — no AST or semantic comparison

Step 3: deploy_candidate(path)
  Input:  single validated .json file
  Output: writes ~/.hermes/skills/<name>/SKILL.md
  Also:   calls save_as_sessiondb_example() → closes flywheel
  Gap:    name generation heuristic (_generate_skill_name) may collide (no counter)
  Gap:    If skill already exists, returns error (no update path for evolved versions)

Step 4: save_as_sessiondb_example(path, output_dir)
  Input:  capture .json + existing dataset (if any)
  Output: datasets/skills/<name>/{train,val,holdout}.jsonl
  Current logic:
    - Load existing dataset
    - Extract task_input from capture["task"]
    - Extract expected_behavior = skill_body[:500] ← CRITICAL GAP
    - Hash domain_tags[0] as category
    - source = "captured"
    - APPEND to train, val, holdout ← CRITICAL GAP B
    - Save via EvalDataset.save() ← okay for single append, but non-atomic

Step 5: evolve_and_deploy(path, iterations=5)
  Input:  capture .json
  Output: runs v2 evolution pipeline, deploys if improvement > noise floor
  Current logic:
    - Validate → temp skill file → copy to ~/.hermes/skills/<name>/
    - Call v2_dispatch(…, eval_source="golden" or "synthetic")
    - If report.recommendation == "deploy": update candidate status
  Gap:    Does NOT re-enrich dataset after evolution (the evolved skill's eval
          dataset is whatever SyntheticDatasetBuilder produced at evolution time,
          not the updated skill body)
  Gap:    "deployed" status is set but the original candidate's body is not
          replaced with the evolved body
```

### 10.2 What the Next Evolution Cycle Needs

```
[Datasets]
  datasets/skills/<name>/{train,val,holdout}.jsonl
  Requirements:
    - Each split has UNIQUE examples (no shared task_input across splits) ← Gap B
    - Each example has structured expected_behavior (rubric, not raw text) ← Gap C
    - Dataset persists across runs (merge, not overwrite) ← Gap D
    - Sufficient examples per split (>1) for reliable scoring ← Gap E
    - Captures full session metadata for analysis ← Gap F

[EvalDataset]
  Methods needed:
    - load() ← EXISTS
    - save() ← EXISTS (non-atomic)
    - merge() ← MISSING ← for dedup + combining synthetic + captured
    - split_assignment_hash() ← MISSING ← for deterministic train/val/holdout
    - atomic_save() ← MISSING ← for crash safety

[SyntheticDatasetBuilder]
  Currently: reads SKILL.md → LLM generates N examples → stratified splits
  Needs to be CALLED from ingest pipeline after deploy ← Gap E

[Evolution Pipeline]
  v2_dispatch(skill_name, eval_dataset_dir)
    Currently: reads eval_dataset_dir, scores, produces report
    Needs: captured session signal to be properly represented in eval dataset

[Reward Signal]
  report.improvement (float)
    Currently: based on synthetic or golden eval only
    With capture: should include captured session performance (real usage)
```

### 10.3 Breakpoint List

| # | Where | What breaks | Fix | Priority |
|---|-------|-------------|-----|----------|
| 1 | `~/.hermes/captured/` | Empty — no plugin writes here | Build capture plugin | P0 |
| 2 | `save_as_sessiondb_example()` | body[:500] → expected_behavior | CapturedExampleEnricher | P0 |
| 3 | `save_as_sessiondb_example()` | Append to all 3 splits | assign_split() by hash | P0 |
| 4 | `save_as_sessiondb_example()` | No dedup, non-atomic save | merge_into_dataset() + atomic save | P0 |
| 5 | `deploy_candidate()` | Never invokes SyntheticDatasetBuilder | Add --enrich flag | P1 |
| 6 | `EvalDataset` / `EvalExample` | Lossy field mapping | Extend dataclass, map fields 1:1 | P1 |
| 7 | `evolve_and_deploy()` | Evolved body not captured in dataset | Post-evolution re-enrichment | P2 |
| 8 | Across pipeline | No way to test end-to-end | Verification script (Section 8) | P0 |

---

## 11. Conclusion and Recommendation

### What this audit reveals

1. The ingest pipeline (`ingest_captured.py`) is **structurally complete** — all CLI commands, validation, deployment, and evolution integration exist and execute.
2. The capture plugin (`capture.py`, `plugin.yaml`) is **entirely absent** — the commit that announced it only committed Part B (ingest). The commit message itself is the architecture spec.
3. The ingest-to-dataset handoff (`save_as_sessiondb_example()`) has **3 P0 bugs** that corrupt evaluation integrity: data leakage across splits, meaningless rubrics, and no deduplication.
4. The dataset builder (`dataset_builder.py`) is **underpowered** — it lacks merge, atomic save, and metadata fields needed for real session data.
5. **The whole Phase 5 flywheel can be closed in ~3.5 days** (P0 items: capture plugin + split fix + rubric extraction + merge/dedup). The remaining P1/P2 items (enrichment, LLM rubrics, metadata fields) are value-adds, not blockers.

### What changes the roadmap

If real session data (once captured) turns out to have richer fields than the b05af91 spec describes — e.g., if user feedback scores, timing data, or tool call arguments are available — then:
- Gap C (rubric extraction) becomes easier (more signal to extract from)
- Gap F (field mapping) becomes more valuable (richer metadata → better analysis)
- Gap E (synthetic enrichment) may need less investment (if captured sessions alone provide enough diverse examples)

**Do NOT proceed with ContentEvolver design or seed density fixes until the P0 items above are implemented and the verification script (Section 8) passes.** Real captured data will reveal whether captured sessions are rich enough to serve as primary eval signal or whether synthetic enrichment is required.

---

*End of audit. Produced 2026-05-03. No code was written — this is a read-only analysis.*
