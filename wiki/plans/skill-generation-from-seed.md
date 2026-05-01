# Skill Generation from Seed — Plan

**Status:** Phase 2 implemented + validated (seed → full 5-section SKILL.md via parallel GEPA)
**Created:** 2026-04-30 03:48
**Project:** hermes-agent-self-evolution

---

## Pivot

We've been running GEPA v2 on existing 11-section SKILL.md files for weeks. Results are mixed — some skills improve (+13.5% hermes-agent, +12.5% companion-workflows), but most are noise-level changes. The core problem: GEPA is designed to optimize **single prompts from scratch**, not edit 600-line procedural documents section by section. We're using a scalpel as a sledgehammer.

**New thesis:** Instead of evolving existing skills, build them from **seed prompts** using GEPA's native strength — iterative single-prompt optimization. A "seed" is a 1-3 sentence description of what the skill should do. GEPA grows it into a full SKILL.md.

This is closer to how GEPA was designed and evaluated (MMLU, GSM8K — single-prompt tasks). It should be faster, cheaper, and produce better results.

---

## Why This Works Better

| Aspect | Old (Evolve Existing) | New (Grow From Seed) |
|--------|----------------------|---------------------|
| Input size | ~600 lines, 11 sections | ~3 sentences |
| GEPA's optimization target | Mutate entire document → noisy gradients | Single prompt grows organically |
| Evaluation cost | 13s/call × 150 examples via SessionDB | 10-20 synthetic examples, fast |
| Meaningful change rate | ~30% of runs (7/24 positive) | Expected much higher |
| Human review burden | Diffing 600-line documents | Reviewing a clean generated doc |
| Time per skill | 3-8 minutes (but often noise) | Target: 1-3 minutes for a useful skill |

---

## Phases

### Phase 1: Proof of Concept — Single Component Generation (Day 1)

**Goal:** Prove GEPA can grow a useful single section of a skill from a seed.

**What:** Pick a simple skill. Feed GEPA the seed "Write a skill that teaches the agent how to search for arXiv papers." Generate ONLY the "Steps" section (not the full 11-section document). Evaluate quality with LLM-as-judge.

**Metrics:**
- Generation time under 3 minutes
- Cost under $0.50
- Generated steps actually useful (judged by Claude/Opus)

**Success criteria:** A single well-formed Steps section that a human would rate ≥7/10.

**Commands:**
```bash
python -m evolution.skills.seed_to_skill \
    --seed "Search arXiv for papers matching a topic" \
    --target-section steps \
    --iterations 5 \
    --eval-model "minimax/minimax-m2.7"
```

### Phase 2: seed_to_skill.py — Full Skill Generator (Days 2-3)

**Phase 2 Completion Log (2026-05-01)**
- Implemented end-to-end `seed_to_skill.py` pipeline:
  - Worker mode: `--target-section {steps,pitfalls,examples,constraints,verification}`
  - Full mode: `--full-skill` (parallel section generation + coherence check + assembly)
- GEPA/DSPy fixes applied to stabilize execution:
  - Structural-only GEPA fitness metric (required GEPA 5-arg signature).
  - Normalized DeepSeek model IDs (e.g. `deepseek-v4-flash` → `deepseek/deepseek-v4-flash`) to avoid “model not found”.
  - Added `.with_inputs("task_input")` to DSPy `Example` objects to prevent GEPA evaluator crashes.
  - Robust extraction of generated text from DSPy/Litellm response shapes (list/dict).
  - Fixed Rich markup crash in coherence PASS/ISSUES printing.
- Metadata standardization:
  - Frontmatter now uses YAML-native mappings only (no inline/raw JSON splicing inside YAML), via `_assemble_skill()`.
  - Output artifacts saved under `output/seed-generated/full-skill_<timestamp>/`.

**Validated run (arXiv seed)**
- Seed: `Search arXiv for papers matching a research topic`
- Exit code: success
- Coherence check: PASS
- Output (latest): see `output/seed-generated/full-skill_*/search-arxiv-for-papers-matching-a-resea.SKILL.md`

**Goal:** A script that takes a seed prompt → produces a complete 11-section SKILL.md.

