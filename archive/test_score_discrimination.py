import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import dspy
from evolution.core.nous_auth import _get_lm_kwargs
from evolution.core.fitness import skill_fitness_metric, _invoke_skill_as_agent
from evolution.core.dataset_builder import EvalDataset
from evolution.skills.skill_module_v2 import MultiComponentSkillModule

# === Setup ========================
lm_kwargs, model = _get_lm_kwargs('minimax/minimax-m2.7')
lm = dspy.LM(model, **lm_kwargs)
dspy.configure(lm=lm)

# Load dataset
dataset = EvalDataset.load(Path('datasets/skills/companion-roundtable'))
holdout = dataset.to_dspy_examples('holdout')
ex = holdout[0]

print('=== SCORING 3 DIFFERENT BODIES AGAINST SAME EXAMPLE ===')
print(f'Task: {ex.task_input[:80]}\n')

# 1. Real skill body (21KB from file)
real_body = Path('output/companion-roundtable/v2_20260429_223959/baseline_skill.md').read_text()

# 2. Mutated skill body (manually alter one section)
mutated_body = real_body.replace(
    'Use xiaomi/mimo-v2.5 for delegation',
    'Use gpt-4 for all delegation tasks'
)

# 3. Bad skill body (short)
bad_body = 'You are a helpful assistant. Answer concisely.'

for name, body in [
    ('real skill (21KB)', real_body),
    ('mutated skill', mutated_body),
    ('bad skill (short)', bad_body),
]:
    print(f"\n--- {name} ---")
    print(f"Body length: {len(body)} chars")
    
    # Invoke skill as agent
    print("Invoking LLM...")
    resp = _invoke_skill_as_agent(body, ex.task_input)
    print(f"Response length: {len(resp)} chars")
    print(f"Response: {resp[:200]}...")
    
    # Score directly (bypassing the is_skill_body check by passing a prediction)
    class FakePred:
        def __init__(self, o):
            self.output = o
    
    score = skill_fitness_metric(ex, FakePred(resp))
    print(f"Score: {score:.4f}")
    
    # Also test is_skill_body detection
    is_body = len(body) > 1500 and body.count("## ") >= 2
    print(f"is_skill_body detection: {is_body}")

print("\n=== DONE ===")
