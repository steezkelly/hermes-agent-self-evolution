#!/usr/bin/env python3
"""Score old vs new skill using pre-existing dataset.
Uses existing holdout examples from old skill's dataset to score BOTH skills.
This gives a fair comparison: same eval questions, different skill quality.

Usage: python score_compare.py <old_skill_path> <new_skill_path> <dataset_dir> [eval_model]
"""
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.nous_auth import _get_lm_kwargs
from evolution.core.fitness import skill_fitness_metric
from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.skills.evolve_skill import mcs_split
import dspy


def load_dataset(dataset_dir: Path):
    """Load holdout examples from pre-built dataset."""
    holdout_path = dataset_dir / "holdout.jsonl"
    examples = []
    for line in holdout_path.read_text().strip().split('\n'):
        if line:
            ex = json.loads(line)
            # Convert to dspy.Example-like object
            class Ex:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)
                def __repr__(self):
                    return f"Ex({', '.join(f'{k}={v!r:.30}' for k,v in self.__dict__.items())})"
            examples.append(Ex(
                task_input=ex.get('task_input', ex.get('input', ex.get('question', ''))),
                expected_output=ex.get('expected_output', ex.get('output', ex.get('answer', ''))),
                rubric=ex.get('rubric', 'Rate the response on correctness, procedure following, and conciseness.'),
            ))
    return examples


def score_module(module, examples, lm):
    """Score a skill module on holdout examples."""
    scores = []
    for ex in examples:
        with dspy.context(lm=lm):
            pred = module(task_input=ex.task_input)
            s = skill_fitness_metric(ex, pred)
            scores.append(s)
    return scores


def load_skill_body(skill_path: Path) -> str:
    """Extract body from SKILL.md (strip frontmatter)."""
    content = skill_path.read_text()
    if content.startswith('---'):
        parts = content.split('\n---\n', 2)
        return parts[2] if len(parts) > 2 else parts[0]
    return content


def score_skill_on_dataset(skill_path: Path, dataset_dir: Path, eval_model: str) -> dict:
    """Load skill, score on dataset holdout."""
    lm_kwargs, eval_model_used = _get_lm_kwargs(eval_model)
    lm_kwargs["num_retries"] = 2
    lm = dspy.LM(eval_model_used, **lm_kwargs)
    dspy.configure(lm=lm)
    
    body = load_skill_body(skill_path)
    sections = mcs_split(body)
    module = MultiComponentSkillModule(body)
    
    examples = load_dataset(dataset_dir)
    print(f"  Loaded {len(examples)} holdout examples")
    
    start = time.time()
    scores = score_module(module, examples, lm)
    elapsed = time.time() - start
    
    avg = sum(scores) / max(1, len(scores))
    return {"avg": avg, "scores": scores, "n": len(scores), "elapsed": elapsed}


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        print("\nExamples:")
        print("  python score_compare.py \\")
        print("    ~/.hermes/skills/companion-system/companion-personas-STALE-20260501/SKILL.md \\")
        print("    ~/.hermes/skills/companion-system/hermes-agent-author/SKILL.md \\")
        print("    ~/hermes0/hermes-agent-self-evolution/datasets/skills/companion-personas \\")
        sys.exit(1)
    
    old_path = Path(sys.argv[1]).expanduser()
    new_path = Path(sys.argv[2]).expanduser()
    dataset_dir = Path(sys.argv[3]).expanduser()
    eval_model = sys.argv[4] if len(sys.argv) > 4 else "deepseek/deepseek-v4-flash"
    
    print(f"Old: {old_path}")
    print(f"New: {new_path}")
    print(f"Dataset: {dataset_dir}")
    print(f"Eval model: {eval_model}")
    print()
    
    print("Scoring OLD skill...")
    try:
        old_result = score_skill_on_dataset(old_path, dataset_dir, eval_model)
        print(f"  OLD avg: {old_result['avg']:.4f} ({old_result['n']} examples, {old_result['elapsed']:.1f}s)")
    except Exception as e:
        print(f"  OLD ERROR: {e}")
        old_result = None
    
    print("Scoring NEW skill...")
    try:
        new_result = score_skill_on_dataset(new_path, dataset_dir, eval_model)
        print(f"  NEW avg: {new_result['avg']:.4f} ({new_result['n']} examples, {new_result['elapsed']:.1f}s)")
    except Exception as e:
        print(f"  NEW ERROR: {e}")
        new_result = None
    
    print()
    if old_result and new_result:
        delta = new_result['avg'] - old_result['avg']
        pct = (delta / old_result['avg']) * 100 if old_result['avg'] > 0 else 0
        print(f"=== COMPARISON ===")
        print(f"  Old:  {old_result['avg']:.4f}")
        print(f"  New:  {new_result['avg']:.4f}")
        print(f"  Delta: {delta:+.4f} ({pct:+.1f}%)")
        if delta > 0:
            print(f"  ✓ NEW beats OLD")
        elif delta < -0.05:
            print(f"  ✗ NEW is worse (regression)")
        else:
            print(f"  ≈ Comparable (within noise)")
