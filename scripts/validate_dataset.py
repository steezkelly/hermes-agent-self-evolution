#!/usr/bin/env python3
"""Quick dataset validation for mnemosyne-self-evolution-tools."""
import json
from pathlib import Path

dataset_dir = Path(__file__).parent / "evolution" / "datasets" / "skills" / "mnemosyne-self-evolution-tools"

total_examples = 0
split_stats = {}

for split in ["train", "val", "holdout"]:
    fpath = dataset_dir / f"{split}.jsonl"
    examples = []
    with open(fpath) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                d = json.loads(line)
                examples.append(d)
    n = len(examples)
    total_examples += n
    total_chars = sum(len(json.dumps(e)) for e in examples)
    avg_len = total_chars / max(1, n)
    
    diff_counts = {}
    cat_counts = {}
    for e in examples:
        diff_counts[e.get("difficulty", "unknown")] = diff_counts.get(e.get("difficulty", "unknown"), 0) + 1
        cat_counts[e.get("category", "unknown")] = cat_counts.get(e.get("category", "unknown"), 0) + 1
    
    split_stats[split] = {
        "count": n,
        "avg_len": avg_len,
        "total_bytes": fpath.stat().st_size,
        "difficulty": diff_counts,
        "categories": cat_counts,
    }

print("=" * 60)
print("DATASET STATS: mnemosyne-self-evolution-tools")
print("=" * 60)
for split, stats in split_stats.items():
    print(f"\n{split.upper()} ({stats['count']} examples, {stats['total_bytes']} bytes on disk):")
    print(f"  Avg JSON length: {stats['avg_len']:.0f} chars")
    print(f"  Difficulty: {stats['difficulty']}")
    print(f"  Categories: {list(stats['categories'].keys())}")

print(f"\nTOTAL: {total_examples} examples across 3 splits")
print(f"Total disk: {sum(s['total_bytes'] for s in split_stats.values())} bytes")
print()

all_valid = True
for split in ["train", "val", "holdout"]:
    fpath = dataset_dir / f"{split}.jsonl"
    with open(fpath) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"INVALID JSON in {split}.jsonl line {i+1}: {e}")
                    all_valid = False
if all_valid:
    print("All JSONL files are valid.")
