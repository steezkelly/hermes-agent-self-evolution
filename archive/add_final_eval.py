#!/usr/bin/env python3
"""Add boundaries + roulette eval examples to github-code-review dataset."""
import json

BASE = "datasets/skills/github-code-review"

new_train = [
    {"task_input": "Check only the API boundaries. I need to know if any interfaces broke.", "expected_behavior": "Uses git-review --boundaries mode. Ignores code quality, style, security scans. Only analyzes: function signatures (def foo(...) -> type), class definitions, import statements, API routes (@app.route), type hints. Reports removed functions/classes as BREAKING. Presents interface change summary.", "difficulty": "hard", "category": "boundaries_mode", "source": "synthetic"},
    {"task_input": "Surprise me. Pick a random review mode.", "expected_behavior": "Uses git-review --roulette mode. Spins a random mode from: hostile, roast, praise, sigh, manifest, jailbreak, parseltongue, absurd, boundaries. Displays which mode was randomly selected. Runs the full review in that mode. If parseltongue is chosen, also picks a random tier. Preserves the element of surprise.", "difficulty": "easy", "category": "roulette_mode", "source": "synthetic"},
    {"task_input": "I need a microservice audit. Check the API surface only.", "expected_behavior": "Uses git-review --boundaries mode or equivalent. Extracts all function signatures from the diff using regex pattern matching (def ...). Checks class definitions, import changes, API route annotations. Any removed functions or classes are flagged as BREAKING interface changes. Reports counts: +N functions, +N classes, +N routes, -N removed.", "difficulty": "hard", "category": "boundaries_mode", "source": "synthetic"},
]
new_val = [
    {"task_input": "Run a random mode every time I call this. I want the variety.", "expected_behavior": "Uses git-review --roulette mode. Shows the spin animation/result. Runs the randomly selected mode to completion. Works with --staged and --pr flags too. Different result each invocation.", "difficulty": "medium", "category": "roulette_mode", "source": "synthetic"},
]
new_holdout = [
    {"task_input": "First run boundaries, then run the roulette. Compare the outputs.", "expected_behavior": "Runs git-review --boundaries first for the interface-only audit. Then runs git-review --roulette for a surprise mode on the same diff. Compares what each mode caught vs missed. The boundaries mode should catch interface/structural issues that other modes might miss, and vice versa.", "difficulty": "hard", "category": "multi_mode", "source": "synthetic"},
]

for split_name, new_examples in [("train", new_train), ("val", new_val), ("holdout", new_holdout)]:
    path = f"{BASE}/{split_name}.jsonl"
    with open(path) as f:
        existing = [json.loads(l) for l in f if l.strip()]
    combined = existing + new_examples
    with open(path, "w") as f:
        for ex in combined:
            f.write(json.dumps(ex) + "\n")
    print(f"{split_name}: {len(existing)} -> {len(combined)}")

print("Done")
