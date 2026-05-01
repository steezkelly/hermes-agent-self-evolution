#!/usr/bin/env python3
"""Run GEPA with proper LM context and progress logging."""
import sys, time, json, traceback
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import dspy
from evolution.core.nous_auth import _get_lm_kwargs

# Configure LM BEFORE any metric calls
lm_kwargs_tuple = _get_lm_kwargs("minimax/minimax-m2.7")
lm_kwargs = lm_kwargs_tuple[0]
model_name = lm_kwargs_tuple[1]
# Add model to kwargs
lm_kwargs = lm_kwargs.copy()
lm_kwargs['model'] = model_name

lm = dspy.LM(**lm_kwargs)
dspy.configure(lm=lm)
print(f"[INIT] Configured LM: {lm.model}", flush=True)

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

skill = 'companion-roundtable'
print(f'[START] Starting mini-GEPA on {skill} (5 iterations)...', flush=True)
start = time.time()

try:
    report: EvolutionReport = v2_dispatch(
        skill_name=skill,
        iterations=5,
        eval_source='synthetic',
        optimizer_model='minimax/minimax-m2.7',
        eval_model='minimax/minimax-m2.7',
        run_tests=False,
        dry_run=False,
    )
    elapsed = time.time() - start
    print(f'\n[DONE] Complete in {elapsed:.0f}s', flush=True)
    print(f'[RESULT] Improvement: {report.improvement:+.4f}', flush=True)
    print(f'[RESULT] Baseline: {report.baseline_score:.4f}  Final: {report.final_score:.4f}', flush=True)
    print(f'[RESULT] Recommendation: {report.recommendation}', flush=True)
    
    # Write result summary to stdout as JSON
    result = {
        "success": True,
        "skill": skill,
        "elapsed": elapsed,
        "improvement": report.improvement,
        "baseline": report.baseline_score,
        "final": report.final_score,
        "recommendation": report.recommendation,
    }
    print(f'[JSON] {json.dumps(result)}', flush=True)
    
except Exception as e:
    elapsed = time.time() - start
    print(f'\n[ERROR] Failed after {elapsed:.0f}s: {e}', flush=True)
    traceback.print_exc()
    result = {
        "success": False,
        "skill": skill,
        "elapsed": elapsed,
        "error": str(e),
    }
    print(f'[JSON] {json.dumps(result)}', flush=True)
    sys.exit(1)
