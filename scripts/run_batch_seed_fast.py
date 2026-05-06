#!/usr/bin/env python3
"""Fast batch seed generation — Phase 3.

3 seeds × 1 iteration × 3 examples = ~8 min total (sequential, no rate-limiting).
"""
import subprocess
import sys
import time
from pathlib import Path

SEEDS = [
    # Companion personas — replace the regressed companion-personas skill
    "Author a detailed Hermes Agent persona: define voice, tone, response style, domain expertise, and behavioral constraints from a role description",
    # Companion orchestration — replace the regressed companion-system-orchestration skill
    "Design a multi-agent companion coordination protocol: define roles, communication patterns, delegation rules, and escalation paths for a team of companion agents",
    # GitHub code review — replace the regressed github-code-review skill
    "Review a GitHub pull request thoroughly: analyze the diff for bugs, security issues, performance problems, and write constructive inline comments via the GitHub API",
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
