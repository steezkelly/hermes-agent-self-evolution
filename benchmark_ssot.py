#!/usr/bin/env python3
"""
Benchmark: SSoT (String Seed of Thought) vs Baseline Synthetic Dataset Generation
Compares two approaches to generating synthetic eval cases from skill artifacts:
  A) Baseline: dspy.ChainOfThought + robust multi-strategy JSON parsing
  B) SSoT: dspy.Predict + forced entropy seed + XML-tagged output extraction

Metrics:
  - Parse success rate (% of generations producing valid JSON)
  - Semantic diversity (mean pairwise TF-IDF cosine distance of task_inputs)
  - Cases per run (how many cases survived parsing)
  - Latency (seconds per case)

Usage:
  python benchmark_ssot.py [--skills-dir ~/.hermes/skills] [--runs 3] [--model "minimax/minimax-m2.7"]

Will create benchmark_results.json with per-skill and aggregate statistics.
"""

import argparse
import asyncio
import ast
import json
import os
import random
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path

import dspy
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from evolution.core.config import EvolutionConfig
from evolution.core.dataset_builder import (
    EvalExample,
    EvalDataset,
    SyntheticDatasetBuilder,
    _try_parse_json,
)


# ─────────────────────────────────────────────────────────────────────────────
# SSoT Implementation (clean, non-breaking)
# ─────────────────────────────────────────────────────────────────────────────

class SSOTSignature(dspy.Signature):
    """SSoT prompt signature: forces entropy generation before task output.

    The model must output:
      <ssot_random_string>TOKEN</ssot_random_string>
      <ssot_math_cot>HASH computation</ssot_math_cot>
      <payload_json>[...cases...]</payload_json>
    """
    text: str = dspy.InputField(desc="The text to test")
    type: str = dspy.InputField(desc="The type of artifact")
    batch_size: int = dspy.InputField(desc="Number of cases")
    seed: str = dspy.InputField(desc="Entropy seed")

    output: str = dspy.OutputField(
        desc="Combined SSoT stream: <ssot_random_string>, <ssot_math_cot>, <payload_json>"
    )


def extract_ssot_payload(raw_output: str) -> list | None:
    """Extract JSON from SSoT XML-tagged output. Returns None on failure."""
    if not raw_output:
        return None

    # Try the XML tag extraction first
    json_match = re.search(r'<payload_json>(.*?)</payload_json>', raw_output, re.DOTALL)
    json_text = json_match.group(1).strip() if json_match else raw_output

    # Clean markdown debris
    clean = re.sub(r'^```json\s*|```$', '', json_text.strip(), flags=re.MULTILINE)

    # Try standard JSON parse
    try:
        result = json.loads(clean)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: try our robust parser on the extracted text
    return _try_parse_json(clean)


def build_ssot_prompt(artifact_text: str, artifact_type: str, batch_size: int) -> str:
    """Build the reinforced SSoT prompt with instruction repetition for small models."""
    safe_text = artifact_text[:3000] + "..." if len(artifact_text) > 3000 else artifact_text
    return (
        f"{safe_text}\n\n"
        f"REPEATED INSTRUCTION: Generate {batch_size} synthetic test case(s) "
        f"for the above {artifact_type}. Output ONLY a JSON list of objects. "
        f"Response MUST start with [ and end with ].\n"
        f"Follow the SSoT protocol: first output a random 8-char alphanumeric seed, "
        f"then do a brief reasoning trace, then output the JSON."
    )


