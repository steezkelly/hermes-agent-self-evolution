"""Validate GEPA v2.1 against companion-workflows.
v1 got +0.125 — now known to be a false positive (type-changing evolution).
If v2 correctly rejects it, that confirms constraint value.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "companion-workflows"
ITERATIONS = 5
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"

print("=" * 60)
print("  GEPA v2.1 Validation — Companion Workflows")
print(f"  Skill: {SKILL}")
print(f"  v1 \"improvement\": +0.125 (now known false positive)")
print(f"  Iterations: {ITERATIONS}")
print(f"  Optimizer: {OPTIMIZER_MODEL}")
print(f"  Eval: {EVAL_MODEL}")
print("  Hypothesis: v2 should REJECT (PurposePreservation)")
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

if report.improvement == 0.0 and report.recommendation == "reject":
    print("  RESULT: v2 rejected (zero change or negative improvement)")
    print("  Possible: GEPA produced no changes, or v2 constraints blocked")
elif report.recommendation == "reject" and report.improvement <= -0.025:
    print("  RESULT: v2 correctly REJECTED a negative change")
    print("  This matches the v2 findings from yesterday")
elif report.recommendation == "review" and report.improvement > 0:
    print("  PARTIAL: v2 assigned 'review' — not fully blocked")
elif report.recommendation == "deploy":
    print("  CONCERN: v2 ACCEPTED a type-changing evolution")
    print("  This suggests PurposePreservation threshold is too lax")
else:
    print(f"  NEUTRAL: v2 recommendation: {report.recommendation} (improvement: {report.improvement:+.4f})")
