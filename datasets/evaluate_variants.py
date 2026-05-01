#!/usr/bin/env python3
"""
Skill Variant Evaluator — companion-memory
=========================================
Creates 4 skill variants, evaluates each on the 15 valset examples
using the sentence embedding scorer, and picks the winner.

Usage: .venv/bin/python3 evaluate_variants.py
"""
import json, os, sys, time
from pathlib import Path
from typing import Optional

import dspy
import numpy as np
from sentence_transformers import SentenceTransformer

# ── Configuration ──────────────────────────────────────────
SKILL_NAME = "companion-memory"
DATASET_DIR = Path("datasets/skills/companion-memory")
SKILL_PATH = Path.home() / ".hermes" / "skills" / "companion-system" / "companion-memory" / "SKILL.md"
VENV_PYTHON = ".venv/bin/python3"
OUTPUT_FILE = "variant_evaluation_results.json"

# ── Load the original skill body ───────────────────────────
def load_skill_body(path: Path) -> str:
    raw = path.read_text()
    if raw.strip().startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return raw.strip()

original_body = load_skill_body(SKILL_PATH)
print(f"Original skill body: {len(original_body)} chars")

# ── Skill variants ─────────────────────────────────────────
# Each variant is a modified version of the skill body.
# We append/enhance sections based on GEPA-discovered patterns.

# Variant B: Add "Response Strategy" section
variant_b_body = original_body + """

## Response Strategy

When answering memory-related questions, follow this approach:

### 1. Understand the User's Question
- Identify what the user is actually asking about: session vs global scope, consolidation behavior, working memory cleanup, provider constraints, tool usage, etc.
- Determine which layer(s) of the memory stack are relevant to their issue
- Do NOT default to reciting the Three-Layer Stack or architecture overview

### 2. Provide Targeted Answers
- Address the specific problem rather than dumping documentation
- Explain relevant memory concepts (scopes, tiers, consolidation limits) only when they help
- Suggest concrete actions the user can take

### 3. When to Include Architecture Details
Include Three-Layer Stack or constraint information ONLY when it directly helps answer:
- If the user asks "why can't I find my session memory?" → explain working vs persistent memory
- If the user asks about consolidation → explain how mnemosyne_sleep works with BEAM tiers
- If the user asks about cleanup → explain working vs long-term storage management
- If the user asks about provider changes → explain the single-provider constraint

### Response Format
- Lead with a direct answer to the question
- Use concise language, not excessive documentation
- Reference relevant paths, commands, or configuration options
- End with actionable suggestions when applicable
"""

# Variant C: Add "When to Include" rules for each major section
variant_c_body = original_body + """

## When to Include Architecture Sections

### Three-Layer Stack Section
**Include when** the user asks about:
- How the three memory layers relate
- What MEMORY.md/Mnemosyne/wiki each do
- Whether layers can be replaced or stacked
- Provider selection or migration

**Exclude when** the user asks about:
- Tool usage details (which mnemosyne function to use)
- Health checks or statistics
- Troubleshooting specific errors
- Design principles or best practices

### Single Provider Constraint Section
**Include when** the user asks about:
- Using two providers simultaneously
- Stacking providers as caches or tiers
- Provider registration or the MemoryManager
- Migrating between providers

**Exclude when** the user asks about:
- Querying/searching memories
- Error debugging (ModuleNotFoundError, sqlite errors, ImportError)
- API usage (mnemosyne_triple_add, mnemosyne_stats, mnemosyne_sleep)
- Configuration of thresholds or importance

### BEAM Tiers Section
**Include when** the user asks about:
- How Mnemosyne organizes memories internally
- Working vs episodic vs archival storage
- Consolidation behavior and memory lifecycles
- Embedding coverage and vector search

**Exclude when** the user asks about:
- High-level architecture questions (direct to Three-Layer Stack)
- Wiki or external store questions

### Detecting Current State Section
**Include only when** the user asks about checking current configuration, provider status, or troubleshooting memory functionality issues.

### Response Format
- Lead with the answer to the question
- Provide technical details, examples, or troubleshooting steps
- Reference relevant tools, tables, or configuration options
"""

