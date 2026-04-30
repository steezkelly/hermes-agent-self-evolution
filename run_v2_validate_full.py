"""Full 10-iteration GEPA v2.1 validation against companion-interview-workflow with golden data.
Matches v1 parameters: 10 iterations, golden dataset, minimax-m2.7 for both optimizer and eval.
If v2 constraints over-reject, this is the test that proves it.
If v2 constraints don't over-reject, this run should show improvement >= v1's +0.0177.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "companion-interview-workflow"
ITERATIONS = 10  # Match v1 parameters
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"
DS_PATH = "datasets/skills/companion-interview-workflow/"

print("=" * 70)
print("  GEPA v2.1 Full Validation — 10 iterations, golden data")
print(f"  Skill: {SKILL} (v1 best: +0.0177)")
print(f"  Iterations: {ITERATIONS}")
print(f"  Dataset: {DS_PATH}")
print(f"  Optimizer: {OPTIMIZER_MODEL} | Eval: {EVAL_MODEL}")
print("=" * 70)
print()

start = time.time()
report: EvolutionReport = v2_dispatch(
    skill_name=SKILL,
    iterations=ITERATIONS,
    eval_source="golden",
    dataset_path=DS_PATH,
    optimizer_model=OPTIMIZER_MODEL,
    eval_model=EVAL_MODEL,
    run_tests=False,
    dry_run=False,
)
elapsed = time.time() - start

print()
print(f"  {'=' * 70}")
print(f"  COMPLETE — {elapsed:.0f}s ({elapsed/60:.1f} min)")
print(f"  Skill: {report.skill_name}")
print(f"  Recommendation: {report.recommendation}")
print(f"  Improvement: {report.improvement:+.4f}")
print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
print(f"  Details: {report.details}")
print(f"  {'=' * 70}")
print()

v1_improvement = 0.0177
print("  VERDICT:")
if report.recommendation == "deploy":
    if report.improvement >= v1_improvement * 0.8:
        print(f"  √ PASS: v2 accepted at +{report.improvement:.4f} (≥ 80% of v1's +{v1_improvement})")
        print(f"    v2 constraints did NOT over-reject.")
    else:
        print(f"  ~ PARTIAL: v2 accepted but improvement (+{report.improvement:.4f})")
        print(f"    is below v1's +{v1_improvement}. GEPA stochasticity or constraint interaction.")
elif report.recommendation == "review":
    print(f"  ~ BORDERLINE: v2 assigned 'review' at +{report.improvement:.4f}")
    if report.improvement > 0:
        print("    Constraints flagged it but didn't block. Review-worthy.")
    else:
        print("    GEPA didn't find improvement. Not a constraint issue.")
elif report.recommendation == "reject":
    print(f"  ! REJECTED at +{report.improvement:.4f}")
    if report.improvement > 0.01:
        print(f"    v2 constraints over-rejected a +{report.improvement:.4f} improvement!")
    elif report.improvement > 0:
        print(f"    Improvement (+{report.improvement:.4f}) is positive but below noise floor.")
        print("    Rejection may be reasonable.")
    else:
        print("    GEPA produced no improvement. Not a constraint issue.")
