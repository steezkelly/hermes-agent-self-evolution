"""Validate GEPA v2.1 against companion-interview-workflow with golden dataset.
Same skill as v1's +0.0177 improvement — but using golden (real) data.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

SKILL = "companion-interview-workflow"
ITERATIONS = 5
OPTIMIZER_MODEL = "minimax/minimax-m2.7"
EVAL_MODEL = "minimax/minimax-m2.7"
DS_PATH = "datasets/skills/companion-interview-workflow/"

print("=" * 60)
print("  GEPA v2.1 Validation — Companion Interview Workflow (golden)")
print(f"  Skill: {SKILL} (v1 improvement: +0.0177)")
print(f"  Dataset: {DS_PATH}")
print(f"  Iterations: {ITERATIONS}")
print(f"  Optimizer: {OPTIMIZER_MODEL}")
print(f"  Eval: {EVAL_MODEL}")
print("=" * 60)
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
print(f"  {'=' * 60}")
print(f"  COMPLETE — {elapsed:.0f}s elapsed")
print(f"  Skill: {report.skill_name}")
print(f"  Recommendation: {report.recommendation}")
print(f"  Improvement: {report.improvement:+.4f}")
print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
print(f"  Details: {report.details}")
print(f"  {'=' * 60}")
print()
if report.recommendation == "deploy":
    print("  PASS: v2 accepted (improvement > 0.03)")
elif report.recommendation == "review":
    print("  PARTIAL: v2 assigned review (improvement positive but < 3%)")
elif report.recommendation == "reject":
    if report.improvement <= 0:
        print("  GEPA produced no improvement — not v2 constraint over-rejection")
    else:
        print("  v2 may have over-rejected — positive improvement was blocked")