async def generate_with_ssot(
    artifact_text: str,
    artifact_type: str = "skill",
    num_cases: int = 5,
    model: str = "minimax/minimax-m2.7",
    api_base: str | None = None,
    api_key: str | None = None,
) -> tuple[list[EvalExample], str | None]:
    """
    Generate eval cases using the SSoT (String Seed of Thought) protocol.

    Returns (examples, error_message).
    error_message is None on success.
    """
    from evolution.core.nous_auth import _get_lm_kwargs

    lm_kwargs, model_used = _get_lm_kwargs(model)
    lm_kwargs.update({
        "cache": False,
        "max_tokens": 2000,
        "temperature": 0.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 1.0,
    })
    if api_base:
        lm_kwargs["api_base"] = api_base
    if api_key:
        lm_kwargs["api_key"] = api_key

    generator = dspy.Predict(SSOTSignature)

    semaphore = asyncio.Semaphore(2)
    tasks = []

    async def run_one(seed: str):
        async with semaphore:
            return await asyncio.to_thread(_run_single_ssot, seed, model_used, lm_kwargs, generator, artifact_text, artifact_type)

    for _ in range(num_cases):
        tasks.append(run_one(str(uuid.uuid4())[:8]))

    results = await asyncio.gather(*tasks)
    examples = []
    errors = []

    for ex, err in results:
        if ex:
            examples.extend(ex)
        if err:
            errors.append(err)

    error_msg = "; ".join(errors[:3]) if errors else None
    return examples, error_msg


def _run_single_ssot(seed: str, model: str, lm_kwargs: dict, generator, artifact_text: str, artifact_type: str) -> tuple[list[EvalExample], str | None]:
    """Run a single SSoT generation in a thread."""
    try:
        import nest_asyncio
        nest_asyncio.apply()
    except Exception:
        pass  # Already applied or not needed

    prompt = build_ssot_prompt(artifact_text, artifact_type, batch_size=1)
    lm = dspy.LM(model, **lm_kwargs)

    with dspy.context(lm=lm):
        result = generator(text=prompt, type=artifact_type, batch_size=1, seed=seed)

    raw_output = getattr(result, "output", "") or ""
    cases = extract_ssot_payload(raw_output)

    if cases is None:
        return [], f"Failed to parse: {raw_output[:100]!r}"

    examples = []
    for c in cases:
        if not isinstance(c, dict):
            continue
        examples.append(EvalExample(
            task_input=c.get("task_input", ""),
            expected_behavior=c.get("expected_behavior", ""),
            difficulty=c.get("difficulty", "medium"),
            category=c.get("category", "general"),
            source="synthetic-ssot",
        ))

    return examples, None


def run_baseline_sync(
    artifact_text: str,
    artifact_type: str = "skill",
    num_cases: int = 5,
    model: str = "minimax/minimax-m2.7",
) -> tuple[list[EvalExample], str | None]:
    """Run the baseline ChainOfThought generator. Synchronous version."""
    from evolution.core.nous_auth import _get_lm_kwargs

    config = EvolutionConfig()
    builder = SyntheticDatasetBuilder(config)

    lm_kwargs, model_used = _get_lm_kwargs(model)
    lm_kwargs["num_retries"] = 8

    lm = dspy.LM(model_used, **lm_kwargs)
    generator = dspy.ChainOfThought(builder.GenerateTestCases)

    try:
        with dspy.context(lm=lm):
            result = generator(
                artifact_text=artifact_text,
                artifact_type=artifact_type,
                num_cases=num_cases,
            )

        cases_raw = _try_parse_json(getattr(result, "test_cases", "") or "")
        if cases_raw is None:
            return [], f"JSON parse failed: {getattr(result, 'test_cases', '')[:100]!r}"

        examples = []
        for c in cases_raw:
            if not isinstance(c, dict):
                continue
            if not c.get("task_input") or not c.get("expected_behavior"):
                continue
            examples.append(EvalExample(
                task_input=c["task_input"],
                expected_behavior=c["expected_behavior"],
                difficulty=c.get("difficulty", "medium"),
                category=c.get("category", "general"),
                source="synthetic-baseline",
            ))

        return examples, None

    except Exception as e:
        return [], str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Diversity Metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_diversity(task_inputs: list[str]) -> float:
    """
    Compute mean pairwise TF-IDF cosine distance.
    Higher = more diverse. 0 = all identical.
    """
    if len(task_inputs) < 2:
        return 0.0

    texts = [ti for ti in task_inputs if ti.strip()]
    if len(texts) < 2:
        return 0.0

    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words='english',
            ngram_range=(1, 2),
            max_features=1000,
        )
        tfidf = vectorizer.fit_transform(texts)
        sim_matrix = cosine_similarity(tfidf)
        n = len(texts)

        # Mean of off-diagonal elements
        total_sim = sim_matrix.sum() - n  # subtract diagonal (self-similarity = 1.0)
        num_pairs = n * (n - 1)
        mean_sim = total_sim / num_pairs if num_pairs > 0 else 0.0

        # Convert similarity to diversity score (1 - similarity)
        diversity = 1.0 - mean_sim
        return round(float(diversity), 4)

    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Runner
