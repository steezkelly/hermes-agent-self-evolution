#!/usr/bin/env python3
"""Smoke test for token cost tracking (v3.1) in fitness.py.

Verifies that estimate_judge_call_cost() is called correctly during
LLMJudge.score() and that the audit_log DB contains non-NULL costs.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_repo_root = Path(__file__).parent.parent.resolve()


def main():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_repo_root)
    env["GEPA_OUTPUT_DIR"] = tempfile.mkdtemp(prefix="cost_smoke_")
    env["_COST_SMOKE_CHILD"] = "1"

    script = _repo_root / "scripts" / "test_cost_tracking.py"
    ret = subprocess.run(
        [sys.executable, str(script), "--child"],
        env=env,
        cwd=str(_repo_root),
    )
    sys.exit(ret.returncode)


def _child_test():
    import sqlite3

    import dspy

    from evolution.core.fitness import LLMJudge
    from evolution.core.config import EvolutionConfig
    from evolution.core.observatory.logger import get_logger
    from evolution.core.observatory.context import set_evaluation_context
    from evolution.core.nous_auth import _get_lm_kwargs

    SKILL_BODY = """\
# Debug Python

Use `pdb.set_trace()` for inline breakpoints.
"""
    task = "How do I set an inline breakpoint in Python?"
    expected = "Use pdb.set_trace() for inline breakpoints."

    logger = get_logger()
    db_path = logger.db_path
    print(f"DB path: {db_path}")

    lm_kwargs, model_used = _get_lm_kwargs("minimax/minimax-m2.7")
    lm_kwargs["num_retries"] = 2
    lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    judge = LLMJudge(EvolutionConfig(judge_model="minimax/minimax-m2.7"))

    print("\n1. Testing with ObsContext (generation=3, skill_name='cost-test')")
    set_evaluation_context(3, "cost-test", task_id="cost-t1")
    score1 = judge.score(task, expected, "use pdb.set_trace()", SKILL_BODY)
    print(f"   Score: correct={score1.correctness:.3f} proc={score1.procedure_following:.3f}")

    print("\n2. Testing without context (should default to gen=0, unknown)")
    set_evaluation_context()
    score2 = judge.score(task, expected, "use breakpoint()", SKILL_BODY)
    print(f"   Score: correct={score2.correctness:.3f} proc={score2.procedure_following:.3f}")

    # Verify DB state
    print("\n3. Verifying DB rows")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT generation, skill_name, model_used, raw_score, latency_ms,
               token_cost_estimate, error_flag
        FROM judge_audit_log ORDER BY timestamp DESC LIMIT 5
    """).fetchall()
    print(f"   Rows in DB: {len(rows)}")
    for r in rows:
        cost = r["token_cost_estimate"]
        cost_str = f"${cost:.6f}" if cost is not None else "NULL"
        print(f"   gen={r['generation']:3d} skill={r['skill_name']:12s} "
              f"model={r['model_used']:30s} score={r['raw_score']:.3f} "
              f"latency={r['latency_ms']} cost={cost_str}")

    non_null = conn.execute(
        "SELECT COUNT(*) FROM judge_audit_log WHERE token_cost_estimate IS NOT NULL"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM judge_audit_log").fetchone()[0]

    print(f"\n4. Result: {non_null}/{total} rows have non-NULL token_cost_estimate")
    if non_null == total and total > 0:
        print("   PASS: All rows have cost estimates.")
        sys.exit(0)
    else:
        print("   FAIL: Some rows missing cost estimates.")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child_test()
    else:
        main()
