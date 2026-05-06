#!/usr/bin/env python3
"""Focused dataset regeneration for 3 stale skills.

Usage:
    cd ~/hermes0/hermes-agent-self-evolution
    .venv/bin/python scripts/regenerate_stale_datasets.py [eval_model]

Targets: companion-personas, companion-system-orchestration, github-code-review
Re-reads current deployed SKILL.md, generates fresh holdout/train/val.
Saves to datasets/skills/<skill>/ with timestamp.
Also reports holdout structure for inspection.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.core.dataset_builder import SyntheticDatasetBuilder
from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs
import dspy

STALE_SKILLS = [
    "companion-personas",
    "companion-system-orchestration",
    "github-code-review",
]

EVAL_MODEL = sys.argv[1] if len(sys.argv) > 1 else "minimax/minimax-m2.7"
SKILL_DIR = Path.home() / ".hermes" / "skills"
DATASET_DIR = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "datasets" / "skills"
TIMESTAMP = time.strftime("%Y%m%d_%H%M%S")


def find_skill_md(skill_name: str) -> Path | None:
    # EXACT match on name: field first, then exact directory name
    for category_dir in SKILL_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        # Exact directory match
        exact = category_dir / skill_name / "SKILL.md"
        if exact.exists():
            return exact
        # STALE archive variants
        for subdir in category_dir.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name == skill_name or subdir.name.startswith(skill_name + "-"):
                md = subdir / "SKILL.md"
                if md.exists():
                    return md
            # Frontmatter EXACT name field
            md = subdir / "SKILL.md"
            if md.exists():
                text = md.read_text()
                # Extract name: line from frontmatter exactly
                fm = text.split("\n---\n", 2)[0] if "\n---\n" in text else ""
                for line in fm.splitlines():
                    if line.strip().startswith("name:"):
                        declared = line.split(":", 1)[1].strip().strip('"').strip("'")
                        if declared == skill_name:
                            return md
    return None


def regenerate(skill_name: str, eval_model: str) -> dict:
    md_path = find_skill_md(skill_name)
    if not md_path:
        return {"skill": skill_name, "status": "MISSING_SKILL", "error": f"SKILL.md not found for {skill_name}"}

    raw = md_path.read_text()
    print(f"\n{'='*60}")
    print(f"Regenerating: {skill_name}")
    print(f"Source: {md_path}")
    print(f"SKILL.md size: {len(raw):,} bytes")
    print(f"Model: {eval_model}")
    print(f"{'='*60}")

    config = EvolutionConfig(
        iterations=1,
        optimizer_model=eval_model,
        eval_model=eval_model,
        judge_model=eval_model,
        run_pytest=False,
    )

    lm_kwargs, model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 2
    lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    builder = SyntheticDatasetBuilder(config)

    t0 = time.time()
    try:
        ds = builder.generate(artifact_text=raw, artifact_type="skill")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "skill": skill_name,
            "status": "GENERATION_FAILED",
            "error": str(e),
        }
    gen_time = time.time() - t0

    # Print preview of generated holdout
    print(f"\nGENERATED: train={len(ds.train)} val={len(ds.val)} holdout={len(ds.holdout)}")
    print("\n--- HOLDOUT PREVIEW ---")
    for i, ex in enumerate(ds.holdout[:3]):
        task_preview = ex.task_input[:120] if ex.task_input else "(empty)"
        exp_preview = ex.expected_behavior[:120] if ex.expected_behavior else "(empty)"
        print(f"\n  [{i}] task_input: {task_preview}...")
        print(f"      expected: {exp_preview}...")
        print(f"      category: {ex.category} | difficulty: {ex.difficulty}")

    # Check content alignment
    aligned = 0
    for ex in ds.holdout:
        task_lower = (ex.task_input or "").lower()
        skill_kw = skill_name.replace("-", " ")
        if skill_kw in task_lower or skill_name.replace("-","") in task_lower:
            aligned += 1
    print(f"\n  Holdout alignment: {aligned}/{len(ds.holdout)} mention skill keywords")

    # Save to timestamped dir + overwrite active dir
    active_dir = DATASET_DIR / skill_name
    backup_dir = DATASET_DIR / f"{skill_name}.bak_{TIMESTAMP}"
    if active_dir.exists():
        import shutil
        shutil.copytree(active_dir, backup_dir)
        print(f"  Backup: {backup_dir}")

    active_dir.mkdir(parents=True, exist_ok=True)
    ds.save(active_dir)

    return {
        "skill": skill_name,
        "status": "OK",
        "dataset_dir": str(active_dir),
        "train": len(ds.train),
        "val": len(ds.val),
        "holdout": len(ds.holdout),
        "gen_time_s": round(gen_time, 1),
        "skill_size": len(raw),
        "holdout_aligned": aligned,
    }


def main():
    print(f"Stale dataset regeneration for {len(STALE_SKILLS)} skills")
    print(f"Model: {EVAL_MODEL}")
    print(f"Output: {DATASET_DIR}")

    results = []
    for name in STALE_SKILLS:
        r = regenerate(name, EVAL_MODEL)
        results.append(r)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        if r["status"] == "OK":
            print(f"  ✓ {r['skill']:36} train={r['train']:2} val={r['val']:2} holdout={r['holdout']:2} align={r.get('holdout_aligned',0)}/{r['holdout']} ({r['gen_time_s']}s)")
        else:
            print(f"  ✗ {r['skill']:36} {r['status']}: {r.get('error','')[:60]}")

    # Save report
    report = DATASET_DIR / "stale_regeneration_report.json"
    report.write_text(json.dumps(results, indent=2))
    print(f"\nReport: {report}")


if __name__ == "__main__":
    main()