# ─────────────────────────────────────────────────────────────────────────────

def load_skills(skills_dir: Path, count: int = 5, min_size: int = 500, max_size: int = 30000) -> list[tuple[str, Path]]:
    """Load diverse skills from the skills directory."""
    skills = []
    for skill_path in sorted(skills_dir.rglob("SKILL.md")):
        size = skill_path.stat().st_size
        if min_size <= size <= max_size:
            skills.append((skill_path.read_text(), skill_path))
        if len(skills) >= count:
            break
    return skills


def run_benchmark(
    skills: list[tuple[str, Path]],
    runs_per_skill: int = 3,
    cases_per_run: int = 5,
    model: str = "minimax/minimax-m2.7",
    api_base: str | None = None,
    api_key: str | None = None,
) -> dict:
    """
    Run the full benchmark comparing baseline vs SSoT across skills and runs.

    Returns a results dict ready for JSON serialization.
    """
    results = {
        "config": {
            "skills_count": len(skills),
            "runs_per_skill": runs_per_skill,
            "cases_per_run": cases_per_run,
            "model": model,
            "api_base": api_base,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "per_skill": [],
        "aggregate": {
            "baseline": {"parse_success_rate": 0.0, "mean_diversity": 0.0, "total_runs": 0, "total_cases": 0},
            "ssot": {"parse_success_rate": 0.0, "mean_diversity": 0.0, "total_runs": 0, "total_cases": 0},
        },
    }

    # Aggregate counters
    agg = {"baseline": {"success": 0, "total": 0, "diversities": [], "all_cases": 0},
           "ssot":    {"success": 0, "total": 0, "diversities": [], "all_cases": 0}}

    for skill_text, skill_path in skills:
        skill_name = f"{skill_path.parent.parent.name}/{skill_path.parent.name}"
        print(f"\n{'='*60}")
        print(f"  Skill: {skill_name} ({len(skill_text)} chars)")
        print(f"{'='*60}")

        skill_result = {
            "skill": skill_name,
            "baseline": {"runs": [], "parse_success_rate": 0.0, "mean_diversity": 0.0},
            "ssot":    {"runs": [], "parse_success_rate": 0.0, "mean_diversity": 0.0},
        }

        for run_i in range(runs_per_skill):
            print(f"\n  Run {run_i + 1}/{runs_per_skill}")

            # ── Baseline ──────────────────────────────────────────────
            print(f"    [BASELINE] generating {cases_per_run} cases...", end=" ", flush=True)
            t0 = time.time()
            baseline_examples, baseline_err = run_baseline_sync(
                skill_text, "skill", cases_per_run, model
            )
            baseline_elapsed = time.time() - t0

            baseline_success = baseline_err is None and len(baseline_examples) > 0
            baseline_diversity = compute_diversity([e.task_input for e in baseline_examples])
            baseline_cases = len(baseline_examples)

            run_result = {
                "run": run_i + 1,
                "success": baseline_success,
                "cases_generated": baseline_cases,
                "diversity": baseline_diversity,
                "elapsed_seconds": round(baseline_elapsed, 2),
                "error": baseline_err[:100] if baseline_err else None,
            }
            skill_result["baseline"]["runs"].append(run_result)

            if baseline_success:
                print(f"OK ({baseline_cases} cases, diversity={baseline_diversity:.3f}, {baseline_elapsed:.1f}s)")
                agg["baseline"]["success"] += 1
                agg["baseline"]["diversities"].append(baseline_diversity)
                agg["baseline"]["all_cases"] += baseline_cases
            else:
                print(f"FAIL ({baseline_err[:60] if baseline_err else 'no cases'})")
            agg["baseline"]["total"] += 1

            # ── SSoT ─────────────────────────────────────────────────
            print(f"    [SSoT]     generating {cases_per_run} cases...", end=" ", flush=True)
            t0 = time.time()
            try:
                ssot_examples, ssot_err = asyncio.run(generate_with_ssot(
                    skill_text, "skill", cases_per_run, model, api_base, api_key
                ))
            except Exception as e:
                ssot_examples, ssot_err = [], str(e)
            ssot_elapsed = time.time() - t0

            ssot_success = ssot_err is None and len(ssot_examples) > 0
            ssot_diversity = compute_diversity([e.task_input for e in ssot_examples])
            ssot_cases = len(ssot_examples)

            run_result = {
                "run": run_i + 1,
                "success": ssot_success,
                "cases_generated": ssot_cases,
                "diversity": ssot_diversity,
                "elapsed_seconds": round(ssot_elapsed, 2),
                "error": ssot_err[:100] if ssot_err else None,
            }
            skill_result["ssot"]["runs"].append(run_result)

            if ssot_success:
                print(f"OK ({ssot_cases} cases, diversity={ssot_diversity:.3f}, {ssot_elapsed:.1f}s)")
                agg["ssot"]["success"] += 1
                agg["ssot"]["diversities"].append(ssot_diversity)
                agg["ssot"]["all_cases"] += ssot_cases
            else:
                print(f"FAIL ({ssot_err[:60] if ssot_err else 'no cases'})")
            agg["ssot"]["total"] += 1

        # Per-skill summary
        b_runs = skill_result["baseline"]["runs"]
        s_runs = skill_result["ssot"]["runs"]
        skill_result["baseline"]["parse_success_rate"] = round(
            sum(1 for r in b_runs if r["success"]) / len(b_runs), 3
        )
        skill_result["baseline"]["mean_diversity"] = round(
            sum(r["diversity"] for r in b_runs if r["success"]) / max(1, sum(1 for r in b_runs if r["success"])), 4
        )
        skill_result["ssot"]["parse_success_rate"] = round(
            sum(1 for r in s_runs if r["success"]) / len(s_runs), 3
        )
        skill_result["ssot"]["mean_diversity"] = round(
            sum(r["diversity"] for r in s_runs if r["success"]) / max(1, sum(1 for r in s_runs if r["success"])), 4
        )

        print(f"\n  {skill_name} Summary:")
        print(f"    Baseline: parse={skill_result['baseline']['parse_success_rate']:.0%}, "
              f"diversity={skill_result['baseline']['mean_diversity']:.3f}")
        print(f"    SSoT:     parse={skill_result['ssot']['parse_success_rate']:.0%}, "
              f"diversity={skill_result['ssot']['mean_diversity']:.3f}")

        results["per_skill"].append(skill_result)

    # Aggregate summary
    for approach in ["baseline", "ssot"]:
        total = agg[approach]["total"]
        success = agg[approach]["success"]
        diversities = agg[approach]["diversities"]
        all_cases = agg[approach]["all_cases"]

        results["aggregate"][approach] = {
            "parse_success_rate": round(success / total, 4) if total > 0 else 0.0,
            "mean_diversity": round(float(np.mean(diversities)), 4) if diversities else 0.0,
            "std_diversity": round(float(np.std(diversities)), 4) if diversities else 0.0,
            "total_runs": total,
            "total_cases_generated": all_cases,
            "cases_per_successful_run": round(all_cases / success, 2) if success > 0 else 0.0,
        }

    # Comparison delta
    b = results["aggregate"]["baseline"]
    s = results["aggregate"]["ssot"]
    results["aggregate"]["comparison"] = {
        "diversity_delta": round(s["mean_diversity"] - b["mean_diversity"], 4),
        "diversity_delta_pct": round((s["mean_diversity"] - b["mean_diversity"]) / max(b["mean_diversity"], 0.001) * 100, 2),
        "parse_rate_delta": round(s["parse_success_rate"] - b["parse_success_rate"], 4),
    }

    return results


def print_summary(results: dict):
    """Print a human-readable summary of results."""
    print("\n" + "=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)

    cfg = results["config"]
    print(f"\nConfig: {cfg['skills_count']} skills × {cfg['runs_per_skill']} runs × {cfg['cases_per_run']} cases | model={cfg['model']}")

    b = results["aggregate"]["baseline"]
    s = results["aggregate"]["ssot"]
    cmp = results["aggregate"]["comparison"]

    print(f"\n{'Metric':<30} {'Baseline':>12} {'SSoT':>12} {'Delta':>12}")
    print("-" * 70)
    print(f"{'Parse success rate':<30} {b['parse_success_rate']:>11.1%} {s['parse_success_rate']:>11.1%} {cmp['parse_rate_delta']:>+11.1%}")
    print(f"{'Mean semantic diversity':<30} {b['mean_diversity']:>12.4f} {s['mean_diversity']:>12.4f} {cmp['diversity_delta']:>+12.4f}")
    print(f"{'StdDev diversity':<30} {b['std_diversity']:>12.4f} {s['std_diversity']:>12.4f} {'—':>12}")
    print(f"{'Total runs':<30} {b['total_runs']:>12} {s['total_runs']:>12} {'—':>12}")
    print(f"{'Total cases generated':<30} {b['total_cases_generated']:>12} {s['total_cases_generated']:>12} {'—':>12}")
    print(f"{'Cases/successful run':<30} {b['cases_per_successful_run']:>12.2f} {s['cases_per_successful_run']:>12.2f} {'—':>12}")

    print("\nPer-skill breakdown:")
    for sr in results["per_skill"]:
        b_s = sr["baseline"]
        s_s = sr["ssot"]
        delta = s_s["mean_diversity"] - b_s["mean_diversity"]
        print(f"  {sr['skill']:<45} B:par={b_s['parse_success_rate']:.0%} div={b_s['mean_diversity']:.3f}  "
              f"S:par={s_s['parse_success_rate']:.0%} div={s_s['mean_diversity']:.3f}  Δdiv={delta:+.3f}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Benchmark SSoT vs baseline synthetic dataset generation")
    parser.add_argument("--skills-dir", type=Path, default=Path("~/.hermes/skills").expanduser())
    parser.add_argument("--runs", type=int, default=3, help="Runs per skill per approach")
    parser.add_argument("--cases", type=int, default=5, help="Cases to generate per run")
    parser.add_argument("--model", type=str, default="minimax/minimax-m2.7")
    parser.add_argument("--api-base", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.json"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    print(f"Loading skills from {args.skills_dir}...")
    skills = load_skills(args.skills_dir, count=5)
    if len(skills) < 3:
        print(f"ERROR: Need at least 3 skills, found {len(skills)}. Check --skills-dir")
        return

    print(f"Loaded {len(skills)} skills. Starting benchmark...")

    results = run_benchmark(
        skills=skills,
        runs_per_skill=args.runs,
        cases_per_run=args.cases,
        model=args.model,
        api_base=args.api_base,
        api_key=args.api_key,
    )

    # Save results
    output_path = args.output
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {output_path}")

    if not args.quiet:
        print_summary(results)


if __name__ == "__main__":
    main()
