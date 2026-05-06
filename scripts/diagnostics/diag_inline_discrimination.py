#!/usr/bin/env python3
"""
Self-contained diagnostic: measure metric discrimination with inline test skill.

Uses a small test skill body (like a debugging checklist), generates synthetic
task inputs + expected behaviors, then compares ORIGINAL vs STRIPPED vs SHUFFLED
across TF-IDF, sentence embeddings, and LLM judge scoring.

If STRIPPED scores higher than ORIGINAL, the metric is broken.
"""

import sys, os
from pathlib import Path

GEPA_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(GEPA_ROOT))
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import dspy
import numpy as np
from evolution.core.fitness import (
    _invoke_skill_as_agent,
    fit_global_scorer,
    fit_embedding_scorer,
    TFIDFSimilarityScorer,
    SentenceEmbeddingScorer,
    LLMJudge,
)
from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs

# ─── Test skill body — a real-looking debugging checklist ──────────────────
TEST_BODY = """# Systematic Debugging Skill

## Step 1: Reproduce the Bug
Run the failing command exactly as reported. Capture the full error trace, exit code, and any stderr output. Do not skip this — it sets the foundation.

## Step 2: Hypothesize Root Cause
Read the error message line by line. Identify the exact error type (KeyError, ImportError, etc.) and the file/line number that triggers it. Form a single explicit hypothesis: "X causes Y because Z".

## Step 3: Build Minimal Reproduction
Create the smallest possible test case that triggers the error. Remove unrelated code, dependencies, and data. This isolates whether the problem is truly in X or an interaction.

## Step 4: Run Diagnostic Tests
For each hypothesis, design one diagnostic test that would prove or disprove it. Use stdout prints, temporary assertions, or a debugger breakpoint. Collect evidence before forming conclusions.

## Step 5: Fix and Verify
Implement the fix that the evidence points to. Run the minimal reproduction first. Then run the full original failing command. Only then consider the bug resolved.
"""

# ─── Structure-bound tasks — answers depend on the skill's exact step order ──
TASKS = [
    (
        "A user reports a bug but hasn't reproduced it yet. What should they do FIRST according to the skill?",
        "Reproduce the bug first by running the failing command exactly as reported and capturing the full error trace. This is step 1.",
    ),
    (
        "After reproducing the bug, what is the NEXT step in the skill's exact procedure?",
        "Hypothesize the root cause. Read the error message line by line, identify the exact error type and file/line, and form a single explicit hypothesis.",
    ),
    (
        "Forming a hypothesis should come BEFORE building a minimal reproduction. What must happen AFTER forming a hypothesis?",
        "Build a minimal reproduction. Create the smallest possible test case that triggers the error and remove unrelated code.",
    ),
    (
        "The user wants to add a try/except block around the failing code rather than debugging. What does the skill say about this?",
        "The skill explicitly says to build a minimal reproduction and run diagnostic tests first. Using try/except as a workaround without understanding the root cause is discouraged.",
    ),
    (
        "What is the FINAL step in the skill's procedure, and what must be true before marking it complete?",
        "Fix and verify. Implement the fix the evidence points to, then run the minimal reproduction first, then run the full original failing command.",
    ),
]


def strip_headings(body: str) -> str:
    return "\n".join(l for l in body.splitlines() if not l.strip().startswith("#")).strip()


