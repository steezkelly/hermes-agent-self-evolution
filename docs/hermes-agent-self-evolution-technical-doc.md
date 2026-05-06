# Hermes Agent Self-Evolution — Technical Documentation

```yaml
---
title: "Hermes Agent Self-Evolution Pipeline"
description: >
  GEPA (Genetic-Pareto Prompt Evolution) pipeline for automatically improving
  Hermes Agent skills, tool descriptions, and system prompts via DSPy + evolutionary search.
  No GPU required. API-only. $2-10 per run.
category: "MLOps / Evolutionary Computation"
difficulty: "Advanced"
prerequisites:
  - "Python 3.10+ with venv"
  - "Nous Portal API credentials (OAuth)"
  - "Hermes Agent installed (https://hermes-agent.nousresearch.com)"
  - "DSPy (dspy-ai) and supporting Python packages"
  - "Git"
license: "MIT"
upstream: "https://github.com/NousResearch/hermes-agent-self-evolution"
local_worktree: "~/hermes0/hermes-agent-self-evolution/"
last_updated: "2026-05-02"
production_runs: 16
phase_status:
  phase_1: "Implemented — 16 production runs"
  phase_2: "Implemented — pipeline complete, 0 production runs"
  phase_3: "Stub"
  phase_4: "Stub"
  phase_5: "Partial — ingest_captured CLI implemented"
---
```

## Glossary

| Term | Definition |
|------|-----------|
| **GEPA** | Genetic-Pareto Prompt Evolution — evolutionary optimization loop that mutates text (skills, tool descriptions), evaluates on a dataset, and selects Pareto-optimal variants (best quality at minimal size). |
| **DSPy** | Declarative Stanford ML framework for LM programming. Wraps skill SKILL.md files as `dspy.Module` subclasses so GEPA can compile them. |
| **SKILL.md** | Markdown skill file with YAML frontmatter + procedure body. The atomic unit of Hermes Agent knowledge. |
| **Pareto-optimal** | A variant is Pareto-optimal if no other variant has both better score AND smaller size. Multi-objective selection keeps the best per baseline/evolved pair. |
| **Ghost improvement** | Phantom score gains caused by GEPA learning the eval dataset rather than improving the skill. Detected when evolved score >> baseline but actual skill quality unchanged. Fixed by reading `predict.predict.__doc__` directly. |
| **Holdout set** | A portion of the eval dataset (typically 5 examples) kept separate from training. Used as the final regression gate — evolved must score ≥ baseline on holdout. |
| **Synthetic dataset** | LLM-generated (task_input, expected_behavior) pairs. Fast to produce. Can be trivial. GEPA works with as few as 3 examples. |
| **Golden dataset** | Hand-curated JSONL with real task examples. Highest quality signal but requires manual effort. Stored in `datasets/skills/<skill>/`. |
| **SessionDB** | Mines real conversation history from Claude Code (~/.claude/history.jsonl) and Hermes session transcripts. Two-stage filter: keyword heuristic + LLM-as-judge scoring. |
| **v1 pipeline** | The original single-loop GEPA implementation used for all 16 real production runs. Simple: load → build dataset → validate → compile loop → extract → compare holdout → save. |
| **v2.1 pipeline** | GEPA v1 wrapped with decision gates: BacktrackController (plateau detection), EvolutionRouter (failure classification), PostHocAnalyzer (power-law phase detection). Integration tests pass. Not yet used for production. |
| **EvolutionRouter** | Classifies WHY a GEPA run failed: edge_case (adversarial examples), structural (format issues), coverage (missing areas), noise (random). Returns fix / extend / abstain recommendation. |
| **BacktrackController** | Detects optimization plateaus using a 3-iteration sliding window at 1% threshold. Restores checkpoint on plateau. Forces archive after 3 consecutive backtracks. |
| **PostHocAnalyzer** | Fits score trajectory to power-law: score = a × iteration^c + b. Classifies phase: c > 0.2 = early discovery (keep going), 0.05 < c < 0.2 = diminishing returns (wrap up), c < 0.05 = plateau (stop now). |

---

## 1. Overview

Hermes Agent Self-Evolution is an evolutionary optimization pipeline that uses **DSPy + GEPA** to automatically improve Hermes Agent's skills, tool descriptions, and system prompts — producing measurably better versions through reflective evolutionary search.

