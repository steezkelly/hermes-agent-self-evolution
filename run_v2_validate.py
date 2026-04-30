"""Validate GEPA v2.1 against a known-positive v1 improvement.
Runs companion-interview-workflow (+0.0177 v1 best) through v2 pipeline
to check that v2 constraints don't over-reject real improvements.
"""
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "companion-interview-workflow"
ITERATIONS = 5   # v2 has backtrack loops; 5 is enough to validate
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"

print("=" * 60)
print("  GEPA v2.1 Validation Run")
print(f"  Skill: {SKILL} (v1 improvement: +0.0177)")
print(f"  Iterations: {ITERATIONS}")
print(f"  Optimizer: {OPTIMIZER_MODEL}")
print(f"  Eval: {EVAL_MODEL}")
print("=" * 60)
print()

start = time.time()
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

print()
print(f"  {'=' * 60}")
print(f"  COMPLETE — {elapsed:.0f}s elapsed")
print(f"  Skill: {report.skill_name}")
print(f"  Recommendation: {report.recommendation}")
print(f"  Improvement: {report.improvement:+.4f}")
print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
print(f"  Router confidence: {report.router_decision.confidence:.1%}")
print(f"  Details: {report.details}")
print(f"  {'=' * 60}")

# Interpretation
print()
print("  INTERPRETATION:")
v1_improvement = 0.0177
if report.recommendation == "deploy":
    print(f"  PASS: v2 accepted and recommends deploy (improvement > 0.03)")
elif report.recommendation == "review":
    print(f"  PARTIAL: v2 assigned 'review' (improvement positive but below 0.03 threshold)")
    print(f"  Check details for which constraint(s) triggered warnings")
elif report.recommendation == "reject":
    if report.improvement < 0:
        print(f"  GEPA generated a worse solution — rejection is correct behavior")
        print(f"  (GEPA stochastically produced a worse variant this run,")
        print(f"   not a v2 constraint override)")
    elif report.improvement > v1_improvement * 0.5:
        print(f"  CONCERN: v2 rejected despite meaningful improvement.")
        print(f"  This suggests over-rejection by constraints.")
    elif report.improvement > 0:
        print(f"  BORDERLINE: improvement positive but small ({report.improvement:+.4f})")
        print(f"  Below noise-floor-adjacent level. Rejection may be reasonable.")
    else:
        print(f"  GEPA produced no improvement this run.")
        print(f"  GEPA is non-deterministic — would need multiple runs to compare")
        print(f"  against v1's +0.0177")
