#!/usr/bin/env python3
"""Runs GEPA v2.1 for github-code-review with a marker file for completion."""
import sys, time, json, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
MARKER = Path("/tmp/gepa_review_done.txt")
MARKER.write_text("starting")

from evolution.core.gepa_v2_dispatch import v2_dispatch

print("Starting full GEPA v2.1 run...", flush=True)
start = time.time()
result = v2_dispatch(
    skill_name="github-code-review",
    iterations=10,
    eval_source="synthetic",
    optimizer_model="minimax/minimax-m2.7",
    eval_model="minimax/minimax-m2.7",
    run_tests=False,
    dry_run=False,
)
elapsed = time.time() - start

out = {
    "skill": "github-code-review",
    "elapsed_seconds": round(elapsed, 1),
    "improvement": result.improvement,
    "recommendation": result.recommendation,
    "router_action": result.router_decision.action,
    "router_failure": result.router_decision.failure_pattern,
    "details": result.details,
    "status": "success",
}
out_path = Path("output") / "batch_evolution_results.json"
out_path.write_text(json.dumps(out, indent=2, default=str))

summary = f"""Done in {elapsed:.0f}s
Improvement: {result.improvement:+.4f}
Recommendation: {result.recommendation}
Router: {result.router_decision.action} ({result.router_decision.failure_pattern})
Details: {result.details}
"""
print(summary, flush=True)
MARKER.write_text(summary)