**Core properties:**
- **No GPU required** — everything operates via API calls (mutation, evaluation, selection)
- **Cost-effective** — estimated $2–10 per optimization run
- **API-only evolution** — mutates text, evaluates results, selects best variants
- **MIT license** — Nous Research

**Project location:**
- Upstream: `https://github.com/NousResearch/hermes-agent-self-evolution`
- Local worktree: `~/hermes0/hermes-agent-self-evolution/`

---

## 2. Phase Implementation Status

| Phase | Target | Status | LOC | Production Runs |
|-------|--------|--------|-----|----------------|
| **Phase 1** | Skill files (SKILL.md) | Implemented | ~800 | 16 (6 PASS, 3 FAIL, 7 FLAT) |
| **Phase 2** | Tool descriptions | Implemented | ~2,100 | 0 (pipeline complete) |
| **Phase 3** | System prompt sections | Stub | 0 | — |
| **Phase 4** | Code (Darwinian Evolver) | Stub | 0 | — |
| **Phase 5** | Continuous loop | Partial | ~500 | — |

---

## 3. Phase 1 — Skill Evolution

### What It Does

SKILL.md files are wrapped as DSPy modules. GEPA generates mutations (instruction tweaks, format changes, added examples), evaluates them against an eval dataset, and selects Pareto-optimal variants that improve quality without bloat.

### Entry Point

```bash
python -m evolution.skills.evolve_skill \
    --skill <name> \
    --iterations N \
    --eval-source synthetic|golden|sessiondb
```

**File location:** `evolution/skills/evolve_skill.py` (454 lines)

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `evolution/skills/evolve_skill.py` | 454 | CLI entry, v1 pipeline orchestrator |
| `evolution/skills/skill_module.py` | 147 | SKILL.md → DSPy module wrapper |
| `evolution/skills/skill_module_v2.py` | 188 | MultiComponentSkillModule + ghost-improvement fix |
| `evolution/core/dataset_builder.py` | 276 | SyntheticDatasetBuilder, GoldenDatasetLoader |
| `evolution/core/constraints.py` | 361 | v1: size ≤15KB, YAML frontmatter, structure validation |
| `evolution/core/fitness.py` | 399 | skill_fitness_metric() — LLM-as-judge scoring |

### Eval Dataset Sources

Three eval sources, selected via `--eval-source`:

**synthetic** — LLM generates (task_input, expected_behavior) pairs from skill text. Fast but can produce trivial examples. GEPA works with as few as 3 examples.

**golden** — Hand-curated JSONL files in `datasets/skills/<skill>/`. Highest quality signal. Stored as:
- `train.jsonl` — training examples
- `val.jsonl` — validation / checkpoint selection
- `holdout.jsonl` — final regression gate (never seen during training)

Fields: `task_input`, `expected_behavior`, `difficulty` (easy/medium/hard), `category`, `source`

**sessiondb** — Mines real conversation history from:
- Claude Code: `~/.claude/history.jsonl`
- GitHub Copilot: `~/.copilot/session-state/*/events.jsonl`
- Hermes SessionDB

Two-stage filtering: keyword heuristic pre-filter + LLM-as-judge scoring. Includes secret detection (API keys, tokens, PEM keys, AWS credentials, DATABASE_URL). **Note:** SessionDB scoring is slow at 13s/call × 150 candidates. Use synthetic eval source for faster iteration.

### Real Run Results

```
PASS (6):
  companion-workflows            golden     10 iters  0.300→0.425   +41.67%  -1981B
  mnemosyne-self-evolution-tools golden     10 iters  0.398→0.470   +18.02%  -3801B
  ceo-orchestration             sessiondb   3 iters  0.513→0.609   +18.88%     0B
  ceo-orchestration             sessiondb  10 iters  0.534→0.628   +17.62%     0B
  companion-interview-workflow   golden     10 iters  0.498→0.515   +3.55%   +377B
  systematic-debugging           synthetic  10 iters  0.674→0.677   +0.56%  -4958B

FAIL (3):
  companion-interview-pipeline   golden      5 iters  0.581→0.553   -4.85%   +706B  (not deployed)
  companion-safety              golden     10 iters  0.565→0.539   -4.58%  +1957B  (not deployed)
  companion-memory              synthetic  10 iters  0.626→0.601   -3.99%    +41B  (not deployed)

FLAT (7):
  ceo-orchestration             synthetic   2 iters  0.604→0.604    0.0%     0B
  hermes-agent                  synthetic  10 iters  0.587→0.587    0.0%     0B
  hermes-agent                  synthetic  10 iters  0.556→0.556    0.0%     0B
  companion-memory-tiers        golden     10 iters  0.606→0.606    0.0%     0B
  mnemosyne-maintenance         golden     10 iters  0.515→0.515    0.0%     0B
  companion-personas            golden     10 iters  0.608→0.608    0.0%     0B
  companion-roundtable          golden     10 iters  0.000→0.000    0.0%  -17494B  (dataset issue)
```

