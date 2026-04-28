#!/usr/bin/env python3
"""
Phase 2: Session Quality Analyzer
=================================
Analyzes Hermes session history to identify:
1. Skill usage signals (which skills were loaded in sessions)
2. Task outcomes (successful completions, failures, user corrections)
3. Sessions worth converting to eval dataset examples
4. Skills that need optimization (declining success rates)

This is the "feedback loop" half of Phase 2 — gathering real signal
from actual usage to improve future evaluation datasets.

Usage:
    python session_quality_analyzer.py --days 7 --min-messages 5
    python session_quality_analyzer.py --skills-only
    python session_quality_analyzer.py --export dataset_additions.jsonl
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Companions system skill names (from ~/.hermes/skills/companion-system/)
COMPANION_SKILLS = {
    "companion-interview-pipeline",
    "companion-interview-workflow",
    "companion-memory",
    "companion-memory-tiers",
    "companion-personas",
    "companion-plan-review",
    "companion-roundtable",
    "companion-safety",
    "companion-workflows",
    "mnemosyne-maintenance",
    "mnemosyne-self-evolution-tools",
}

# Keywords that indicate successful task completion
SUCCESS_KEYWORDS = [
    "done", "completed", "finished", "accomplished", "deployed",
    "saved", "written", "created", "fixed", "resolved", "succeeded",
    "thank you", "perfect", "excellent", "great work"
]

# Keywords that indicate failure, correction, or negative feedback
FAILURE_KEYWORDS = [
    "no that's wrong", "not correct", "that's wrong", "try again",
    "don't do that", "stop", "cancel", "wait", "actually",
    "failed", "error", "didn't work", "doesn't work",
    "no improvement", "still broken", "reverted", "rolled back",
    "that's not what i asked", "not what i wanted"
]

# Keywords that suggest a skill was used or invoked
SKILL_USAGE_KEYWORDS = [
    "skill", "load skill", "skill_view", "following the skill",
    "as the skill says", "per the skill", "according to the skill",
    "companion", "workflow", "interview", "roundtable", "mnemosyne"
]


def get_recent_sessions(db_path: str, days: int, min_messages: int) -> list[dict]:
    """Fetch recent sessions with their message counts."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cutoff = (datetime.now() - timedelta(days=days)).timestamp()

    cur.execute("""
        SELECT
            s.id,
            s.source,
            s.model,
            s.started_at,
            s.ended_at,
            s.end_reason,
            s.message_count,
            s.tool_call_count,
            s.input_tokens,
            s.output_tokens,
            s.estimated_cost_usd,
            s.title,
            COUNT(m.id) as actual_messages
        FROM sessions s
        LEFT JOIN messages m ON m.session_id = s.id
        WHERE s.started_at > ?
        GROUP BY s.id
        HAVING actual_messages >= ?
        ORDER BY s.started_at DESC
    """, (cutoff, min_messages))

    sessions = [dict(row) for row in cur.fetchall()]
    conn.close()
    return sessions


def get_session_messages(db_path: str, session_id: str) -> list[dict]:
    """Get all messages for a session."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, role, content, tool_calls, tool_name, timestamp
        FROM messages
        WHERE session_id = ?
        ORDER BY timestamp ASC
    """, (session_id,))

    messages = [dict(row) for row in cur.fetchall()]
    conn.close()
    return messages


def analyze_session_quality(session: dict, messages: list[dict]) -> dict:
    """Analyze a single session for quality signals."""
    all_content = " ".join(
        m.get("content", "") or ""
        for m in messages
    ).lower()

    # Count success/failure signals
    success_count = sum(1 for kw in SUCCESS_KEYWORDS if kw in all_content)
    failure_count = sum(1 for kw in FAILURE_KEYWORDS if kw in all_content)

    # Skill usage detection
    skill_hints = [kw for kw in SKILL_USAGE_KEYWORDS if kw in all_content]

    # Companion skill mentions
    companion_mentions = [
        s for s in COMPANION_SKILLS
        if s.replace("-", " ") in all_content or s.replace("_", " ") in all_content
    ]

    # First assistant message (often contains skill loading indication)
    firstAssistant = next(
        (m for m in messages if m["role"] == "assistant"),
        {}
    )

    # Last assistant message tone
    lastAssistant = None
    for m in reversed(messages):
        if m["role"] == "assistant" and m.get("content"):
            lastAssistant = m["content"][:500].lower()
            break

    # User corrections: look for messages that override or correct
    user_messages = [m for m in messages if m["role"] == "user"]
    correction_count = sum(
        1 for m in user_messages
        if any(kw in (m.get("content") or "").lower() for kw in FAILURE_KEYWORDS[:8])
    )

    # Outcome scoring
    if failure_count > success_count and correction_count > 1:
        outcome = "failed"
        score_signal = "negative"
    elif success_count > failure_count and correction_count == 0:
        outcome = "succeeded"
        score_signal = "positive"
    elif correction_count > 0:
        outcome = "partial"
        score_signal = "mixed"
    else:
        outcome = "unknown"
        score_signal = "neutral"

    # Convert timestamps
    started = datetime.fromtimestamp(session["started_at"]).isoformat()
    ended = datetime.fromtimestamp(session["ended_at"]).isoformat() if session["ended_at"] else None

    return {
        "session_id": session["id"],
        "source": session["source"],
        "model": session["model"],
        "started_at": started,
        "ended_at": ended,
        "end_reason": session["end_reason"],
        "message_count": session["actual_messages"],
        "tool_call_count": session["tool_call_count"],
        "outcome": outcome,
        "score_signal": score_signal,
        "success_signals": success_count,
        "failure_signals": failure_count,
        "user_corrections": correction_count,
        "companion_skills_mentioned": companion_mentions,
        "skill_keywords_found": skill_hints[:5],
        "title": session.get("title") or "(no title)",
        "cost_usd": session.get("estimated_cost_usd") or 0,
    }


