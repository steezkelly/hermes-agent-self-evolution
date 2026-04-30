#!/usr/bin/env python3.12
"""Validate v2 constraint checks against the 7 VALIDATING skills.

For each skill:
  - Load baseline body
  - Load latest evolved body (from best run output)
  - Run PurposePreservationChecker
  - Report: PASS (accepted) / REJECT (blocked) / MAYBE (needs review)
  - Compare against expected outcome

Expected outcomes (from session log):
  REJECT: hermes-agent, mnemosyne-self-evolution-tools
  ACCEPT: ceo-orchestration, systematic-debugging
  MAYBE: companion-workflows
  UNKNOWN: companion-interview-workflow, companion-system-orchestration
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from evolution.core.constraints_v2 import PurposePreservationChecker, extract_body

OUTPUT = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "output"

VALIDATING_SKILLS = [
    "hermes-agent",
    "companion-workflows",
    "ceo-orchestration",
    "mnemosyne-self-evolution-tools",
    "companion-system-orchestration",
    "companion-interview-workflow",
    "systematic-debugging",
]

# Expected outcomes (from session analysis)
EXPECTED = {
    "hermes-agent": "REJECT",
    "companion-workflows": "MAYBE",
    "ceo-orchestration": "ACCEPT",
    "mnemosyne-self-evolution-tools": "REJECT",
    "companion-system-orchestration": "ACCEPT",
    "companion-interview-workflow": "ACCEPT",
    "systematic-debugging": "ACCEPT",
}


def find_latest_run(skill_name: str) -> Path | None:
    skill_dir = OUTPUT / skill_name
    if not skill_dir.exists():
        return None
    runs = sorted(skill_dir.glob("**/evolved_skill.md"), reverse=True)
    if runs:
        return runs[0].parent
    return None


def find_baseline_skill(skill_name: str) -> Path | None:
    """Find baseline from output directory (baseline_skill.md)."""
    skill_dir = OUTPUT / skill_name
    if not skill_dir.exists():
        return None
    runs = sorted(skill_dir.glob("**/baseline_skill.md"), reverse=True)
    if runs:
        return runs[0]
    return None


def main():
    checker = PurposePreservationChecker()
    results = []

    for skill in VALIDATING_SKILLS:
        print(f"\n{'='*60}")
        print(f"SKILL: {skill}")
        print(f"{'='*60}")

        baseline_path = find_baseline_skill(skill)
        if not baseline_path:
            print(f"  [WARN] No baseline skill found in {SKILLS_DIR}")
            continue

        with open(baseline_path) as f:
            baseline_raw = f.read()
        baseline_body = extract_body(baseline_raw)

        run_dir = find_latest_run(skill)
        if run_dir is None:
            print(f"  [WARN] No evolved output found in {OUTPUT / skill}")
            continue

        evolved_file = run_dir / "evolved_skill.md"
        if not evolved_file.exists():
            print(f"  [WARN] No evolved_skill.md in {run_dir}")
            continue

        with open(evolved_file) as f:
            evolved_raw = f.read()
        evolved_body = extract_body(evolved_raw)

        # Load metrics
        metrics_file = run_dir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file) as f:
                metrics = json.load(f)
            delta = metrics.get("improvement", 0.0)
            src = metrics.get("eval_source", "?")
            print(f"  Run: {run_dir.name}")
            print(f"  Source: {src}")
            print(f"  Improvement: {delta:+.4f}")
        else:
            report_file = run_dir / "report.json"
            if report_file.exists():
                with open(report_file) as f:
                    report = json.load(f)
                delta = report.get("improvement", 0.0)
                rec = report.get("recommendation", "?")
                print(f"  Run: {run_dir.name}")
                print(f"  Recommendation: {rec}")
                print(f"  Improvement: {delta:+.4f}")

        # Check purpose preservation
        ok, msg = checker.check(evolved_body, baseline_body)

        print(f"\n  Purpose Preservation: {'PASS' if ok else 'REJECT'}")
        for part in msg.split(" — "):
            print(f"    {part[:120]}")

        expected = EXPECTED.get(skill, "UNKNOWN")
        actual = "ACCEPT" if ok else "REJECT"
        if expected == "MAYBE":
            verdict = f"OK (expected MAYBE)"
        elif expected == actual:
            verdict = f"OK ({actual})"
        else:
            verdict = f"MISMATCH (expected {expected}, got {actual})"

        print(f"\n  Expected: {expected} | Actual: {actual} | {verdict}")

        results.append({
            "skill": skill,
            "expected": expected,
            "actual": actual,
            "verdict": verdict,
            "ok": ok,
            "msg": msg,
        })

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    matches = sum(
        1 for r in results
        if r["expected"] in ("ACCEPT", "REJECT") and r["expected"] == r["actual"]
    )
    maybes = sum(1 for r in results if r["expected"] == "MAYBE")
    print(f"  Matched expected: {matches}/{len(results) - maybes} ({maybes} MAYBE excluded)")
    print()
    for r in results:
        print(f"  [{r['verdict']:20s}] {r['skill']}")
    print()


if __name__ == "__main__":
    main()