**Best result:** companion-workflows: 0.300 → 0.425 (+41.67%) using golden dataset with minimax-m2.7.

**Datasets requiring expansion:**
- `companion-roundtable` — 1/0/0 (train/val/holdout). Always produces 0.0/0.0. Must expand to 10/5/5 before next run.
- `github-code-review` — 1 training example only. Expansion needed.

### Constraint System

**v1 constraints** (`evolution/core/constraints.py`):
- Skill size ≤ 15KB (hard gate — reject if exceeded)
- YAML frontmatter must have: `name`, `description`, `tags`
- Must contain a procedure section (## Steps or numbered list)
- Skill must be loadable (parseable)

**v2 constraint checkers** (`evolution/core/constraints_v2.py`, 581 lines):
- **ConfigDriftChecker** — frontmatter name/description/category must not drift from baseline
- **SkillRegressionChecker** — reject if evolved holdout score < baseline holdout score
- **ScopeCreepChecker** — detect term/vocabulary drift using vocabulary overlap between baseline and evolved

---

## 4. Phase 2 — Tool Description Evolution

### What It Does

Tool descriptions are the natural language `description` field in Hermes tool schemas — what the model reads when deciding which tool to call. Evolving them improves tool-selection accuracy. The pipeline treats this as a **classification problem**: given a task description, does the agent pick the right tool?

### Entry Point

```bash
python -m evolution.tools.evolve_tool_description \
    --tool <name>          # e.g., search_files, read_file
    --iterations N \
    --eval-source synthetic|sessiondb

# Evolve all 39 tools at once
python -m evolution.tools.evolve_tool_description \
    --all-tools \
    --iterations N
```

**File location:** `evolution/tools/evolve_tool_description.py` (443 lines)

### Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `evolution/tools/evolve_tool_description.py` | 443 | CLI entry point |
| `evolution/tools/tool_description_v2.py` | 529 | GEPA v2 pipeline with all decision gates |
| `evolution/tools/tool_dataset_builder.py` | 461 | ToolDescriptionDataset (task, tool_name) triples |
| `evolution/tools/tool_module.py` | 163 | ToolDescriptionStore + ToolDescriptionModule |
| `evolution/tools/ingest_captured.py` | 499 | Phase 5 CLI for captured skill ingest |

### Architecture

```
Task description
      ↓
DSPy Predict → tool_name prediction
      ↓
Compare against ground truth
      ↓
GEPA mutates description text (max 500 chars per description)
      ↓
Evaluate: did agent pick the right tool?
```

**39 tools** with synthetic templates covering all major categories: file, terminal, search, browser, web, memory, skills, messaging, code, RL.

**ToolDescriptionConstraintValidator** enforces:
- Max 500 chars per tool description
- Non-empty description required
- Must not cause regression on tool selection accuracy
- Schema structure (parameter names, types) is frozen — only description text evolves

---

## 5. GEPA Pipeline Architecture

### Active: GEPA v1 Pipeline

Used for all 16 real production runs. Simple single-loop design:

```
1. Load skill (find_skill + load_skill)
2. Build eval dataset (synthetic / golden / sessiondb)
3. Validate baseline constraints (v1 constraints.py)
4. Setup DSPy + GEPA compile loop
5. Run N iterations of GEPA mutation + evaluation
6. Extract evolved skill body (_extract_evolved_skill_body)
7. Reject if size > 15KB or structure invalid
8. Compare baseline vs evolved on holdout set
9. Save evolved skill + report.json
```

**Known v1 issues (all fixed locally):**
- MultiComponentSkillModule.forward() discarded all LLM outputs → fixed by reading `predict.predict.__doc__` directly
- TF-IDF metric saturation at ~0.315 → root cause was trivial datasets (1–3 examples), fixed by expanding datasets

### Ready: GEPA v2.1 Dispatch Pipeline

v2.1 wraps v1's GEPA loop with decision gates, rollback, and analytical stop determination. **Integration tests pass. Not yet used for production runs — validation in progress.**

```
1. Load skill + build dataset (same as v1)
2. ConfigDriftChecker — frontmatter stability gate
3. BacktrackController loop (1..max_attempts):
   3a.  GEPA compile + extract evolved body
   3b.  Config drift check (frontmatter)
   3c.  Evaluate on holdout (baseline vs evolved)
   3d.  SkillRegressionChecker — reject if evolved < baseline
   3e.  ScopeCreepChecker — term drift detection
   3f.  ParetoSelector — multi-objective (score vs size)
   3g.  plateau → restore checkpoint, continue
   3h.  3 consecutive backtracks → force_archive, stop
4. PostHocAnalyzer — power-law fitting + phase classification
5. EvolutionRouter — classify failure pattern (edge_case / structural / coverage / noise)
6. Generate EvolutionReport (deploy / review / reject)
```

### v2.1 Components

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| `gepa_v2_dispatch.py` | `evolution/core/` | 455 | v2_dispatch() — wraps v1 with gates |
| `EvolutionRouter` | `evolution/core/router.py` | 189 | Classifies failure pattern → fix / extend / abstain |
| `BacktrackController` | `evolution/core/backtrack.py` | 137 | Plateau detection: 3-iter sliding window, 1% threshold |
| `PostHocAnalyzer` | `evolution/core/posthoc_analyzer.py` | 294 | Power-law fitting: early_discovery / diminishing_returns / plateau |
| `ParetoSelector` | `evolution/core/pareto_selector.py` | 134 | Multi-objective: score vs size |

**Router thresholds (heuristics — unvalidated):**
- edge_case: ≥80% failures are hard/adversarial → suggest FIX
- structural: ≥60% failures cluster in same category + ≥3 new conditionals → suggest FIX
- coverage: failures span unrelated domains → suggest EXTEND
- noise: no pattern → suggest EXTEND

**PostHoc phase classification:**
- c > 0.2 → Early Discovery (steep improvement, keep going)
- 0.05 < c < 0.2 → Diminishing Returns (slowing, start wrapping up)
- c < 0.05 → Plateau (flatlined, stop now)

---

## 6. Core Infrastructure

### Dataset Builders

**SyntheticDatasetBuilder** (`evolution/core/dataset_builder.py`):
- Reads skill text, generates (task_input, expected_behavior) pairs via LLM
- Fields: task_input, expected_behavior, difficulty (easy/medium/hard), category, source
- Default split: 10 train / 5 val / 5 holdout

**GoldenDatasetLoader** (`evolution/core/dataset_builder.py`):
- Loads hand-curated JSONL from `datasets/skills/<skill>/`
- Same field structure as synthetic
- Highest quality but requires manual curation

**ExternalDatasetBuilder** (`evolution/core/external_importers.py`, 803 lines):
- Mines Claude Code, GitHub Copilot, and Hermes SessionDB
- Two-stage filtering: keyword heuristic → LLM-as-judge
- Secret detection: API keys, tokens, PEM keys, AWS credentials, DATABASE_URL
- Balanced brace JSON parser handles nested braces in string values

### Fitness Metric

**skill_fitness_metric()** (`evolution/core/fitness.py`, 399 lines):
- LLM-as-judge with multi-dimensional rubric
- Dimensions: procedure_followed (0–1), correctness_usefulness (0–1), concision (0–1)
- Returns average of three dimensions
- TF-IDF similarity between expected_behavior and actual output

### Nous Auth

**nous_auth.py** (`evolution/core/nous_auth.py`, 196 lines):
- Reads Nous Portal OAuth credentials from hermes-agent auth store
- **Preserves full model IDs** (e.g., `minimax/minimax-m2.7`) instead of stripping to bare names
- Required for correct Nous API routing

### Model Configuration

**Recommended for GEPA runs:**
```bash
--optimizer-model "minimax/minimax-m2.7" \
--eval-model "minimax/minimax-m2.7"
```

The pipeline works through the Nous API with minimax-m2.7. Full model IDs (provider/model-name format) must be preserved — bare model names cause routing failures.

---

## 7. Repository Structure

```
hermes-agent-self-evolution/
├── evolution/
│   ├── core/                              # Shared infrastructure (~4,251 lines)
│   │   ├── config.py                     # EvolutionConfig, repo path resolution
│   │   ├── types.py                      # RouterDecision, BacktrackDecision, EvolutionReport
│   │   ├── fitness.py                    # skill_fitness_metric() — LLM-as-judge scoring
│   │   ├── dataset_builder.py            # SyntheticDatasetBuilder, GoldenDatasetLoader
│   │   ├── external_importers.py         # Claude Code / Copilot / Hermes miners
│   │   ├── nous_auth.py                  # Nous Portal OAuth — full model ID preservation
│   │   ├── constraints.py                # v1: size, structure validators
│   │   ├── constraints_v2.py             # v2: ConfigDrift, SkillRegression, ScopeCreep
│   │   ├── router.py                     # EvolutionRouter — fix / extend / abstain
│   │   ├── backtrack.py                  # BacktrackController — plateau detection
│   │   ├── pareto_selector.py            # ParetoSelector — multi-objective selection
│   │   ├── posthoc_analyzer.py           # PostHocAnalyzer — power-law fitting
│   │   ├── evolve_skill_v2.py            # EvolutionRun — v2 pipeline entry
│   │   └── gepa_v2_dispatch.py           # v2_dispatch() — v1 wrapped with gates
│   │
│   ├── skills/                           # Phase 1: Skill evolution (PRODUCTION)
│   │   ├── evolve_skill.py               # CLI: python -m evolution.skills.evolve_skill
│   │   ├── skill_module.py               # SKILL.md → DSPy module wrapper
│   │   └── skill_module_v2.py            # MultiComponentSkillModule + ghost-improvement fix
│   │
│   ├── tools/                            # Phase 2: Tool descriptions (PRODUCTION)
│   │   ├── evolve_tool_description.py    # CLI: python -m evolution.tools.evolve_tool_description
│   │   ├── tool_module.py                # ToolDescriptionStore + ToolDescriptionModule
│   │   ├── tool_dataset_builder.py       # ToolDescriptionDataset (task, tool_name) triples
│   │   ├── tool_description_v2.py       # GEPA v2 pipeline for tools
│   │   └── ingest_captured.py            # Phase 5 ingest CLI
│   │
│   ├── prompts/                          # Phase 3: System prompt (STUB)
│   ├── code/                             # Phase 4: Code evolution (STUB)
│   └── monitor/                          # Phase 5: Continuous loop (STUB)
│
├── datasets/
│   ├── skills/                           # 15 skill eval datasets (train/val/holdout JSONL)
│   ├── sessiondb_candidates.jsonl        # Raw SessionDB candidates (unreviewed)
│   └── sessiondb_enriched.jsonl          # Enriched + scored SessionDB examples
│
├── output/                               # Evolved skill outputs per run
│   └── <skill-name>/
│       └── <timestamp>/
│           ├── evolved_skill.md
│           ├── baseline_skill.md
│           └── report.json
│
├── stats/
│   └── evolution_stats.csv               # All 16 runs: timestamps, scores, Δ, timing
│
└── reports/                              # Phase 1 validation report PDF
```

---

## 8. Local Modifications

All patches live in `~/hermes0/hermes-agent-self-evolution/` (git worktree, separate from upstream):

| Patch | File | Issue Fixed |
|-------|------|-------------|
| **ghost-improvement fix** | `evolution/skills/skill_module_v2.py` | `_extract_evolved_skill_body` reads `predict.predict.__doc__` directly instead of relying on wrapper instructions. Prevents phantom score gains from eval dataset noise. |
| **nous_auth model-ID preservation** | `evolution/core/nous_auth.py` | Preserves full model IDs (`minimax/minimax-m2.7`) instead of bare names. Required for correct Nous API routing. |
| **CoT→Predict optimization** | `evolution/core/external_importers.py` | Replaces `dspy.ChainOfThought` with `dspy.Predict` in RelevanceFilter. Reduces scoring from 30s → 13s per call. |
| **SessionDB scoring** | `evolution/core/external_importers.py` | Still slow: 13s/call × 150 candidates. synthetic eval_source recommended for smaller skills. |

---

## 9. Known Issues and Technical Debt

### Critical

- **companion-roundtable dataset insufficient** — 1 train / 0 val / 0 holdout. Always produces 0.0/0.0 scores. Must expand to 10/5/5 before next run.
- **github-code-review dataset insufficient** — only 1 train example. Expansion needed.

### Performance

- **SessionDB relevance scoring slow** — 13s/call × 150 candidates. Not usable at scale. Use synthetic eval_source.
- **v1 MultiComponent bug** — fixed locally (forward() discarding outputs). Verify before next v1 run.

### Heuristics Requiring Validation

- **Router thresholds** — edge_case ≥80%, structural ≥60% are empirical heuristics, not validated against real failure distributions.
- **BacktrackController window** — 3-iter / 1% threshold is near the LLM noise floor (~±2–5%). May conflate noise with true performance ceilings.
- **PostHoc power-law fitting** — requires ≥3 data points; only works on score trajectories.

### Pipeline Status

- **v2.1 not used for production** — integration tests pass but no real GEPA runs have used `gepa_v2_dispatch` yet.
- **Three regressions uninvestigated** — companion-interview-pipeline (-4.85%), companion-safety (-4.58%), companion-memory (-3.99%) failed on holdout. Root cause unknown.

---

## 10. Guardrails

Every evolved variant must pass ALL of the following before deployment:

1. **Full test suite** — `pytest tests/ -q` must pass 100%
2. **Size limits** — Skills ≤15KB, tool descriptions ≤500 chars
3. **Caching compatibility** — No mid-conversation changes; all changes take effect on new sessions
4. **Semantic preservation** — Must not drift from original purpose
5. **Holdout regression gate** — Evolved must score ≥ baseline on holdout set
6. **PR review** — All changes go through human review; never direct commit

---

## 11. Benchmarks

Three benchmarks serve as regression gates (not fitness functions):

| Benchmark | Tests | Speed | Cost | Role |
|-----------|-------|-------|------|------|
| TBLite | 100 coding/sysadmin tasks | ~1–2 hours | ~$20–50 | Primary regression gate |
| TerminalBench2 | 89 harder tasks (requires Docker) | ~2–4 hours | ~$50–200 | Thorough validation |
| YC-Bench | 100–500 turn coherence | ~3–6 hours | ~$50–200 | Long-horizon check |

**Key principle:** Benchmarks are GATES, not fitness functions. A variant that improves skill quality by 20% but drops TBLite by 5% is **rejected**.

---

## 12. Usage Examples

### Run a skill evolution (production v1 pipeline)

```bash
cd ~/hermes0/hermes-agent-self-evolution

python -m evolution.skills.evolve_skill \
    --skill companion-workflows \
    --iterations 10 \
    --eval-source golden \
    --optimizer-model "minimax/minimax-m2.7" \
    --eval-model "minimax/minimax-m2.7" \
    --output-dir output/
```

### Run a tool description evolution

```bash
python -m evolution.tools.evolve_tool_description \
    --tool search_files \
    --iterations 5 \
    --eval-source synthetic \
    --optimizer-model "minimax/minimax-m2.7" \
    --eval-model "minimax/minimax-m2.7"
```

### List available skills for evolution

```bash
python -m evolution.skills.evolve_skill --help
```

### Check run history

```bash
cat stats/evolution_stats.csv
```

---

## 13. Git History

```
c139005  Phase 2: Tool description evolution pipeline          2026-04-29
519cc69  Phase 5 wrap: v2.1 fixes, companion-workflows run    2026-04-28
b05af91  Phase 5: CAPTURED mode — Hermes Agent plugin          2026-04-28
606588f  v2.2 integration: PostHocAnalyzer wired              2026-04-27
d83414e  Size-aware growth constraint + RelevanceFilter cap      2026-04-27
4844a40  ghost-improvement bug fix                              2026-04-26
7306d82  Apply merged upstream PRs (#24, #26, #35)            2026-04-25
4693c8f  Hermes session importer + short skill name fix        2026-03-29
3fb26f1  External session importers (Claude Code, Copilot)     2026-03-29
```

---

## 14. See Also

- `companion-system--evolution-pipeline.md` — Full wiki page with detailed Phase 1 results
- `captured-skill-ingest-pipeline.md` — Phase 5 captured skill ingest
- `gepa-v2-threshold-analysis.md` — Router threshold analysis
- `https://github.com/NousResearch/hermes-agent-self-evolution` — Upstream repository
- `https://hermes-agent.nousresearch.com` — Hermes Agent documentation
