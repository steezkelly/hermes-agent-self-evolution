"""Run companion-roundtable with 20 iterations, single attempt.
Captures evolved_skill.md if produced, or diagnoses why not.
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "companion-roundtable"
ITERATIONS = 20
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"

print(f"{'=' * 60}")
print(f"  Deep Evolution Run — {SKILL}")
print(f"  Iterations: {ITERATIONS}")
print(f"  Optimizer: {OPTIMIZER_MODEL}")
print(f"  Eval: {EVAL_MODEL}")
print(f"{'=' * 60}")
print()

start = time.time()
try:
    report: EvolutionReport = v2_dispatch(
        skill_name=SKILL,
        iterations=ITERATIONS,
        eval_source="synthetic",
        optimizer_model=OPTIMIZER_MODEL,
        eval_model=EVAL_MODEL,
        run_tests=False,
        dry_run=False,
    )
    elapsed = time.time() - start
    print(f"\n  {'=' * 50}")
    print(f"  COMPLETE — {elapsed:.0f}s elapsed")
    print(f"  Improvement: {report.improvement:+.4f}")
    print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
    print(f"  Recommendation: {report.recommendation}")
    print(f"  {'=' * 50}")

    # Show per-attempt metrics
    print(f"\n  Per-attempt details:")
    for attempt in report.attempt_metrics:
        print(f"    Attempt {attempt['attempt']}: "
              f"baseline={attempt['avg_baseline']:.4f}, "
              f"evolved={attempt['avg_evolved']:.4f}, "
              f"delta={attempt['improvement']:+.4f}")

    # Check if evolved_skill.md was saved
    output_dirs = list(Path("output") / SKILL / "v2_*")
    print(f"\n  Output dirs: {len(output_dirs)} found")

except Exception as e:
    elapsed = time.time() - start
    print(f"\n  ERROR after {elapsed:.0f}s: {e}")
    import traceback
    traceback.print_exc()