# Variant D: Full fusion — Variant B + C + query-type routing + anti-patterns
variant_d_body = original_body + """

## Response Strategy

### Query Type Classification
Identify the user's question type and respond accordingly:

| Question Type | Examples | Response Strategy |
|--------------|----------|-----------------|
| **Conceptual/Explanatory** | "How does X work?", "What is Y?" | Identify the specific concept, extract relevant knowledge, provide focused explanation without unnecessary sections |
| **Troubleshooting/Diagnostic** | "Why isn't X working?", "Is this a bug?" | Identify the symptom, cross-reference with known system behaviors, provide actionable insights, confirm/normalcy assessment |
| **Configuration/Usage** | "How do I set up X?", "Can I use Y and Z together?" | Provide direct guidance based on documented capabilities, clearly state limitations, include relevant commands/paths/config |
| **Design/Best Practice** | "What's the recommended approach?", "Should I do X or Y?" | Present trade-offs, reference design principles (capture broadly/curate narrowly), give concrete recommendations |

### When to Include Each Section
#### Three-Layer Stack
Include ONLY when the question is about layer relationships, provider selection, or architecture. NOT for tool usage, errors, or health checks.

#### Single Provider Constraint
Include ONLY when the question involves running two providers, stacking caches, or provider migration. NOT for querying, debugging, or API usage.

#### BEAM Tiers
Include when the question is about memory organization, consolidation, embeddings, or tiers.

#### Detecting Current State
Include ONLY when checking current configuration or troubleshooting functionality.

### Anti-Patterns to Avoid
- **DO NOT** regurgitate the Three-Layer Stack or constraint section for every question
- **DO NOT** include sections "just in case" — each section must earn its place
- **DO NOT** answer a question about tool usage with architecture documentation
- **DO NOT** include the single-provider constraint when the question is about error debugging

### Response Format
- Lead with a direct answer to the specific question
- Provide technical details, examples, or troubleshooting steps as appropriate
- Reference relevant tools, commands, paths, or configuration
- If the Three-Layer Stack or constraint sections provide necessary context, include them briefly; otherwise omit them
- End with actionable next steps when applicable
"""

variants = {
    "A (baseline)": original_body,
    "B (targeted-response)": variant_b_body,
    "C (constraint-aware)": variant_c_body,
    "D (full-fusion)": variant_d_body,
}

print(f"\nVariant sizes:")
for name, body in variants.items():
    print(f"  {name}: {len(body)} chars")

# ── Load dataset ───────────────────────────────────────────
from evolution.core.dataset_builder import GoldenDatasetLoader, EvalDataset

dataset = GoldenDatasetLoader.load(DATASET_DIR)
print(f"\nDataset: {len(dataset.train)} train, {len(dataset.val)} val, {len(dataset.holdout)} holdout")

# ── Set up LM ──────────────────────────────────────────────
# Get MiniMax key from auth
auth_path = Path.home() / ".hermes" / "auth.json"
with open(auth_path) as f:
    auth = json.load(f)
cred = auth["credential_pool"]["minimax"][0]
key = cred["access_token"]
base_url = "https://api.minimax.io/anthropic/v1"

os.environ["MINIMAX_API_KEY"] = key
os.environ["MINIMAX_BASE_URL"] = base_url
os.environ["OPENAI_API_KEY"] = key
os.environ["OPENAI_BASE_URL"] = base_url

lm = dspy.LM("minimax-m2.7", api_base=base_url, custom_llm_provider="openai", num_retries=8)
dspy.configure(lm=lm)

# ── Set up sentence embedding scorer ───────────────────────
from evolution.core.fitness import fit_embedding_scorer, fit_global_scorer, clear_global_scorer
from evolution.core.fitness import SentenceEmbeddingScorer

print("\nFitting scorers...")
clear_global_scorer()
embed_scorer = fit_embedding_scorer(dataset.to_dspy_examples("train") + dataset.to_dspy_examples("val"))
fit_global_scorer(dataset.to_dspy_examples("train") + dataset.to_dspy_examples("val"))
print("  Scorers fitted")

# ── SkillModule ────────────────────────────────────────────
from evolution.skills.skill_module import SkillModule