def is_good_eval_example(session_analysis: dict, messages: list[dict]) -> bool:
    """Determine if a session would make a good eval dataset example."""
    # Skip very short sessions
    if session_analysis["message_count"] < 4:
        return False

    # Skip sessions with unknown outcomes on companion skills
    if session_analysis["companion_skills_mentioned"]:
        if session_analysis["outcome"] in ("succeeded", "partial"):
            return True

    # Good positive examples: high success signals, no corrections
    if (
        session_analysis["score_signal"] == "positive"
        and session_analysis["message_count"] >= 6
        and len(session_analysis["companion_skills_mentioned"]) == 0
    ):
        # Check for substantive content (not just chit-chat)
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        if total_chars > 1000:
            return True

    return False


def build_eval_example(session_analysis: dict, messages: list[dict]) -> dict:
    """Convert a high-quality session into an eval dataset example."""
    # Find the user query that started the substantive work
    user_messages = [
        m for m in messages
        if m["role"] == "user" and len(m.get("content", "") or "") > 50
    ]

    task_input = ""
    if user_messages:
        # Use the first substantive user message as the task
        task_input = user_messages[0].get("content", "")[:2000]

    # Extract the last assistant response as reference for expected behavior
    assistant_content = ""
    for m in reversed(messages):
        if m["role"] == "assistant" and m.get("content"):
            assistant_content = m["content"][:1500]
            break

    return {
        "task_input": task_input,
        "expected_behavior": (
            f"Helpful, substantive response addressing the user's request. "
            f"Session outcome: {session_analysis['outcome']}. "
            f"Reference: {assistant_content[:500]}"
        ),
        "difficulty": "medium" if session_analysis["message_count"] > 10 else "easy",
        "category": "real_usage_example",
        "source": f"sessiondb:{session_analysis['session_id'][:8]}",
    }


def main():
    parser = argparse.ArgumentParser(description="Phase 2 session quality analyzer")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--min-messages", type=int, default=3, help="Min messages per session")
    parser.add_argument("--db", default="/home/steve/.hermes/state.db", help="SessionDB path")
    parser.add_argument("--skills-only", action="store_true", help="Only show companion skill sessions")
    parser.add_argument("--export", help="Export good sessions to JSONL file")
    parser.add_argument("--limit", type=int, default=50, help="Max sessions to analyze")
    args = parser.parse_args()

    print(f"Fetching sessions from last {args.days} days...")
    sessions = get_recent_sessions(args.db, args.days, args.min_messages)
    print(f"Found {len(sessions)} sessions with {args.min_messages}+ messages")

    if not sessions:
        print("No sessions found. Try --days 14 or --days 30")
        sys.exit(0)

    sessions = sessions[:args.limit]

    print(f"\nAnalyzing {len(sessions)} sessions...\n")

    all_analyses = []
    skill_sessions = defaultdict(list)

    for session in sessions:
        messages = get_session_messages(args.db, session["id"])
        analysis = analyze_session_quality(session, messages)

        for skill in analysis["companion_skills_mentioned"]:
            skill_sessions[skill].append(analysis)

        all_analyses.append(analysis)

    # Summary statistics
    outcomes = defaultdict(int)
    for a in all_analyses:
        outcomes[a["outcome"]] += 1

    print("=== Session Outcome Summary ===")
    for outcome, count in sorted(outcomes.items(), key=lambda x: -x[1]):
        pct = count / len(all_analyses) * 100
        print(f"  {outcome:12s}: {count:3d} ({pct:.1f}%)")

    print(f"\n=== Companion Skill Sessions ===")
    if skill_sessions:
        for skill, analyses in sorted(skill_sessions.items(), key=lambda x: -len(x[1])):
            succeeded = sum(1 for a in analyses if a["outcome"] == "succeeded")
            partial = sum(1 for a in analyses if a["outcome"] == "partial")
            print(f"  {skill:40s}: {len(analyses)} sessions ({succeeded} ok, {partial} partial)")
    else:
        print("  (no companion skill sessions in this period)")

    if args.skills_only:
        return

    # Find good eval examples
    good_examples = []
    for analysis, session in zip(
        all_analyses,
        sessions
    ):
        messages = get_session_messages(args.db, session["id"])
        if is_good_eval_example(analysis, messages):
            example = build_eval_example(analysis, messages)
            example["analysis"] = {
                "outcome": analysis["outcome"],
                "score_signal": analysis["score_signal"],
                "session_id": analysis["session_id"],
                "started_at": analysis["started_at"],
            }
            good_examples.append(example)

    print(f"\n=== Eval Dataset Candidates ===")
    print(f"  {len(good_examples)} high-quality sessions found")

    if good_examples and not args.export:
        print("\nTop candidates:")
        for ex in good_examples[:5]:
            print(f"  [{ex['analysis']['outcome']}] {ex['task_input'][:80]}...")

    if args.export:
        out_path = Path(args.export)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            for ex in good_examples:
                f.write(json.dumps(ex) + "\n")
        print(f"\nExported {len(good_examples)} examples to {out_path}")


if __name__ == "__main__":
    main()
