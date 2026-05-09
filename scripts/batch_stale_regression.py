"""Batch GEPA evolution for STALE and REGRESSION skills — synthetic source."""
import sys, os, time, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch

SKILLS = [
    ("companion-interview-pipeline", 5),
    ("companion-memory", 5),
    ("companion-safety", 5),
    ("github-code-review", 5),
    ("github-pr-review", 5),
    ("linear-issue-creator", 5),
    ("systematic-debugging", 5),
]

results = []
for skill_name, iters in SKILLS:
    print(f"\n{'='*60}")
    print(f"  GEPA: {skill_name}  |  source=synthetic  |  iters={iters}")
    print(f"{'='*60}")
    start = time.time()
    try:
        report = v2_dispatch(
            skill_name=skill_name,
            iterations=iters,
            eval_source="synthetic",
            optimizer_model="minimax/minimax-m2.7",
            eval_model="minimax/minimax-m2.7",
            run_tests=False,
        )
        elapsed = time.time() - start
        print(f"\n  ✅ DONE — {elapsed:.0f}s  improvement={report.improvement:+.4f}")
        print(f"  recommendation: {report.recommendation}")
        results.append({
            "skill": skill_name,
            "status": "success",
            "elapsed": elapsed,
            "improvement": report.improvement,
            "recommendation": report.recommendation,
        })
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n  ❌ ERROR — {elapsed:.0f}s: {e}")
        results.append({
            "skill": skill_name,
            "status": "error",
            "elapsed": elapsed,
            "error": str(e),
        })

# Save
out_dir = Path(__file__).parent.parent / "output"
out_dir.mkdir(parents=True, exist_ok=True)
out_path = out_dir / f"batch_stale_regression_{time.strftime('%Y%m%d_%H%M%S')}.json"
out_path.write_text(json.dumps(results, indent=2, default=str))
print(f"\n{'='*60}")
print(f"  BATCH COMPLETE — {sum(1 for r in results if r['status']=='success')}/{len(results)} OK")
print(f"  Results: {out_path}")
print(f"{'='*60}")
