#!/usr/bin/env python3
"""Batch regenerate evaluation datasets for all skills in the GEPA registry.

Usage:
    cd ~/hermes0/hermes-agent-self-evolution
    source .venv/bin/activate
    python scripts/regenerate_all_datasets.py [eval_model]

Generates fresh synthetic holdout/train/val for every skill listed in
card-registry.json from the currently deployed SKILL.md content.

Model defaults to the EvolutionConfig judge_model (minimax/minimax-m2.7).
Override with first positional arg, e.g. "minimax/minimax-m2.7".
"""
import json
import os
import sys
import time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.core.dataset_builder import SyntheticDatasetBuilder
from evolution.core.config import EvolutionConfig
from evolution.skills.skill_module import load_skill
from evolution.core.nous_auth import _get_lm_kwargs
import dspy


SKILL_DIR = Path.home() / ".hermes" / "skills"
REGISTRY_PATH = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "gepa_kanban" / "card-registry.json"
DATASET_DIR = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "datasets" / "skills"
OUTPUT_JSONL = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "datasets" / "regeneration_report.jsonl"

EVAL_MODEL = sys.argv[1] if len(sys.argv) > 1 else "minimax/minimax-m2.7"


def find_skill_md(skill_name: str) -> Path | None:
    """Find deployed SKILL.md with exact name matching."""
    for category_dir in SKILL_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        # Exact directory name
        exact = category_dir / skill_name / "SKILL.md"
        if exact.exists():
            return exact
        # Archive/variant prefixes
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
                fm = text.split("\n---\n", 2)[0] if "\n---\n" in text else ""
                for line in fm.splitlines():
                    if line.strip().startswith("name:"):
                        declared = line.split(":", 1)[1].strip().strip('"').strip("'")
                        if declared == skill_name:
                            return md
    return None


def regenerate(skill_name: str, eval_model: str) -> dict:
    """Generate fresh dataset from current deployed skill."""
    md_path = find_skill_md(skill_name)
    if not md_path:
        return {
            "skill": skill_name,
            "status": "MISSING_SKILL",
            "error": f"SKILL.md not found for {skill_name}",
        }

    raw = md_path.read_text()
    config = EvolutionConfig(
        iterations=1,
        optimizer_model=eval_model,
        eval_model=eval_model,
        judge_model=eval_model,
        run_pytest=False,
    )

    # Setup LM
    lm_kwargs, model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 3
    lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=lm)

    builder = SyntheticDatasetBuilder(config)

    t0 = time.time()
    try:
        ds = builder.generate(artifact_text=raw, artifact_type="skill")
    except Exception as e:
        return {
            "skill": skill_name,
            "status": "GENERATION_FAILED",
            "error": str(e),
        }
    gen_time = time.time() - t0

    # Save
    out_dir = DATASET_DIR / skill_name
    out_dir.mkdir(parents=True, exist_ok=True)
    ds.save(out_dir)

    return {
        "skill": skill_name,
        "status": "OK",
        "dataset_dir": str(out_dir),
        "train": len(ds.train),
        "val": len(ds.val),
        "holdout": len(ds.holdout),
        "gen_time_s": round(gen_time, 1),
        "source_skill": str(md_path),
        "skill_size": len(raw),
    }


def main():
    registry = json.loads(REGISTRY_PATH.read_text())
    print(f"Regenerating datasets for {len(registry)} skills")
    print(f"Model: {EVAL_MODEL}")
    print(f"Output: {DATASET_DIR}")
    print("=" * 60)

    results = []
    stats = Counter()

    for i, card in enumerate(registry):
        name = card["skill_name"]
        print(f"\n[{i+1}/{len(registry)}] {name} ... ", end="", flush=True)

        result = regenerate(name, EVAL_MODEL)
        results.append(result)
        stats[result["status"]] += 1

        if result["status"] == "OK":
            print(f"OK  train={result['train']} val={result['val']} holdout={result['holdout']} ({result['gen_time_s']}s)")
        else:
            print(f"FAIL: {result['error'][:80]}")

        # Write incremental report
        with open(OUTPUT_JSONL, "a") as f:
            f.write(json.dumps(result) + "\n")

    print("\n" + "=" * 60)
    print("SUMMARY")
    for status, count in stats.most_common():
        print(f"  {status}: {count}")

    # Also write full report
    report_path = OUTPUT_JSONL.with_suffix(".json")
    report_path.write_text(json.dumps(results, indent=2))
    print(f"\nReports written:")
    print(f"  {OUTPUT_JSONL}")
    print(f"  {report_path}")


if __name__ == "__main__":
    main()
