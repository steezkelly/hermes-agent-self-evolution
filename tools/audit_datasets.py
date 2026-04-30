#!/usr/bin/env python3
"""
Comprehensive dataset audit for GEPA skills.
Analyzes all 15 datasets in datasets/skills/ for:
- Counts per split (train/val/holdout)
- Difficulty distribution (easy/medium/hard)
- Category coverage (unique categories per skill)
- Example length stats (task_input, expected_behavior)
- Stub detection ("review the conversation", "nothing to save", etc.)
- Duplicate detection (near-identical task_inputs)
- Score interpretation context from evolution_stats.csv
"""
import json
import os
import sys
import csv
from pathlib import Path
from collections import Counter, defaultdict

BASE = Path("~/hermes0/hermes-agent-self-evolution").expanduser()
DATASETS = BASE / "datasets" / "skills"
STATS = BASE / "stats" / "evolution_stats.csv"

STUB_PATTERNS = [
    "review the conversation",
    "nothing to save",
    "nothing to remember",
    "save notable items",
    "no notable items",
    "nothing particularly notable",
]

def load_stats():
    """Load evolution_stats.csv into a dict keyed by skill_name."""
    stats = {}
    if not STATS.exists():
        return stats
    with open(STATS) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["skill_name"]
            if name not in stats:
                stats[name] = []
            stats[name].append(row)
    return stats


