"""Run GEPA v2.1 evolution on all 4 re-datased skills."""
import sys
import os
import time
import json
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILLS = [
    "companion-roundtable",
    "companion-personas",
    "mnemosyne-maintenance",
    "companion-memory-tiers",
]

ITERATIONS = 5
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"

results = []

for skill_name in SKILLS:
    print(f"\n{'=' * 60}")
    print(f"  GEPA v2.1 Evolution Run")
    print(f"  Skill: {skill_name}")
    print(f"  Iterations: {ITERATIONS}")
    print(f"  Optimizer: {OPTIMIZER_MODEL}")
    print(f"  Eval: {EVAL_MODEL}")
    print(f"{'=' * 60}")
    print()

    start = time.time()
    try:
        report: EvolutionReport = v2_dispatch(
            skill_name=skill_name,
            iterations=ITERATIONS,
            eval_source="synthetic",
            optimizer_model=OPTIMIZER_MODEL,
            eval_model=EVAL_MODEL,
            run_tests=False,
            dry_run=False,
        )
        elapsed = time.time() - start
        result = {
            "skill": skill_name,
            "elapsed_seconds": elapsed,
            "recommendation": report.recommendation,
            "improvement": report.improvement,
            "router_action": report.router_decision.action,
            "router_failure": report.router_decision.failure_pattern,
            "details": report.details,
            "status": "success",
        }
        print(f"\n  {'=' * 50}")
        print(f"  COMPLETE — {elapsed:.0f}s elapsed")
        print(f"  Improvement: {report.improvement:+.4f}")
        print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
        print(f"  Recommendation: {report.recommendation}")
        print(f"  {'=' * 50}")
    except Exception as e:
        elapsed = time.time() - start
        result = {
            "skill": skill_name,
            "elapsed_seconds": elapsed,
            "status": "error",
            "error": str(e),
        }
        print(f"\n  ERROR after {elapsed:.0f}s: {e}")

    results.append(result)

print(f"\n\n{'=' * 60}")
print(f"  FINAL RESULTS")
print(f"{'=' * 60}")
for r in results:
    s = r["skill"]
    if r["status"] == "success":
        print(f"  {s}: {r['improvement']:+.4f} ({r['router_action']}) — {r['recommendation']} ({r['elapsed_seconds']:.0f}s)")
    else:
        print(f"  {s}: ERROR — {r.get('error', 'unknown')} ({r['elapsed_seconds']:.0f}s)")

# Save results to JSON for inspection
out_path = Path(__file__).parent / "output" / "batch_evolution_results.json"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(results, indent=2, default=str))
print(f"\nResults saved to {out_path}")