**Architecture:**
```
seed (1-3 sentences)
    │
    ▼
Section-specific GEPA runs (parallel, one per section)
    │
    ├─► Title + Description  (GEPA run 1)
    ├─► Steps                (GEPA run 2)
    ├─► Pitfalls             (GEPA run 3)
    ├─► Examples             (GEPA run 4)
    ├─► Constraints          (GEPA run 5)
    └─► Verification         (GEPA run 6)
    │
    ▼
Assembly + Cross-section coherence check
    │
    ▼
Final SKILL.md
```

Each section gets its own GEPA run with section-specific evaluation. A final coherence pass ensures sections don't contradict each other.

**Key implementation decisions:**
- Parallel section generation (6 GEPA runs, max 3 concurrent to avoid API contention)
- Section-specific eval criteria (Steps get "procedure quality" rubric, Pitfalls get "realism" rubric, etc.)
- Coherence check: LLM reads all sections, flags contradictions

**Script location:** `evolution/skills/seed_to_skill.py`

### Phase 3: Batch Generation + Skill Library (Days 4-5)

**Goal:** Generate 10-20 new skills from seeds to prove the pipeline works at scale.

**Seeds to try:**
- Domain-specific skills (data-science, security, gaming)
- Cross-domain fusion skills (combining creative-ideation + code-review patterns)
- Missing companion skills
- Tool usage guides for under-documented tools

**Output:** A `generated-skills/` directory with each skill's SKILL.md + generation metadata (cost, time, seed, evaluation scores).

### Phase 4: Seed Refinement Loop (Day 6+)

**Goal:** Meta-optimization — evolve the seed-writing process itself.

If some seeds produce better skills than others, can we learn what makes a good seed? Run GEPA on seed text → evaluate quality of resulting skill → optimize seed writing.

---

## Technical Details

### Section-Specific Evaluation

Each section type needs its own rubric for GEPA's fitness function:

| Section | Evaluation Focus | Judge Prompt |
|---------|-----------------|-------------|
| Title/Description | Clarity, specificity, uniqueness | "Rate this skill description on how well it communicates what the skill does" |
| Steps | Procedure correctness, order, completeness | "Rate these steps on whether following them would achieve the skill's purpose" |
| Pitfalls | Realism, specificity, actionability | "Rate these pitfalls on whether they describe real issues an agent would encounter" |
| Examples | Diversity, clarity, realism | "Rate these examples on how well they illustrate the skill's usage" |
| Constraints | Relevance, precision, enforceability | "Rate these constraints on whether they're specific enough to actually constrain behavior" |
| Verification | Testability, completeness | "Rate this verification section on whether it provides clear pass/fail checks" |

### Model Strategy

- **Generation LM:** deepseek-v4-pro (via ollama-cloud) — strong creative output
- **Reflection LM:** deepseek-v4-flash — fast, cheap, good enough for evaluation
- **Judge LM:** minimax/minimax-m2.7 — known good at rubric-based scoring

### Cost Estimate

Per skill (6 sections × 5 GEPA iterations × ~10 synthetic examples):
- Generation: ~30 API calls (6 sections × 5 iterations)
- Evaluation: ~300 API calls (6 sections × 5 iterations × 10 examples)
- Total: ~330 calls × ~$0.001/call ≈ $0.33 per skill
- With coherence pass: ~$0.40/skill

At scale (20 skills): ~$8.00 total. Negligible.

---

## Risks & Unknowns

1. **Section coherence:** Can independently generated sections form a coherent whole? The coherence pass mitigates this but might not be sufficient.

2. **Seed quality sensitivity:** Some seeds may produce great skills, others garbage. Phase 4 addresses this but we need to validate the variance first.

3. **Prompt length creep:** GEPA might generate verbose sections. Constraint checking (char limits) is already in place from v2.

4. **Hallucinated capabilities:** A generated skill might claim the agent can do something it can't. Need factual validation step.

5. **Template lock-in:** If all generated skills follow the same 11-section template too rigidly, they lose character. Consider injecting style variation.

---

## Success Criteria

1. A single `seed_to_skill.py` that runs end-to-end from seed → valid SKILL.md
2. At least 3 generated skills rated ≥7/10 by human review
3. Generation time under 5 minutes per skill
4. Cost under $1.00 per skill

---

## Related

- `PLAN.md` — Master project plan (skill evolution, tool descriptions, system prompts)
- `gepa_kanban/board-state.md` — Current GEPA experiment tracking
- Memory: 2026-04-30 pivot decision to shift from evolve-existing to grow-from-seed
