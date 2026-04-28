#!/usr/bin/env python3
"""
SessionDB → Eval Dataset Converter
==================================
Converts high-quality sessiondb session candidates into properly formatted
eval dataset examples for skill-specific training.

Usage:
    # Convert all candidates into a merged pool
    python session_to_dataset.py --input datasets/sessiondb_candidates.jsonl \\
        --output datasets/sessiondb_enriched.jsonl

    # Add to a specific skill's dataset
    python session_to_dataset.py --input datasets/sessiondb_candidates.jsonl \\
        --skill companion-workflows \\
        --append datasets/skills/companion-workflows/train.jsonl

    # Review what would be added before committing
    python session_to_dataset.py --input datasets/sessiondb_candidates.jsonl \\
        --skill companion-workflows \\
        --dry-run
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

# Skill domain keywords — what topics a session should cover to be relevant
SKILL_DOMAINS = {
    "companion-interview-pipeline": [
        "interview", "question", "ask steve", "companion role", "psychologist",
        "curator", "researcher", "manager", "ceo", "hr", "philosopher", "engineer",
        "round", "follow-up question", "interview-progress"
    ],
    "companion-interview-workflow": [
        "interview", "companion", "workflow", "question", "role", "persona",
        "delegation", "delegate_task", "spawn-agent"
    ],
    "companion-memory": [
        "mnemosyne", "memory", "remember", "triple", "forget", "recall",
        "importance", "scope", "knowledge graph", "episodic", "wm", "em"
    ],
    "companion-memory-tiers": [
        "tier", "working memory", "episodic", "semantic", "importance",
        "consolidation", "beam", "mnemosyne", "memory tier"
    ],
    "companion-personas": [
        "companion", "persona", "role", "character", "voice", "style",
        "curator", "researcher", "engineer", "ceo", "hr", "philosopher",
        "psychologist", "system", "manager"
    ],
    "companion-plan-review": [
        "plan review", "design review", "review queue", "companion plan",
        "implementation plan", "review order"
    ],
    "companion-roundtable": [
        "roundtable", "multi-persona", "discussion", "synthesis", "debate",
        "coffee shop", "companions talking", "cross-role"
    ],
    "companion-safety": [
        "delegation", "timeout", "pii", "privacy", "boundary", "safety",
        "constraint", "workaround", "hermes delegation"
    ],
    "companion-workflows": [
        "workflow", "feedback loop", "collaborative", "investigative", "pair",
        "planning", "roadmap", "A/B test", "post-completion", "audit",
        "health check", "strategic"
    ],
    "mnemosyne-maintenance": [
        "backup", "consolidation", "mnemosyne", "sleep", "maintenance",
        "repair", "clean", "gc", "garbage"
    ],
    "mnemosyne-self-evolution-tools": [
        "self-evolution", "diagnostic", "introspect", "metrics", "stats",
        "health check", "observatory", "monitor"
    ],
}

# Task type classifiers
TASK_TYPES = {
    "investigation": ["investigate", "research", "find evidence", "look for", "search"],
    "delegation": ["delegate", "spawn", "dispatch", "send to", "assign to"],
    "creation": ["write", "create", "make", "draft", "compose", "save to"],
    "analysis": ["analyze", "review", "synthesize", "reflect", "assess", "evaluate"],
    "orchestration": ["orchestrate", "coordinate", "manage", "schedule", "plan"],
    "feedback": ["feedback", "calibrate", "adjust", "correct", "improve"],
    "memory": ["remember", "store", "recall", "mnemosyne", "triple", "forget"],
}


def classify_task_type(content: str) -> str:
    """Classify what type of task this session represents."""
    content_lower = content.lower()
    scores = {}
    for task_type, keywords in TASK_TYPES.items():
        scores[task_type] = sum(1 for kw in keywords if kw in content_lower)
    if max(scores.values()) == 0:
        return "general"
    return max(scores, key=scores.get)


def skill_relevance(session: dict) -> dict[str, float]:
    """Score how relevant a session is to each skill domain.
    Returns dict of skill -> relevance score (0.0-1.0).
    """
    content = (session.get("task_input", "") + " " + session.get("expected_behavior", "")).lower()
    scores = {}
    for skill, keywords in SKILL_DOMAINS.items():
        matches = sum(1 for kw in keywords if kw in content)
        scores[skill] = min(1.0, matches / 3)  # Normalize: 3+ keyword matches = full score
    return scores


def convert_session_to_examples(session: dict) -> list[dict]:
    """Convert a single session into one or more eval examples for relevant skills."""
    task_input = session.get("task_input", "")
    expected = session.get("expected_behavior", "")
    analysis = session.get("analysis", {})
    outcome = analysis.get("outcome", "unknown")
    score_signal = analysis.get("score_signal", "neutral")

    # Skip sessions that are just cron job reports
    if "scheduled cron job" in task_input.lower()[:100]:
        return []
    # Skip sessions that are just background process notifications
    if task_input.lower().startswith("[important") and "completed" in task_input.lower():
        return []

    examples = []
    task_type = classify_task_type(task_input)

    # Determine difficulty from session characteristics
    msg_count = len(task_input) // 200  # rough proxy
    if msg_count > 10:
        difficulty = "hard"
    elif msg_count > 4:
        difficulty = "medium"
    else:
        difficulty = "easy"

    # Only create positive examples from succeeded sessions
    if outcome == "succeeded" and score_signal == "positive":
        category = f"positive_{task_type}"
    elif outcome == "partial":
        category = f"partial_{task_type}"
    else:
        category = task_type

    example = {
        "task_input": task_input[:2000],  # Truncate long inputs
        "expected_behavior": expected[:500],
        "difficulty": difficulty,
        "category": category,
        "source": session.get("source", "sessiondb"),
    }

    examples.append(example)
    return examples


def main():
    parser = argparse.ArgumentParser(description="Convert session candidates to eval dataset")
    parser.add_argument("--input", required=True, help="Input JSONL (session candidates)")
    parser.add_argument("--output", help="Output JSONL file")
    parser.add_argument("--skill", help="Filter to a specific skill")
    parser.add_argument("--append", help="Append to existing dataset file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be added")
    parser.add_argument("--min-relevance", type=float, default=0.0, help="Min relevance threshold")
    args = parser.parse_args()

    # Load sessions
    sessions = []
    with open(args.input) as f:
        for line in f:
            if line.strip():
                sessions.append(json.loads(line))

    print(f"Loaded {len(sessions)} session candidates")

    # Convert each session
    all_examples = []
    skill_counts = defaultdict(int)

    for session in sessions:
        examples = convert_session_to_examples(session)
        for ex in examples:
            if args.skill:
                # Check skill relevance
                relevance = skill_relevance(session)
                if relevance.get(args.skill, 0) < args.min_relevance:
                    continue
                ex["relevance"] = relevance.get(args.skill, 0)

            all_examples.append(ex)
            skill_counts[ex["category"]] += 1

    print(f"\n=== Conversion Summary ===")
    print(f"Total examples: {len(all_examples)}")

    print(f"\nBy category:")
    for cat, count in sorted(skill_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:40s}: {count}")

    if args.dry_run:
        print("\n--- Dry run: would add ---")
        for ex in all_examples[:10]:
            print(f"  [{ex['difficulty']}] {ex['task_input'][:80]}...")
        return

    if not args.output and not args.append:
        print("\nNo --output or --append specified. Showing top examples:")
        for ex in all_examples[:10]:
            print(f"\n  [{ex['difficulty']}] [{ex['category']}]")
            print(f"  {ex['task_input'][:120]}...")
        return

    # Write output
    out_path = Path(args.output or args.append)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.append else "w"
    count = 0
    with open(out_path, mode) as f:
        for ex in all_examples:
            # Remove internal fields before writing
            to_write = {k: v for k, v in ex.items() if k not in ("relevance",)}
            f.write(json.dumps(to_write) + "\n")
            count += 1

    action = "Appended" if args.append else "Wrote"
    print(f"\n{action} {count} examples to {out_path}")


if __name__ == "__main__":
    main()
