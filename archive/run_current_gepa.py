import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from evolution.core.gepa_v2_dispatch import v2_dispatch

print('Starting GEPA run...', flush=True)
start = time.time()
report = v2_dispatch(
    skill_name='companion-roundtable',
    iterations=5,
    eval_source='synthetic',
    optimizer_model='minimax/minimax-m2.7',
    eval_model='minimax/minimax-m2.7',
    run_tests=False,
    dry_run=False,
)
elapsed = time.time() - start
print(f'=== COMPLETE {elapsed:.0f}s ===')
print(f'Baseline: {report.baseline_score:.4f}')
print(f'Final:    {report.final_score:.4f}')
print(f'Improve:  {report.improvement:+.4f}')
print(f'Router:   {report.router_decision.action}')
print(f'Reason:   {report.router_decision.failure_pattern}')
print(f'Rec:      {report.recommendation}')
