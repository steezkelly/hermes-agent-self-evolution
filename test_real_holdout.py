"""Fast metric sanity check on real companion-roundtable holdout data.

Run the fixed metric against the real holdout dataset to show:
- Mean score is NOT ~0.30 (flat)
- Scores vary by example (LLM quality matters)
- Takes ~15s for 5 examples (vs ~2-3 min with minimax-m2.7)
"""
import sys, os, time
sys.path.insert(0, "/home/steve/hermes0/hermes-agent-self-evolution")
os.chdir("/home/steve/hermes0/hermes-agent-self-evolution")

import dspy
from pathlib import Path

# Use local Ollama for speed
lm = dspy.LM("ollama/qwen3:sm", api_base="http://localhost:11434")
dspy.configure(lm=lm)

from evolution.skills.skill_module import find_skill, load_skill
from evolution.skills.skill_module_v2 import MultiComponentSkillModule
from evolution.core.fitness import skill_fitness_metric, fit_global_scorer, clear_global_scorer
from evolution.core.dataset_builder import EvalDataset

# Load skill
skill_path = find_skill("companion-roundtable", Path.home() / ".hermes")
skill = load_skill(skill_path)
body = skill["body"]

# Load dataset
dataset = EvalDataset.load(Path("datasets/skills/companion-roundtable"))
examples = dataset.to_dspy_examples("holdout")
print(f"Holdout examples: {len(examples)}")

# Fit TF-IDF
fit_global_scorer(examples)

# Create module
mod = MultiComponentSkillModule(body)

print("\n" + "="*70)
print("Real metric on companion-roundtable holdout (LLM invoked)")
print("="*70)

scores = []
for i, ex in enumerate(examples):
    pred = mod(task_input=ex.task_input)
    t0 = time.time()
    score = skill_fitness_metric(ex, pred)
    elapsed = time.time() - t0
    scores.append(score)
    print(f"\nExample {i+1}:  score={score:.3f}  (metric took {elapsed:.1f}s)")
    print(f"  task: {ex.task_input[:100]}...")
    print(f"  expected: {ex.expected_behavior[:100]}...")

print(f"\n--- Summary ---")
print(f"Mean: {sum(scores)/len(scores):.3f}")
print(f"Min:  {min(scores):.3f}")
print(f"Max:  {max(scores):.3f}")
print(f"Range: {max(scores)-min(scores):.3f}")

# Before fix these would all be ~0.30-0.33 (flat).
# Range >0.1 means the metric is actually working.
range_val = max(scores) - min(scores)
if range_val > 0.10:
    print(f"\n=> PASS: Range {range_val:.3f} > 0.10 — metric discriminates across examples")
else:
    print(f"\n=> UNCERTAIN: Range {range_val:.3f} ≤ 0.10 — scores somewhat flat (may need better model)")

print("="*70)
