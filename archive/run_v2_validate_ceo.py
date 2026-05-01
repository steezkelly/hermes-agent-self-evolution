"""Validate GEPA v2.1 against ceo-orchestration — strongest v1 signal (+0.0968).
Synthetic eval should work since GEPA consistently finds changes for this skill.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "ceo-orchestration"
ITERATIONS = 5
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"

print("=" * 60)
print("  GEPA v2.1 Validation — CEO Orchestration")
print(f"  Skill: {SKILL} (v1 improvement: +0.0968)")
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
print(f"  Details: {report.details}")
print(f"  {'=' * 60}")

print()
print("  INTERPRETATION:")
if report.recommendation == "deploy":
    print(f"  PASS: v2 accepted and recommends deploy (improvement > 0.03)")
elif report.recommendation == "review":
    print(f"  PARTIAL: v2 assigned 'review' (improvement > 0 but below 3%)")
elif report.recommendation == "reject":
    print(f"  CHECK: v2 rejected.")
    if report.improvement <= 0:
        print(f"  But GEPA produced no improvement — may not be constraint over-rejection")
    else:
        print(f"  v2 constraint over-rejection is possible here")
