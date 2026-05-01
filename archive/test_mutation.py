import sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from evolution.core.gepa_v2_dispatch import v2_dispatch

print('Testing module mutation...', flush=True)
report = v2_dispatch(
    skill_name='companion-roundtable',
    iterations=1,
    eval_source='synthetic',
    optimizer_model='minimax/minimax-m2.7',
    eval_model='minimax/minimax-m2.7',
    run_tests=False,
    dry_run=False,
)
print(f'\nBaseline: {report.baseline_score:.4f}')
print(f'Final:    {report.final_score:.4f}')
print(f'Improve:  {report.improvement:+.4f}')
print(f'Rec:      {report.recommendation}')