def evaluate_variant(skill_body: str, valset: list) -> dict:
    """Evaluate a skill variant on the valset, returning per-example scores."""
    module = SkillModule(skill_body)
    scores = []
    responses = []
    
    for i, ex in enumerate(valset):
        task = getattr(ex, "task_input", "")
        expected = getattr(ex, "expected_behavior", "")
        if not task.strip():
            continue
        
        try:
            prediction = module.forward(task)
            response = getattr(prediction, "output", "")
            score = embed_scorer.score(response, expected)
        except Exception as e:
            response = f"[error: {e}]"
            score = 0.0
        
        scores.append(score)
        responses.append({"task_input": task[:80], "score": score, "response_len": len(response)})
        
        if (i + 1) % 5 == 0:
            print(f"    {i+1}/{len(valset)} examples scored")
    
    avg_score = sum(scores) / max(len(scores), 1)
    return {
        "avg_score": avg_score,
        "per_example_scores": scores,
        "total_score": sum(scores),
        "num_examples": len(scores),
        "details": responses,
    }

# ── Evaluate each variant ──────────────────────────────────
results = {}
valset = dataset.to_dspy_examples("val")
print(f"\nEvaluating {len(variants)} variants on {len(valset)} valset examples...")
print(f"Each example requires an LLM call (~10-15s each). Total: ~{len(valset) * len(variants) * 12 // 60} min\n")

for name, body in variants.items():
    print(f"\n{'='*60}")
    print(f"  Evaluating variant: {name}")
    print(f"{'='*60}")
    start = time.time()
    result = evaluate_variant(body, valset)
    elapsed = time.time() - start
    results[name] = result
    print(f"  Avg score: {result['avg_score']:.4f}")
    print(f"  Time: {elapsed:.0f}s")

# ── Results table ──────────────────────────────────────────
print(f"\n\n{'='*60}")
print(f"  RESULTS COMPARISON")
print(f"{'='*60}")
print(f"{'Variant':<25} {'Avg Score':<12} {'Total':<10} {'Examples':<10}")
print(f"{'-'*25} {'-'*12} {'-'*10} {'-'*10}")
for name, result in sorted(results.items(), key=lambda x: x[1]["avg_score"], reverse=True):
    print(f"{name:<25} {result['avg_score']:.4f}       {result['total_score']:.4f}  {result['num_examples']}")

winner = max(results.items(), key=lambda x: x[1]["avg_score"])
print(f"\n  🏆 WINNER: {winner[0]} — score: {winner[1]['avg_score']:.4f}")
print(f"  Baseline score: {results.get('A (baseline)', {}).get('avg_score', 0):.4f}")
print(f"  Improvement: {winner[1]['avg_score'] - results.get('A (baseline)', {}).get('avg_score', 0):.4f}")

# ── Save results ───────────────────────────────────────────
output = {
    "skill": SKILL_NAME,
    "timestamp": time.strftime("%Y%m%d_%H%M%S"),
    "variants": {
        name: {
            "avg_score": r["avg_score"],
            "total_score": r["total_score"],
            "num_examples": r["num_examples"],
            "per_example_scores": [round(s, 4) for s in r["per_example_scores"]],
        }
        for name, r in results.items()
    },
    "winner": winner[0],
    "winner_score": winner[1]["avg_score"],
    "baseline_score": results.get("A (baseline)", {}).get("avg_score", 0),
    "improvement": winner[1]["avg_score"] - results.get("A (baseline)", {}).get("avg_score", 0),
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(output, f, indent=2)

print(f"\nResults saved to {OUTPUT_FILE}")

# ── Write winning variant ──────────────────────────────────
# Only if improvement is positive
if winner[1]["avg_score"] > results.get("A (baseline)", {}).get("avg_score", 0):
    win_body = variants[winner[0]]
    # Get frontmatter
    with open(SKILL_PATH) as f:
        raw = f.read()
    frontmatter = ""
    if raw.strip().startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1].strip()
    
    new_content = f"---\n{frontmatter}\n---\n\n{win_body}\n"
    # Don't overwrite the live file - write to output dir
    output_path = Path("output") / SKILL_NAME / f"evolved_{winner[0].split()[0].lower()}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(new_content)
    print(f"Winning variant written to {output_path}")
else:
    print("Winner did not improve over baseline — not writing variant")
