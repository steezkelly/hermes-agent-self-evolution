#!/usr/bin/env python3
"""Score a skill's baseline performance using synthetic holdout evaluation.
Usage: python score_baseline.py <skill_name_or_path> [skill_dir]

Skill_dir defaults to ~/.hermes/skills/
Outputs: avg holdout score, per-example scores.
"""
import sys, json, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.dataset_builder import SyntheticDatasetBuilder
from evolution.core.fitness import skill_fitness_metric
from evolution.core.config import EvolutionConfig
from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.skills.evolve_skill import mcs_split
import dspy

def load_skill_raw(skill_name_or_path: str, skill_dir: str = None) -> str:
    """Load skill raw content."""
    if skill_dir is None:
        skill_dir = os.path.expanduser("~/.hermes/skills")
    
    p = Path(skill_name_or_path)
    if p.is_file():
        return p.read_text()
    
    # Try as skill name
    for root, dirs, files in os.walk(skill_dir):
        for f in files:
            if f == "SKILL.md":
                skill_path = Path(root) / f
                # Check if parent dir matches or if name matches in frontmatter
                content = skill_path.read_text()
                if skill_name_or_path in content.split('\n---\n', 2)[0] if '\n---\n' in content else skill_name_or_path in content:
                    return content
    raise FileNotFoundError(f"Skill '{skill_name_or_path}' not found in {skill_dir}")


def score_skill(skill_content: str, skill_name: str, eval_model: str = "deepseek/deepseek-v4-flash") -> dict:
    """Generate dataset and score baseline skill on holdout examples."""
    from evolution.core.nous_auth import _get_lm_kwargs
    
    config = EvolutionConfig(
        iterations=1,
        optimizer_model=eval_model,
        eval_model=eval_model,
        judge_model=eval_model,
        run_pytest=False,
    )
    
    # Generate synthetic dataset
    builder = SyntheticDatasetBuilder(config)
    dataset = builder.generate(artifact_text=skill_content, artifact_type="skill")
    
    print(f"  Dataset: {len(dataset.train)} train / {len(dataset.val)} val / {len(dataset.holdout)} holdout")
    
    # Setup DSPy
    lm_kwargs, eval_model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 3
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)
    
    # Parse skill body (strip frontmatter)
    parts = skill_content.split('\n---\n', 2)
    frontmatter = parts[1] if len(parts) > 1 else ""
    body = parts[2] if len(parts) > 2 else parts[0] if parts else skill_content
    
    # Build module and score on holdout
    sections = mcs_split(body)
    baseline_module = MultiComponentSkillModule(body)
    holdout_examples = dataset.to_dspy_examples("holdout")
    
    scores = []
    for ex in holdout_examples:
        with dspy.context(lm=lm):
            pred = baseline_module(task_input=ex.task_input)
            s = skill_fitness_metric(ex, pred)
            scores.append(s)
    
    avg = sum(scores) / max(1, len(scores))
    return {
        "skill": skill_name,
        "avg_score": avg,
        "n_holdout": len(scores),
        "scores": scores,
        "dataset": {
            "train": len(dataset.train),
            "val": len(dataset.val),
            "holdout": len(dataset.holdout),
        }
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    skill_input = sys.argv[1]
    eval_model = sys.argv[2] if len(sys.argv) > 2 else "deepseek/deepseek-v4-flash"
    
    print(f"Scoring: {skill_input}")
    print(f"Eval model: {eval_model}")
    
    try:
        content = load_skill_raw(skill_input)
        # Extract name from frontmatter
        name = skill_input
        if content.startswith('---'):
            fm_end = content.index('\n---\n', 4)
            fm_text = content[3:fm_end]
            for line in fm_text.split('\n'):
                if line.startswith('name:'):
                    name = line.split('name:', 1)[1].strip().strip('"\'')
                    break
        print(f"Name: {name}")
        result = score_skill(content, name, eval_model)
        print(f"\n=== RESULTS ===")
        print(f"Skill: {result['skill']}")
        print(f"Holdout examples: {result['n_holdout']}")
        print(f"Avg score: {result['avg_score']:.4f}")
        print(f"Per-example: {[f'{s:.3f}' for s in result['scores']]}")
        print(f"\nDataset sizes: {result['dataset']}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
