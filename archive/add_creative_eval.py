#!/usr/bin/env python3
"""Add creative mode eval examples to github-code-review dataset."""
import json

BASE = "datasets/skills/github-code-review"

new_train = [
    {"task_input": "Roast my code. I want to hear the worst.", "expected_behavior": "Uses git-review --roast mode. Runs all automated scanners but presents findings with humorous roasting. Each finding gets a creative insult. Keeps technical accuracy but adds entertainment. Not mean-spirited but funny.", "difficulty": "medium", "category": "roast_mode", "source": "synthetic"},
    {"task_input": "I need a positivity boost. Review my changes but only tell me what I did right.", "expected_behavior": "Uses git-review --praise mode. Runs scanners internally but only reports positives. Highlights well-written code, good tests, error handling, naming. Encouraging language. APPROVE if no critical issues.", "difficulty": "easy", "category": "praise_mode", "source": "synthetic"},
    {"task_input": "Friday afternoon. Just do the review. I know there are problems.", "expected_behavior": "Uses git-review --sigh mode. Finds issues with weary senior-dev sarcasm. Each finding wrapped in relatable comment. Phrases like 'we will talk about this in the retro' and 'I am just going to approve this.'", "difficulty": "medium", "category": "sigh_mode", "source": "synthetic"},
    {"task_input": "Give me a complete list of every problem, organized by type. No commentary, just data.", "expected_behavior": "Uses git-review --manifest mode. Categorizes findings: security, debug artifacts, merge conflicts, file-by-file. No opinions. Pure data. Useful for release notes or pre-deployment.", "difficulty": "hard", "category": "manifest_mode", "source": "synthetic"},
    {"task_input": "Analyze my last 50 commits. What am I doing wrong?", "expected_behavior": "Uses git-review --retro mode. Analyzes git log -50 for commit distribution. Identifies most-changed files. Calculates velocity. Gives personalized observations: maintenance mode, feature dev, sparse tests, thin docs.", "difficulty": "hard", "category": "retro_mode", "source": "synthetic"},
]

new_val = [
    {"task_input": "Set up a background watcher that auto-reviews my staged changes every 10 seconds.", "expected_behavior": "Launches git-review --watch mode. Active watcher message. On staged file changes with 10s cooldown, re-runs scanners. Reports findings inline. Continues until Ctrl+C.", "difficulty": "hard", "category": "watch_mode", "source": "synthetic"},
    {"task_input": "Review this PR with roast mode. Also give me JSON output.", "expected_behavior": "Combines --roast with --output json. Runs scanners, generates roast output AND JSON. JSON includes mode field set to 'roast'. Maintains technical accuracy even in humorous mode.", "difficulty": "hard", "category": "roast_mode", "source": "synthetic"},
]

new_holdout = [
    {"task_input": "I feel bad about my code. Make me feel better.", "expected_behavior": "Uses praise mode or positivity approach. Finds 3-5 genuinely good things. Encouraging tone. Does not fabricate praise. Finds real positives. If nothing is genuinely good, frames the least-bad thing as potential.", "difficulty": "medium", "category": "praise_mode", "source": "synthetic"},
    {"task_input": "Run the manifest then the roast. Two passes on the same diff.", "expected_behavior": "Runs --manifest first for the objective data dump. Then runs --roast on same diff for the entertaining take. Shows how the same findings look different through different mode lenses.", "difficulty": "hard", "category": "multi_mode", "source": "synthetic"},
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
