#!/usr/bin/env python3
"""Score new seed-generated skills by generating their own datasets.
Each skill generates its own synthetic eval dataset, then scores on holdout.
This gives us a proper baseline score for each new skill.

Usage: python score_new_skills.py [eval_model]
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.dataset_builder import SyntheticDatasetBuilder
from evolution.core.config import EvolutionConfig
from evolution.skills.skill_module import load_skill
from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.core.fitness import skill_fitness_metric
from evolution.core.nous_auth import _get_lm_kwargs
import dspy


SKILLS = [
    ("hermes-agent-author", "~/.hermes/skills/companion-system/hermes-agent-author/SKILL.md"),
    ("design-a-multi-agent-companion-coordinat", "~/.hermes/skills/companion-system/design-a-multi-agent-companion-coordinat/SKILL.md"),
    ("github-pr-review", "~/.hermes/skills/github/github-pr-review/SKILL.md"),
]

OLD_BASELINES = {
    "hermes-agent-author": 0.627,  # companion-personas
    "design-a-multi-agent-companion-coordinat": 0.731,  # companion-system-orchestration
    "github-pr-review": 0.650,  # github-code-review
}

EVAL_MODEL = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4-flash"


def score_skill(skill_path: Path, skill_name: str, eval_model: str) -> dict:
    """Generate dataset for skill and score on holdout."""
    # Load skill properly
    skill = load_skill(skill_path)
    raw = skill["raw"]
    
    # Setup LM
    lm_kwargs, model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 2
    lm = dspy.LM(model_used, **lm_kwargs)
    dspy.configure(lm=lm)
    
    # Generate dataset
    config = EvolutionConfig(
        iterations=1,
        eval_model=eval_model,
        judge_model=eval_model,
    )
    builder = SyntheticDatasetBuilder(config)
    
    t0 = time.time()
    ds = builder.generate(artifact_text=raw, artifact_type="skill")
    gen_time = time.time() - t0
    print(f"  Dataset: {len(ds.train)} train / {len(ds.val)} val / {len(ds.holdout)} holdout ({gen_time:.1f}s)")
    
    # Save dataset
    save_dir = Path("datasets/skills") / skill_name
    ds.save(save_dir)
    
    # Build module from body
    body = skill["body"]
    module = MultiComponentSkillModule(body)
    holdout = ds.to_dspy_examples("holdout")
    
    # Score
    t0 = time.time()
    scores = []
    for ex in holdout:
        with dspy.context(lm=lm):
            pred = module(task_input=ex.task_input)
            s = skill_fitness_metric(ex, pred)
            scores.append(s)
    score_time = time.time() - t0
    
    avg = sum(scores) / max(1, len(scores))
    return {
        "skill": skill_name,
        "avg_score": avg,
        "n_holdout": len(scores),
        "scores": scores,
        "gen_time_s": round(gen_time, 1),
        "score_time_s": round(score_time, 1),
        "body_chars": len(body),
        "old_baseline": OLD_BASELINES.get(skill_name),
        "delta": avg - OLD_BASELINES.get(skill_name, 0),
    }


if __name__ == "__main__":
    print(f"Eval model: {EVAL_MODEL}")
    print()
    
    results = []
    for skill_name, skill_path in SKILLS:
        skill_path = Path(skill_path).expanduser()
        print(f"Scoring: {skill_name}")
        try:
            r = score_skill(skill_path, skill_name, EVAL_MODEL)
            results.append(r)
            delta = r["delta"]
            old = r["old_baseline"]
            print(f"  Score: {r['avg_score']:.4f} | Old: {old:.4f} | Delta: {delta:+.4f}")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = "✓" if r["delta"] > 0 else ("~" if abs(r["delta"]) < 0.05 else "✗")
        print(f"  {status} {r['skill']}: new={r['avg_score']:.4f} old={r['old_baseline']:.4f} delta={r['delta']:+.4f}")
    
    # Save
    out_path = Path("output/baseline_scores_20260501.json")
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out_path}")
