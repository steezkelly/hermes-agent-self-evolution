#!/usr/bin/env python3
"""Batch seed generation — Phase 3 of skill-generation-from-seed plan.

Generates 3 new skills from seeds covering high-value gaps:
  1. personal-osint-audit — Security skill for personal attack surface assessment
  2. exploratory-data-analysis — Data science skill for systematic dataset profiling
  3. research-planning — Cross-domain research orchestration

Each runs with --full-skill, 3 iterations/section, max 3 concurrent.
Total expected: ~15-20 minutes.
"""
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.skills.seed_to_skill import generate_full_skill

SEEDS = [
    {
        "seed": "Audit your own digital footprint and online exposure by searching for your name, email, and username across public databases, social networks, and breach logs",
        "skill_slug": "personal-osint-audit",
        "description": "Personal OSINT audit: assess your own public digital footprint",
    },
    {
        "seed": "Explore and profile a dataset systematically: infer types, detect missing values, compute summary statistics, and generate a written report of findings",
        "skill_slug": "exploratory-data-analysis",
        "description": "Exploratory data analysis for unfamiliar datasets",
    },
    {
        "seed": "Plan and execute a multi-step research task: decompose a question, run parallel web searches, synthesize findings into a coherent written report with citations",
        "skill_slug": "research-planning",
        "description": "Research orchestration: plan, search, synthesize",
    },
]

ITERATIONS = 3
OPTIMIZER_MODEL = "deepseek/deepseek-v4-pro"
EVAL_MODEL = "minimax/minimax-m2.7"

results = []

for i, spec in enumerate(SEEDS):
    seed = spec["seed"]
    slug = spec["skill_slug"]
    print(f"\n{'=' * 60}")
    print(f"  [{i+1}/{len(SEEDS)}] Seed: {slug}")
    print(f"  {seed[:80]}...")
    print(f"{'=' * 60}")

    start = time.time()
    try:
        import subprocess as _subprocess
        import sys as _sys
        proc = _subprocess.run(
            [_sys.executable, "-m", "evolution.skills.seed_to_skill",
             "--seed", seed,
             "--full-skill",
             "--iterations", str(ITERATIONS),
             "--optimizer-model", OPTIMIZER_MODEL,
             "--eval-model", EVAL_MODEL,
             "--n-examples", "5"],
            capture_output=True, text=True, timeout=900,
            cwd=str(Path(__file__).parent),
        )
        print(proc.stdout[-3000:] if len(proc.stdout) > 3000 else proc.stdout)
        if proc.returncode != 0:
            print("STDERR:", proc.stderr[-1000:] if proc.stderr else "")
        skill_paths = sorted(Path("output/seed-generated").glob("full-skill_*/"+slug+".SKILL.md"))
        skill_path = str(skill_paths[-1]) if skill_paths else ""
        content = ""
        if skill_path:
            content = Path(skill_path).read_text()
        elapsed = time.time() - start
        status = "SUCCESS" if skill_path else "FAILED"
        print(f"\n  {'✓' if status == 'SUCCESS' else '✗'} {status} — {skill_path}")
        print(f"    Time: {elapsed:.0f}s | Chars: {len(content):,}")
        results.append({"slug": slug, "status": status, "skill_path": skill_path, "elapsed": elapsed, "chars": len(content)})
        continue

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ✗ FAILED after {elapsed:.0f}s: {e}")
        results.append({"slug": slug, "status": "FAILED", "error": str(e), "elapsed": elapsed})

print(f"\n{'=' * 60}")
print("  BATCH SUMMARY")
print(f"{'=' * 60}")
for r in results:
    icon = "✓" if r["status"] == "SUCCESS" else "⚠" if r["status"] == "DRYRUN" else "✗"
    print(f"  {icon} {r['slug']}: {r['status']} ({r.get('elapsed', 0):.0f}s)")
    if r["status"] == "SUCCESS":
        print(f"      {r['skill_path']} — {r.get('chars', 0):,} chars, coherence={r.get('coherence_passed')}")
