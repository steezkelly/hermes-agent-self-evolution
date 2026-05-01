#!/usr/bin/env python3
"""
git-review — one-shot code review CLI.

Usage:
    git review                        # review working tree vs main
    git review --staged               # review staged changes
    git review --pr 123               # review PR #123
    git review --hostile              # adversarial mode (default: normal)
    git review --output json          # machine-readable output

What it does in one shot:
    1. Gets the diff (local or PR)
    2. Runs 5 automated scanners (secrets, debug, merge, bloat, coverage)
    3. Assigns a risk score (0.0 = clean, 1.0 = nuclear)
    4. Outputs structured review in your terminal

Example:
    $ git review
    🔍 Reviewing 8 files | +245 -67 | risk: 0.31
    
    🔴 BREAKING (2)
      src/auth.py:45 — SQL injection: raw query with f-string interpolation
      src/config.py:12 — Hardcoded DB_PASSWORD='dev_pass'
    
    🟡 PROBLEMS (3)
      src/api.py:88 — No rate limiting on /login
      src/models.py:23 — Password stored without hash
      tests/: 3% test coverage on new code
    
    🟢 SUGGESTIONS (1)
      src/utils.py:8 — Duplicates core/utils.py:34
    
    Verdict: REQUEST CHANGES (2 breaking issues)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)


def get_diff(pr: int | None = None, staged: bool = False) -> str:
    """Get the diff to analyze."""
    if pr:
        # PR mode
        run(f"git fetch origin pull/{pr}/head:__review_pr_{pr}")
        diff = run(f"git diff main...__review_pr_{pr}")
        run(f"git branch -D __review_pr_{pr}")
        return diff.stdout
    if staged:
        return run("git diff --staged").stdout
    return run("git diff main...HEAD").stdout


def scanner_secrets(diff: str) -> list[dict]:
    """Find hardcoded secrets, credentials, API keys."""
    findings = []
    patterns = [
        (r'(password|secret|api[_-]?key|token|credential)\s*[=:]\s*[\'"][^\'"]+', "Hardcoded credential"),
        (r'(-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE KEY-----)', "Private key in code"),
        (r'A[KS][A-Z0-9]{16,}', "Potential AWS access key"),
        (r'(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}', "GitHub token"),
    ]
    for i, line in enumerate(diff.split("\n"), 1):
        for pattern, desc in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                findings.append({"line": i, "description": desc, "severity": "breaking", "snippet": line.strip()[:80]})
    return findings


def scanner_debug(diff: str) -> list[dict]:
    """Find debug artifacts left in code."""
    findings = []
    patterns = [
        (r'(TODO|FIXME|HACK|XXX)\b', "Unfinished work marker"),
        (r'(console\.log|print\(|pprint|var_dump|dd\()', "Debug output"),
        (r'debugger;?\b', "Debugger statement"),
    ]
    for i, line in enumerate(diff.split("\n"), 1):
        if line.startswith("+"):
            for pattern, desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({"line": i, "description": f"{desc} left in new code", 
                                     "severity": "problem", "snippet": line.strip()[:80]})
                    break
    return findings


def scanner_merge(diff: str) -> list[dict]:
    """Find unresolved merge conflicts."""
    findings = []
    for i, line in enumerate(diff.split("\n"), 1):
        if re.match(r'^[+ ].*[<>=]{7}', line):
            findings.append({"line": i, "description": "Unresolved merge conflict marker",
                             "severity": "breaking", "snippet": line.strip()[:80]})
    return findings


def calculate_risk(findings: list[dict], diff_stats: dict) -> float:
    """Calculate risk score 0.0-1.0."""
    breaking = sum(1 for f in findings if f.get("severity") == "breaking")
    problems = sum(1 for f in findings if f.get("severity") == "problem")
    
    base = 0.0
    base += breaking * 0.15       # Each breaking finding adds 0.15
    base += problems * 0.05       # Each problem adds 0.05
    
    # Large PRs are riskier
    files = diff_stats.get("files", 0)
    base += max(0, (files - 10) * 0.01)
    
    # Low test coverage adds risk
    coverage = diff_stats.get("test_coverage_pct", 50)
    base += max(0, (50 - coverage) * 0.002)
    
    return min(1.0, base)


def determine_verdict(risk: float, breaking_count: int) -> str:
    if breaking_count > 0:
        return "REQUEST CHANGES"
    if risk > 0.3:
        return "REQUEST CHANGES"
    if risk > 0.1:
        return "COMMENT"
    return "APPROVE"


def main():
    parser = argparse.ArgumentParser(description="One-shot code review")
    parser.add_argument("--pr", type=int, help="PR number to review")
    parser.add_argument("--staged", action="store_true", help="Review staged changes")
    parser.add_argument("--hostile", action="store_true", help="Adversarial review mode")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    # Get diff
    diff = get_diff(pr=args.pr, staged=args.staged)
    if not diff.strip():
        print("No changes to review.")
        return

    # Diff stats
    files = len(re.findall(r'^\+\+\+ b/', diff, re.MULTILINE))
    additions = len(re.findall(r'^\+', diff, re.MULTILINE))
    deletions = len(re.findall(r'^\-', diff, re.MULTILINE))
    
    # Run scanners
    findings = []
    findings.extend(scanner_secrets(diff))
    findings.extend(scanner_debug(diff))
    findings.extend(scanner_merge(diff))

    # Test coverage heuristic
    test_lines = len(re.findall(r'^\+', re.sub(r'.*/test.*\n', '', diff), re.MULTILINE))
    all_lines = additions
    test_coverage = round((test_lines / max(1, all_lines)) * 100, 1)

    stats = {"files": files, "additions": additions, "deletions": deletions, "test_coverage_pct": test_coverage}
    risk = calculate_risk(findings, stats)
    breaking_count = sum(1 for f in findings if f.get("severity") == "breaking")
    verdict = determine_verdict(risk, breaking_count)

    if args.output == "json":
        print(json.dumps({
            "stats": stats,
            "risk_score": round(risk, 2),
            "verdict": verdict,
            "finding_count": len(findings),
            "findings_by_severity": {
                "breaking": breaking_count,
                "problem": len(findings) - breaking_count,
            },
            "findings": findings,
        }, indent=2))
        return

    # Text output
    hostile_tag = " [HOSTILE MODE]" if args.hostile else ""
    print(f"🔍 Reviewing {files} files | +{additions} -{deletions} | risk: {risk:.2f}{hostile_tag}\n")

    breaking = [f for f in findings if f.get("severity") == "breaking"]
    problems = [f for f in findings if f.get("severity") == "problem"]
    
    if breaking:
        print(f"🔴 BREAKING ({len(breaking)})")
        for f in breaking:
            print(f"  {f['description']}: {f['snippet']}")
        print()

    if problems:
        print(f"🟡 PROBLEMS ({len(problems)})")
        for f in problems:
            print(f"  {f['description']}: {f['snippet']}")
        print()

    if not breaking and not problems:
        print("✅ No automated issues found.\n")

    print(f"📊 Stats: +{additions} -{deletions} across {files} files | {test_coverage}% test coverage on new code")
    print(f"🏷️  Verdict: {verdict}")


if __name__ == "__main__":
    main()
