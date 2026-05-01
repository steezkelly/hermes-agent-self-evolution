#!/usr/bin/env python3
"""
Synthetic Eval Dataset Expander
================================
Expands skill evaluation datasets by generating additional diverse examples
using the existing examples as templates. Requires a working LLM.

Usage:
    # Expand all skills to minimum 20 train examples
    python tools/expand_dataset.py --target-min-train 20

    # Expand specific skills only
    python tools/expand_dataset.py --skills hermes-agent,companion-workflows

    # Dry run — show what would be generated
    python tools/expand_dataset.py --dry-run

    # Generate additional holdout examples for better evaluation
    python tools/expand_dataset.py --target-min-holdout 10 --variant holdout
"""
import argparse
import json
import sys
import random
from pathlib import Path
from collections import defaultdict

BASE = Path.home() / "hermes0" / "hermes-agent-self-evolution"
DATASETS = BASE / "datasets" / "skills"

# Minimum targets per split
DEFAULT_TARGETS = {"train": 15, "val": 5, "holdout": 5}

# Skill priorities (from audit_datasets.py)
SKILL_PRIORITIES = {
    "github-code-review": 33.0,         # 1 train, 0 val, 0 holdout — critical
    "mnemosyne-self-evolution-tools": 17.0,  # 3/1/3 — high
}

def audit_dataset(skill_name: str) -> dict:
    """Quick audit to count existing examples per split."""
    skill_dir = DATASETS / skill_name
    if not skill_dir.is_dir():
        return {"error": "not found", "splits": {}}
    splits = {}
    for split_name in ["train", "val", "holdout"]:
        path = skill_dir / f"{split_name}.jsonl"
        if path.exists():
            count = sum(1 for _ in path.open() if _.strip())
            splits[split_name] = count
        else:
            splits[split_name] = 0
    return {"splits": splits}

def identify_gaps(skill_name: str, targets: dict) -> dict:
    """Identify which splits need expansion and by how many examples."""
    audit = audit_dataset(skill_name)
    gaps = {"skill": skill_name}
    for split, target in targets.items():
        current = audit["splits"].get(split, 0)
        needed = max(0, target - current)
        gaps[split] = {"current": current, "target": target, "needed": needed}
    gaps["total_needed"] = sum(g["needed"] for g in gaps.values() if isinstance(g, dict))
    return gaps

def expand_all(targets: dict, dry_run: bool = False, skill_filter: list = None):
    """Identify all gaps and produce a plan."""
    all_gaps = {}
    for skill_dir in sorted(DATASETS.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill = skill_dir.name
        if skill_filter and skill not in skill_filter:
            continue
        gaps = identify_gaps(skill, targets)
        if gaps["total_needed"] > 0:
            all_gaps[skill] = gaps

    # Print report
    print(f"{'Skill':35s} {'Train':>8s} {'Val':>6s} {'Hold':>6s} {'Need':>6s}")
    print("-" * 65)
    total = 0
    for skill in sorted(all_gaps):
        g = all_gaps[skill]
        tr = f"{g['train']['current']}→{g['train']['target']}"
        vl = f"{g['val']['current']}→{g['val']['target']}"
        ho = f"{g['holdout']['current']}→{g['holdout']['target']}"
        prio = SKILL_PRIORITIES.get(skill, "")
        print(f"{skill:35s} {tr:>8s} {vl:>6s} {ho:>6s} {g['total_needed']:>4d}  {'PRIORITY' if prio else ''}")
        total += g["total_needed"]

    print(f"\nTotal examples needed: {total}")
    if dry_run:
        print("\n[DRY RUN] No files modified.")
        return

    # If not dry run, tell them what to do
    print(f"\nTo generate: run evolve_skill.py with --expand-dataset for each skill.")
    print(f"Or use the session enrichment pipeline:")
    print(f"  python tools/session_quality_analyzer.py --days 30 --export /tmp/session_candidates.json")
    print(f"  python tools/session_to_dataset.py --input /tmp/session_candidates.json --skill <SKILL> --append datasets/skills/<SKILL>/train.jsonl")

def main():
    parser = argparse.ArgumentParser(description="Expand skill evaluation datasets")
    parser.add_argument("--target-min-train", type=int, default=DEFAULT_TARGETS["train"],
                        help=f"Minimum train examples (default: {DEFAULT_TARGETS['train']})")
    parser.add_argument("--target-min-val", type=int, default=DEFAULT_TARGETS["val"],
                        help=f"Minimum val examples (default: {DEFAULT_TARGETS['val']})")
    parser.add_argument("--target-min-holdout", type=int, default=DEFAULT_TARGETS["holdout"],
                        help=f"Minimum holdout examples (default: {DEFAULT_TARGETS['holdout']})")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without modifying")
    parser.add_argument("--skills", type=str, help="Comma-separated skill names to target")

    args = parser.parse_args()
    targets = {
        "train": args.target_min_train,
        "val": args.target_min_val,
        "holdout": args.target_min_holdout,
    }
    skill_filter = [s.strip() for s in args.skills.split(",")] if args.skills else None
    expand_all(targets, dry_run=args.dry_run, skill_filter=skill_filter)

if __name__ == "__main__":
    main()
