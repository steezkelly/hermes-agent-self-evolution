#!/usr/bin/env python3
"""GEPA v2.1 evolution run for github-code-review with verbose logging."""
import sys
print("=== Starting evolution run ===", flush=True)

import time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
print("Path setup done", flush=True)

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport
print("Imports done", flush=True)

print("Calling v2_dispatch...", flush=True)
start = time.time()
report = v2_dispatch(
    skill_name="github-code-review",
    iterations=10,
    eval_source="synthetic",
    optimizer_model="minimax.minimax-m2.7",
    eval_model="minimax.minimax-m2.7",
    run_tests=False,
    dry_run=False,
)
elapsed = time.time() - start

print(f"\n{'='*50}", flush=True)
print(f"  Elapsed: {elapsed:.0f}s", flush=True)
print(f"  Improvement: {report.improvement:+.4f}", flush=True)
print(f"  Recommendation: {report.recommendation}", flush=True)
print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})", flush=True)
print(f"  Details: {report.details}", flush=True)
print(f"{'='*50}", flush=True)
