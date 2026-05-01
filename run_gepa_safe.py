#!/usr/bin/env python3
"""Run GEPA with timeout-protected LM and progress logging."""
import sys, time, json, traceback
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import dspy
from evolution.core.nous_auth import _get_lm_kwargs

# Configure LM with timeouts  
lm_kwargs_tuple = _get_lm_kwargs("deepseek/deepseek-v4-pro")
lm_kwargs = lm_kwargs_tuple[0].copy()
model_name = lm_kwargs_tuple[1]
lm_kwargs['model'] = model_name
lm_kwargs['request_timeout'] = 120
lm_kwargs['num_retries'] = 2

lm = dspy.LM(**lm_kwargs)
dspy.configure(lm=lm)
print(f"[INIT] LM: {lm.model} (timeout=120s, retries=2)", flush=True)

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

skill = 'companion-roundtable'
print(f'[START] GEPA on {skill} (20 iterations)...', flush=True)
start = time.time()

try:
    report: EvolutionReport = v2_dispatch(
        skill_name=skill,
        iterations=20,
        eval_source='synthetic',
        optimizer_model='deepseek/deepseek-v4-pro',
        eval_model='deepseek/deepseek-v4-pro',
        run_tests=False,
        dry_run=False,
    )
    elapsed = time.time() - start
    print(f'\n[DONE] Complete in {elapsed:.0f}s', flush=True)
    print(f'[RESULT] Improvement: {report.improvement:+.4f}', flush=True)
    print(f'[RESULT] Baseline: {report.baseline_score:.4f}  Final: {report.final_score:.4f}', flush=True)
    print(f'[RESULT] Recommendation: {report.recommendation}', flush=True)
    result = {
        "success": True, "skill": skill, "elapsed": elapsed,
        "improvement": report.improvement,
        "baseline": report.baseline_score, "final": report.final_score,
        "recommendation": report.recommendation,
    }
    print(f'[JSON] {json.dumps(result)}', flush=True)
except Exception as e:
    elapsed = time.time() - start
    print(f'\n[ERROR] Failed after {elapsed:.0f}s: {e}', flush=True)
    traceback.print_exc()
    print(f'[JSON] {json.dumps({"success": False, "skill": skill, "elapsed": elapsed, "error": str(e)})}', flush=True)
    sys.exit(1)
