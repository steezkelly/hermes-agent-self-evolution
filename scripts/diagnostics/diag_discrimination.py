#!/usr/bin/env python3
"""
Diagnostic: measure actual metric discrimination on a real skill + dataset.

Tests:
  1. Real skill body → agent response → compare TF-IDF vs sentence embeddings vs LLM judge
  2. Stripped skill body (no headings) → agent response → compare scores
  3. Shuffled paragraphs → agent response → compare scores

The "stripped > original" paradox found earlier should NOT happen if the metric
properly captures semantic quality.
"""

import sys
import os
from pathlib import Path

# Ensure GEPA repo is importable
GEPA_ROOT = Path.cwd()
sys.path.insert(0, str(GEPA_ROOT))

os.environ["TOKENIZERS_PARALLELISM"] = "false"

import dspy
from evolution.core.config import EvolutionConfig
from evolution.core.dataset_builder import SyntheticDatasetBuilder
from evolution.core.fitness import (
    _invoke_skill_as_agent,
    fit_global_scorer,
    fit_embedding_scorer,
    TFIDFSimilarityScorer,
    SentenceEmbeddingScorer,
    LLMJudge,
    FitnessScore,
)
from evolution.skills.skill_module import load_skill, find_skill
from evolution.core.nous_auth import _get_lm_kwargs


def load_skill_and_dataset(skill_name: str, num_cases: int = 5):
    config = EvolutionConfig(eval_dataset_size=num_cases)
    hermes_path = Path(os.environ.get("HERMES_PATH", str(Path.home() / ".hermes" / "hermes-agent")))
    skill_path = find_skill(skill_name, hermes_path)
    if not skill_path:
        raise FileNotFoundError(f"Skill {skill_name} not found in {hermes_path}")
    skill = load_skill(skill_path)
    builder = SyntheticDatasetBuilder(config)
    dataset = builder.generate(artifact_text=skill["raw"], artifact_type="skill", num_cases=num_cases)
    return skill, dataset


def strip_headings(body: str) -> str:
    lines = [l for l in body.splitlines() if not l.startswith("#")]
    return "\n".join(lines).strip()


