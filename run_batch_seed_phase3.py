#!/usr/bin/env python3
"""Phase 3 expansion: new skills in unexplored domains.

3 seeds × 1 iteration × 3 examples = ~8 min total (sequential).
No legacy baseline to regress against — pure new capability.
"""
import subprocess
import sys
import time
from pathlib import Path

SEEDS = [
    # Research synthesis — combines web search + arxiv + wiki into structured reports
    "Synthesize a comprehensive research report from web search, arXiv papers, and wiki notes on a given topic, producing an structured summary with key findings, disagreements, and open questions",
    # Linear issue creation — natural language to Linear GraphQL issue creation
    "Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API",
    # Codebase metrics — LOC, language ratios, complexity signals from a repository
    "Analyze a codebase directory and produce a metrics report: line counts per language, file count, estimated complexity hotspots, and summary statistics using pygount",
]

SKILL_DIR = Path.home() / ".hermes" / "skills"

def run_seed(seed: str, idx: int):
    print(f"\n{'='*60}")
    print(f"Seed {idx+1}/{len(SEEDS)}: {seed[:60]}...")
    print('='*60)
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, "-m", "evolution.skills.seed_to_skill",
         "--seed", seed,
         "--full-skill",
         "--iterations", "1",
         "--n-examples", "3",
         "--optimizer-model", "deepseek/deepseek-v4-pro",
         "--eval-model", "deepseek/deepseek-v4-flash",
        ],
        cwd=Path(__file__).parent,
    )
    elapsed = time.time() - t0
    print(f"  → Done in {elapsed:.0f}s (exit {proc.returncode})")
    return proc.returncode == 0

if __name__ == "__main__":
    results = []
    for i, seed in enumerate(SEEDS):
        ok = run_seed(seed, i)
        results.append((seed[:50], ok))
        if i < len(SEEDS) - 1:
            print(f"\n  Sleeping 5s between seeds to avoid rate-limiting...")
            time.sleep(5)

    print(f"\n\n{'='*60}")
    print("BATCH SUMMARY")
    print('='*60)
    for seed, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status}  {seed}")
    print(f"\nTotal: {sum(1 for _, ok in results if ok)}/{len(results)} succeeded")