def shuffle_paragraphs(body: str) -> str:
    import random
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    random.seed(42)
    shuffled = paragraphs[:]
    random.shuffle(shuffled)
    return "\n\n".join(shuffled)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Inline metric discrimination test")
    parser.add_argument("--model", default="minimax/minimax-m2.7", help="Eval model")
    parser.add_argument("--judge-model", default=None, help="LLM judge model")
    args = parser.parse_args()
    if args.judge_model is None:
        args.judge_model = args.model

    print(f"=" * 70)
    print(f"INLINE SKILL DISCRIMINATION TEST")
    print(f"  Eval model:  {args.model}")
    print(f"  Judge model: {args.judge_model}")
    print(f"=" * 70)

    body = TEST_BODY
    stripped = strip_headings(body)
    shuffled = shuffle_paragraphs(body)

    print(f"\nBody sizes: original={len(body)}, stripped={len(stripped)}, shuffled={len(shuffled)}")

    # Build dspy Examples
    dspy_examples = [
        dspy.Example(task_input=t, expected_behavior=e).with_inputs("task_input")
        for t, e in TASKS
    ]
    expected_texts = [e for _, e in TASKS]

    # Fit TF-IDF
    print(f"\n[1] Fitting TF-IDF scorer...")
    fit_global_scorer(dspy_examples)
    from evolution.core.fitness import _global_scorer as tfidf

    # Fit embeddings
    print(f"[2] Fitting sentence embedding scorer...")
    fit_embedding_scorer(dspy_examples)
    from evolution.core.fitness import _embed_scorer as embed

    # Configure LM
    lm_kwargs, model_used = _get_lm_kwargs(args.model)
    dspy_lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=dspy_lm)

    # Judge
    judge_config = EvolutionConfig(eval_model=args.judge_model)
    judge = LLMJudge(judge_config)

    results = []
    for idx, (task, expected) in enumerate(TASKS, 1):
        print(f"\n[3.{idx}] Task: {task[:80]}...")
        print(f"    Expected: {expected[:80]}...")

        for label, variant_body in [("ORIGINAL", body), ("STRIPPED", stripped), ("SHUFFLED", shuffled)]:
            try:
                output = _invoke_skill_as_agent(variant_body, task)
                output_preview = output[:100].replace("\n", " ") + f"... (len={len(output)})"
            except Exception as exc:
                output = ""
                output_preview = f"[FAILED: {exc}]"

            # TF-IDF
            tf_score = tfidf.score(output, expected) if tfidf and tfidf._fitted else 0.5
            # Embedding
            emb_score = embed.score(output, expected) if embed and embed._fitted else 0.5
            # Judge
            try:
                js = judge.score(task_input=task, expected_behavior=expected, agent_output=output, skill_text=variant_body[:2000])
                judge_comp = js.composite
                judge_corr = js.correctness
            except Exception as exc:
                judge_comp = None
                judge_corr = None

            print(f"    {label:10} | tf={tf_score:.4f} emb={emb_score:.4f} judge={judge_comp if judge_comp is not None else 'FAIL':<7} | {output_preview}")

            results.append({
                "task": idx,
                "variant": label,
                "output_len": len(output),
                "tfidf": tf_score,
                "embed": emb_score,
                "judge": judge_comp,
                "judge_corr": judge_corr,
            })

    print(f"\n" + "=" * 70)
    print(f"AGGREGATE SCORES (mean across {len(TASKS)} tasks)")
    print(f"=" * 70)

    def mean_for(label: str, metric: str):
        vals = [r[metric] for r in results if r["variant"] == label and r[metric] is not None]
        return sum(vals) / max(1, len(vals))

    for label in ["ORIGINAL", "STRIPPED", "SHUFFLED"]:
        tf = mean_for(label, "tfidf")
        emb = mean_for(label, "embed")
        judge = mean_for(label, "judge")
        print(f"  {label:10} : TF-IDF={tf:.4f}  Embed={emb:.4f}  Judge={judge:.4f}")

    # Check discrimination
    for metric_name, metric_key in [("TF-IDF", "tfidf"), ("Embed", "embed"), ("Judge", "judge")]:
        orig = mean_for("ORIGINAL", metric_key)
        stripped_score = mean_for("STRIPPED", metric_key)
        shuffled_score = mean_for("SHUFFLED", metric_key)
        worst = min(stripped_score, shuffled_score)
        delta = orig - worst
        status = "✅" if delta > 0.1 else ("⚠️" if delta > 0.05 else "🚨 FAIL")
        print(f"\n  {metric_name:8} discrimination: ORIGINAL - worst = {delta:.4f}  {status}")

    # Save
    import csv
    csv_path = Path("output/inline_discrimination.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Results saved to: {csv_path}")


if __name__ == "__main__":
    main()
