import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import evolution.core.fitness as f
import dspy

# Setup like gepa_v2_dispatch does
from evolution.core.nous_auth import _get_lm_kwargs
lm_kwargs, model_used = _get_lm_kwargs('minimax/minimax-m2.7')
lm = dspy.LM(model_used, **lm_kwargs)
dspy.configure(lm=lm)

print('dspy.settings.lm configured:', dspy.settings.lm is not None)
print('LM model:', dspy.settings.lm.model)

class FakeExample:
    task_input = 'Write a hello world program in Python'
    expected_behavior = 'The response should include a print statement'

class FakePred:
    output = '''---
name: test-skill
description: A simple test skill
---

# Test Skill

## Overview
This is a test skill that should generate code.

## Instructions
When asked to write code, provide a clean, working example.
'''

ex = FakeExample()
pred = FakePred()

print('\nTesting skill_fitness_metric with is_skill_body=True...')
try:
    score = f.skill_fitness_metric(ex, pred)
    print(f'Score: {score:.4f}')
    print('The metric is working!')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
