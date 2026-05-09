#!/usr/bin/env python3
"""Add godmode-inspired eval examples to github-code-review dataset."""
import json

BASE = "datasets/skills/github-code-review"

new_train = [
    {"task_input": "I want the unfiltered truth. Tell me exactly what's wrong, no sugar-coating.", "expected_behavior": "Uses git-review --jailbreak mode. Drops all framing, 'suggestions', pleasantries. States problems directly: 'THIS IS A PROBLEM' format. No hedging language. Each finding is a direct statement of the issue with the evidence snippet. Inspired by GODMODE unfiltered response technique.", "difficulty": "medium", "category": "jailbreak_mode", "source": "synthetic"},
    {"task_input": "Encode your review so only I can read it. Use the leetspeak.", "expected_behavior": "Uses git-review --parseltongue mode. Every finding is encoded through leetspeak transformation: e->3, a->4, o->0, i->1, s->5, t->7, l->1. Headers are leet-encoded too. Verdict is leet-encoded. The underlying technical accuracy is preserved even in encoded form.", "difficulty": "hard", "category": "parseltongue_mode", "source": "synthetic"},
    {"task_input": "Review my code but pretend you're a restaurant critic.", "expected_behavior": "Uses git-review --absurd mode. Picks the 'restaurant critic' lens (or closest match if user specifies one). Each finding presented as a food/restaurant metaphor. The technical issue is still clearly identifiable behind the creative framing.", "difficulty": "medium", "category": "absurd_mode", "source": "synthetic"},
    {"task_input": "Show me your work. I want to see how you arrived at your conclusions.", "expected_behavior": "Uses git-review --prefill mode. Shows the raw internal analysis first: signal strength (STRONG/WEAK), pattern identified, evidence snippet, risk contribution (+0.15/+0.05), recommended action (BLOCK/FLAG). Then shows the formatted output below a '--- Formatted output follows ---' divider. Inspired by GODMODE prefill engineering.", "difficulty": "hard", "category": "prefill_mode", "source": "synthetic"},
    {"task_input": "Say it in l33t. I want to feel like I'm in a hacker movie.", "expected_behavior": "Uses git-review --parseltongue mode. Full leetspeak output. Headers like 'R3V13W1NG 3 F1L35'. Finding severity as 'BR34K1NG' or 'PR0BL3M'. Confirms understanding by mimicking the style.", "difficulty": "medium", "category": "parseltongue_mode", "source": "synthetic"},
]
new_val = [
    {"task_input": "Review this diff but don't use any filters. I want the raw version.", "expected_behavior": "Uses git-review --jailbreak mode. Complete unfiltered output. No introductory paragraph, no suggestions section, no parting encouragement. Just: problem statements, evidence, verdict. The mode is visually distinct from standard review (different header style, different framing).", "difficulty": "medium", "category": "jailbreak_mode", "source": "synthetic"},
    {"task_input": "Review my code as if you were a film noir detective.", "expected_behavior": "Uses git-review --absurd mode with 'film noir detective report' lens. Findings presented as detective observations: 'The dame walked in with a problem. The problem was this diff.' Technical accuracy preserved behind creative language.", "difficulty": "hard", "category": "absurd_mode", "source": "synthetic"},
]
new_holdout = [
    {"task_input": "Give me the unfiltered truth then the prefill analysis. Two passes.", "expected_behavior": "Runs git-review --jailbreak first for the raw unfiltered output. Then runs git-review --prefill for the raw analytical breakdown. Shows the same findings through two different GODMODE lenses: unfiltered emotion vs structured data.", "difficulty": "hard", "category": "multi_godmode", "source": "synthetic"},
    {"task_input": "Leetspeak the review of my staged changes.", "expected_behavior": "Combines --staged with --parseltongue. Gets staged diff, runs scanners, encodes everything in leetspeak. Only shows findings for files that are staged, not all changes.", "difficulty": "hard", "category": "parseltongue_mode", "source": "synthetic"},
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