def shuffle_paragraphs(body: str) -> str:
    paras = [p for p in body.split("\n\n") if p.strip()]
    import random
    random.seed(42)
    random.shuffle(paras)
    return "\n\n".join(paras)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GEPA metric discrimination diagnostic")
    parser.add_argument("--skill", default="systematic-debugging", help="Skill name to test")
    parser.add_argument("--cases", type=int, default=5, help="Synthetic eval cases to generate")
    parser.add_argument("--model", default="minimax/minimax-m2.7", help="Eval model")
    parser.add_argument("--judge-model", default=None, help="LLM judge model (defaults to --model)")
    args = parser.parse_args()

    if args.judge_model is None:
        args.judge_model = args.model

    print(f"=" * 70)
    print(f"GEPA Metric Discrimination Diagnostic")
    print(f"  Skill:       {args.skill}")
    print(f"  Eval model:  {args.model}")
    print(f"  Judge model: {args.judge_model}")
    print(f"  Cases:       {args.cases}")
    print(f"=" * 70)

    # Load skill + dataset
    print(f"\n[1] Loading skill & dataset...")
    skill, dataset = load_skill_and_dataset(args.skill, args.cases)
    body = skill["body"]
    print(f"  Body size: {len(body):,} chars, {body.count('##')} headings")
    print(f"  Dataset:   {len(dataset.train)} train / {len(dataset.val)} val / {len(dataset.holdout)} holdout")

    # Prepare variants
    stripped = strip_headings(body)
    shuffled = shuffle_paragraphs(body)
    all_examples = dataset.train + dataset.val + dataset.holdout
    dspy_examples = dataset.to_dspy_examples("train") + dataset.to_dspy_examples("val") + dataset.to_dspy_examples("holdout")

    print(f"\n[2] Preparing scorers...")
    # TF-IDF scorer — fit on ALL expected behaviors
    fit_global_scorer(dspy_examples)
    from evolution.core.fitness import _global_scorer
    tfidf = _global_scorer

    # Embedding scorer — fit on ALL expected behaviors
    fit_embedding_scorer(dspy_examples)
    from evolution.core.fitness import _embed_scorer
    embed = _embed_scorer

    # LLM Judge
    judge_config = EvolutionConfig(eval_model=args.judge_model)
    judge = LLMJudge(judge_config)

    # Configure eval LM
    lm_kwargs, model_used = _get_lm_kwargs(args.model)
    lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    results = []

    for idx, ex in enumerate(all_examples):
        task = ex.task_input
        expected = ex.expected_behavior
        print(f"\n[3.{idx+1}] Example {idx+1}/{len(all_examples)}")
        print(f"  TASK:      {task[:100]}...")
        print(f"  EXPECTED:  {expected[:100]}...")

        for label, variant_body in [("ORIGINAL", body), ("STRIPPED", stripped), ("SHUFFLED", shuffled)]:
            print(f"\n    → {label} (len={len(variant_body):,})")
            # Invoke
            try:
                agent_output = _invoke_skill_as_agent(variant_body, task)
                print(f"      Output:  {agent_output[:120]}... (len={len(agent_output)})")
            except Exception as exc:
                agent_output = "[INFERENCE FAILED]"
                print(f"      FAILED:  {exc}")

            # Score: TF-IDF
            tfidf_score = tfidf.score(agent_output, expected) if tfidf and tfidf._fitted else None
            print(f"      TF-IDF:   {tfidf_score}")

            # Score: Sentence Embedding
            embed_score = embed.score(agent_output, expected) if embed and embed._fitted else None
            print(f"      Embed:    {embed_score}")

            # Score: LLM Judge (slow, one per variant)
            try:
                judge_score = judge.score(
                    task_input=task,
                    expected_behavior=expected,
                    agent_output=agent_output,
                    skill_text=variant_body[:2000],
                )
                print(f"      Judge:    correctness={judge_score.correctness:.2f}, proc={judge_score.procedure_following:.2f}, conciseness={judge_score.conciseness:.2f}, composite={judge_score.composite:.2f}")
            except Exception as exc:
                judge_score = None
                print(f"      Judge:    FAILED ({exc})")

            results.append({
                "example": idx + 1,
                "label": label,
                "output_len": len(agent_output),
                "tfidf": tfidf_score,
                "embed": embed_score,
                "judge": judge_score.composite if judge_score else None,
                "judge_correctness": judge_score.correctness if judge_score else None,
                "judge_procedure": judge_score.procedure_following if judge_score else None,
                "judge_conciseness": judge_score.conciseness if judge_score else None,
            })

    # Summary
    print(f"\n" + "=" * 70)
    print(f"SUMMARY")
    print(f"=" * 70)

    import pandas as pd
    df = pd.DataFrame(results)
    if not df.empty:
        for metric in ["tfidf", "embed", "judge"]:
            if metric not in df.columns or df[metric].isna().all():
                continue
            pivot = df.groupby("label")[metric].mean()
            print(f"\n  {metric.upper()} mean scores:")
            for label in ["ORIGINAL", "STRIPPED", "SHUFFLED"]:
                if label in pivot.index:
                    print(f"    {label:12} {pivot[label]:.4f}")
            # Delta: original minus worst
            best = pivot.get("ORIGINAL", 0)
            worst = min(pivot.get("STRIPPED", 0), pivot.get("SHUFFLED", 0))
            delta = best - worst
            print(f"    ORIGINAL - worst variant delta: {delta:.4f}")
            if delta < 0.1:
                print(f"    ⚠️  WARNING: Delta < 0.1 — metric may not discriminate well!")
            if delta > 0.2:
                print(f"    ✅ Delta > 0.2 — decent discrimination")
            if delta > 0.4:
                print(f"    ✅✅ Delta > 0.4 — strong discrimination")

    # Save results
    out = Path("output/metric_discrimination_results.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\n  Results saved to: {out}")


if __name__ == "__main__":
    main()