def audit_skill(skill_name: str) -> dict:
    """Return a detailed audit dict for one skill."""
    skill_dir = DATASETS / skill_name
    if not skill_dir.is_dir():
        return {"skill": skill_name, "error": "directory not found"}

    result = {
        "skill": skill_name,
        "splits": {},
        "all_examples": [],
        "difficulty_dist": Counter(),
        "categories": Counter(),
        "task_input_lengths": [],
        "expected_lengths": [],
        "stub_count": 0,
        "total_examples": 0,
        "duplicate_task_inputs": 0,
    }

    for split in ["train.jsonl", "val.jsonl", "holdout.jsonl"]:
        path = skill_dir / split
        if not path.exists():
            result["splits"][split] = {"count": 0, "error": "file not found"}
            continue

        examples = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        examples.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        examples.append({"error": str(e)})

        result["splits"][split] = {
            "count": len(examples),
            "file_size_bytes": path.stat().st_size,
        }

        for ex in examples:
            if "error" in ex:
                continue
            result["all_examples"].append(ex)
            result["total_examples"] += 1

            diff = ex.get("difficulty", "unknown").lower()
            result["difficulty_dist"][diff] += 1

            cat = ex.get("category", "uncategorized")
            result["categories"][cat] += 1

            ti = ex.get("task_input", "")
            eb = ex.get("expected_behavior", "")
            result["task_input_lengths"].append(len(ti))
            result["expected_lengths"].append(len(eb))

            # Stub detection
            ti_lower = ti.lower()
            eb_lower = eb.lower()
            if any(p in ti_lower or p in eb_lower for p in STUB_PATTERNS):
                result["stub_count"] += 1

    # Duplicate detection (first 60 chars of task_input)
    seen = set()
    for ex in result["all_examples"]:
        prefix = ex.get("task_input", "")[:60]
        if prefix in seen:
            result["duplicate_task_inputs"] += 1
        seen.add(prefix)

    # Clean up all_examples from result to keep it compact
    result["example_count"] = len(result["all_examples"])
    del result["all_examples"]

    # Convert Counters to dict for JSON serialization
    result["difficulty_dist"] = dict(result["difficulty_dist"])
    result["categories"] = dict(result["categories"])

    # Summary stats
    ti_lens = result["task_input_lengths"]
    eb_lens = result["expected_lengths"]
    result["task_input_avg"] = round(sum(ti_lens) / len(ti_lens), 1) if ti_lens else 0
    result["task_input_med"] = sorted(ti_lens)[len(ti_lens)//2] if ti_lens else 0
    result["expected_avg"] = round(sum(eb_lens) / len(eb_lens), 1) if eb_lens else 0
    result["expected_med"] = sorted(eb_lens)[len(eb_lens)//2] if eb_lens else 0
    result["stub_pct"] = round(result["stub_count"] / max(result["total_examples"], 1) * 100, 1)
    result["dup_pct"] = round(result["duplicate_task_inputs"] / max(result["total_examples"], 1) * 100, 1)

    # Clean up raw lists for JSON
    del result["task_input_lengths"]
    del result["expected_lengths"]

    return result


def audit_all():
    stats = load_stats()
    skills = sorted([d.name for d in DATASETS.iterdir() if d.is_dir() and d.name != ".gitkeep"])

    print(f"GEPA Dataset Audit — {len(skills)} skills\n")
    print(f"{'Skill':35s} {'Train':>6s} {'Val':>4s} {'Hold':>5s} {'Diff':>8s} {'Stub%':>6s} {'Dup%':>6s} {'AvgIn':>6s} {'AvgExp':>7s} {'Cats':>4s} {'Best Imp':>9s}")
    print("-" * 102)

    all_results = []
    for skill in skills:
        audit = audit_skill(skill)
        all_results.append(audit)

        splits = audit["splits"]
        train = splits.get("train.jsonl", {}).get("count", 0)
        val = splits.get("val.jsonl", {}).get("count", 0)
        hold = splits.get("holdout.jsonl", {}).get("count", 0)

        # Difficulty summary
        diff = audit["difficulty_dist"]
        diff_str = f"{diff.get('easy',0)}e/{diff.get('medium',0)}m/{diff.get('hard',0)}h"

        # Best improvement from stats
        best_imp = 0.0
        if skill in stats:
            for row in stats[skill]:
                imp = float(row["improvement"])
                if abs(imp) > abs(best_imp):
                    best_imp = imp

        n_cats = len(audit["categories"])

        print(f"{skill:35s} {train:>6d} {val:>4d} {hold:>5d} {diff_str:>8s} {audit['stub_pct']:>5.1f}% {audit['dup_pct']:>5.1f}% {audit['task_input_avg']:>5.0f} {audit['expected_avg']:>6.0f} {n_cats:>4d} {best_imp:>+8.4f}")

    # Summary statistics
    print(f"\n{'='*102}")
    print(f"SUMMARY")
    print(f"{'='*102}")

    insufficient = [r for r in all_results if r["splits"].get("train.jsonl", {}).get("count", 0) < 8]
    print(f"\nSkills with <8 train examples (insufficient for GEPA):")
    for r in insufficient:
        t = r["splits"].get("train.jsonl", {}).get("count", 0)
        v = r["splits"].get("val.jsonl", {}).get("count", 0)
        h = r["splits"].get("holdout.jsonl", {}).get("count", 0)
        if t < 8:  # only those actually below threshold
            print(f"  - {r['skill']}: {t}/{v}/{h}")

    no_val = [r for r in all_results if r["splits"].get("val.jsonl", {}).get("count", 0) < 2]
    no_hold = [r for r in all_results if r["splits"].get("holdout.jsonl", {}).get("count", 0) < 1]

    if no_val:
        print(f"\nSkills with <2 val examples:")
        for r in no_val:
            v = r["splits"].get("val.jsonl", {}).get("count", 0)
            print(f"  - {r['skill']}: val={v}")

    if no_hold:
        print(f"\nSkills with <1 holdout example:")
        for r in no_hold:
            h = r["splits"].get("holdout.jsonl", {}).get("count", 0)
            print(f"  - {r['skill']}: holdout={h}")

    # Detect one-category-only skills (no category diversity)
    one_cat = [r for r in all_results if len(r["categories"]) <= 1 and r["total_examples"] > 0]
    if one_cat:
        print(f"\nSkills with only 1 category (no diversity):")
        for r in one_cat:
            print(f"  - {r['skill']}: cats={list(r['categories'].keys())[:3]}")

    # Stub-heavy skills
    stubs = [r for r in all_results if r["stub_pct"] > 20 and r["total_examples"] > 0]
    if stubs:
        print(f"\nSkills with >20% stub examples:")
        for r in stubs:
            print(f"  - {r['skill']}: {r['stub_pct']}% stubs ({r['stub_count']}/{r['total_examples']})")

    # Duplicate-heavy
    dups = [r for r in all_results if r["dup_pct"] > 20 and r["total_examples"] > 0]
    if dups:
        print(f"\nSkills with >20% near-duplicate task_inputs:")
        for r in dups:
            print(f"  - {r['skill']}: {r['dup_pct']}% dups")

    # Best candidate skills for evolution (high train count, low existing improvement, diverse categories)
    print(f"\n{'='*102}")
    print(f"EVOLUTION PRIORITY MATRIX")
    print(f"{'='*102}")

    scored = []
    for r in all_results:
        if r["total_examples"] == 0:
            continue
        train_count = r["splits"].get("train.jsonl", {}).get("count", 0)
        has_hard = r["difficulty_dist"].get("hard", 0) > 0
        n_cats = len(r["categories"])
        stub_pct = r["stub_pct"]
        dup_pct = r["dup_pct"]

        # Best improvement from stats
        best_imp = 0.0
        if r["skill"] in stats:
            for row in stats[r["skill"]]:
                imp = float(row["improvement"])
                if abs(imp) > abs(best_imp):
                    best_imp = imp

        # Priority score: higher = more urgent to fix
        # Factors: low train count (needs more data), high stubs (needs cleanup),
        # low categories (needs diversity), low improvement (headroom)
        priority = 0.0
        priority += max(0, 10 - train_count) * 2  # train deficit
        priority += stub_pct * 1.5  # stub problem
        priority += dup_pct * 1.5  # duplicate problem
        priority += max(0, 5 - n_cats) * 3  # category diversity deficit
        if best_imp == 0.0 and train_count >= 8:
            priority += 5  # flatline despite enough data = dataset quality issue
        if not has_hard:
            priority += 3  # missing hard examples
        
        scored.append((priority, r["skill"], train_count, n_cats, has_hard, stub_pct, dup_pct, best_imp))

    scored.sort(key=lambda x: -x[0])

    print(f"{'Priority':>9s} {'Skill':30s} {'Train':>5s} {'Cats':>4s} {'Hard?':>6s} {'Stub%':>6s} {'Dup%':>6s} {'BestImp':>8s}")
    print("-" * 85)
    for pri, name, tr, nc, hh, stub, dup, imp in scored:
        if pri > 0:
            imp_str = f"{imp:+7.4f}" if imp != 0 else "  0.0000"
            print(f"{pri:>8.1f} {name:30s} {tr:>5d} {nc:>4d} {'YES' if hh else 'NO':>6s} {stub:>5.1f}% {dup:>5.1f}% {imp_str}")


    # Detailed per-skill breakdown for worst offenders
    print(f"\n{'='*102}")
    print(f"DETAILED ANALYSIS — WORST OFFENDERS (priority > 15)")
    print(f"{'='*102}")

    for pri, name, tr, nc, hh, stub, dup, imp in scored:
        if pri > 15:
            r = next(x for x in all_results if x["skill"] == name)
            print(f"\n--- {name} (priority: {pri:.1f}) ---")
            splits = r["splits"]
            print(f"  Splits: train={splits['train.jsonl']['count']}, val={splits['val.jsonl']['count']}, holdout={splits['holdout.jsonl']['count']}")
            print(f"  Difficulty: {r['difficulty_dist']}")
            print(f"  Categories ({nc}): {list(r['categories'].keys())}")
            print(f"  Avg input: {r['task_input_avg']} chars, Avg expected: {r['expected_avg']} chars")
            print(f"  Stubs: {r['stub_count']}/{r['total_examples']} ({stub}%)")
            print(f"  Dup task prefixes: {r['duplicate_task_inputs']}/{r['total_examples']} ({dup}%)")
            print(f"  Best GEPA improvement: {imp:+.4f}")

    return all_results


if __name__ == "__main__":
    results = audit_all()
    # Write structured JSON
    output_path = Path("tools/audit_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull audit JSON written to {output_path}")
