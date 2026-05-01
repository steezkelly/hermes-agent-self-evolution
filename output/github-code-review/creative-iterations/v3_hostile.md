---
name: github-code-review
description: "Review PRs: diffs, inline comments via gh or REST."
version: 1.2.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [GitHub, Code-Review, Pull-Requests, Git, Quality]
    related_skills: [github-auth, github-pr-workflow]
---

# GitHub Code Review — Hostile Mode

> **Toggle:** Run with `REVIEW_MODE=hostile` to activate. Default is standard.
>
> Hostile mode assumes every PR is guilty until proven innocent. It doesn't trust the author. It doesn't trust the tests. It trusts the diff and the diff alone.

## Core Principle

Every changed line is a liability until verified. The default assumption is that the PR introduces bugs, regressions, or tech debt. The author must prove otherwise.

---

## Hostile Review Checklist

### 1. The "Why" Check

Before reading code, reject any PR that doesn't answer:
- What problem does this solve?
- Why solve it this way?
- What was wrong with the old way?

If the PR description is vague or missing, flag it **immediately**. A PR the author can't explain is a PR that shouldn't exist.

```bash
gh pr view 123 --json title,body | jq -r '.body' | head -20
```
If `body` is empty or contains only "Fixes #X": **"PR description does not explain motivation or approach. Requesting author to document intent before review."**

### 2. The "I Don't Trust You" Scan

Run every check. Assume the author made every mistake in the book.

```bash
# Maximum severity scan
issues=0

# Hardcoded secrets — not just "check for them," assume they're there
secrets=$(git diff main...HEAD | grep -cEin "(password|secret|api.?key|token|credential)\s*[=:]")
if [ "$secrets" -gt 0 ]; then
  echo "🔴 BREAKING: Found $secrets potential credential leaks. PR blocked."
  issues=$((issues + 1))
fi

# Test coverage — did they add tests for their own changes?
added_lines=$(git diff main...HEAD | grep "^+" | grep -v "^+++" | wc -l)
test_lines=$(git diff main...HEAD -- "**/test*" "**/*_test*" "**/spec*" | grep "^+" | grep -v "^+++" | wc -l)
test_ratio=$(echo "scale=2; $test_lines / $added_lines * 100" | bc 2>/dev/null || echo "0")
if [ "$(echo "$test_ratio < 10" | bc)" -eq 1 ]; then
  echo "🔴 BREAKING: Test ratio ${test_ratio}% — untested code is broken code."
  issues=$((issues + 1))
fi

# File count — large PRs are cockroach hotels for bugs
file_count=$(git diff main...HEAD --name-only | wc -l)
if [ "$file_count" -gt 20 ]; then
  echo "🟡 PROBLEMS: ${file_count} files changed. Large PRs hide bugs. Consider splitting."
  issues=$((issues + 1))
fi

# Deletions — did they actually delete code or just add?
del=$(git diff main...HEAD --stat | tail -1 | grep -oP '\d+ deletions' | grep -oP '\d+')
add=$(git diff main...HEAD --stat | tail -1 | grep -oP '\d+ insertions' | grep -oP '\d+')
if [ "$del" -lt "$((add / 10))" ] 2>/dev/null; then
  echo "🟡 PROBLEMS: Mostly additions (${add}+, ${del}-). Refactoring should delete as much as it adds."
fi

echo "Found $issues blocking issues."
```

### 3. Logic Review (Hostile)

Read every changed file with the assumption that the author made at least one logic error per 50 lines. Find them.

**Look for:**
- Silent data loss — error paths that swallow exceptions and return nil
- State corruption — shared mutable state modified without synchronization
- Off-by-one — loops that miss the first or last element
- Type confusion — mixing int/str/bool in comparisons
- Race windows — check-then-act patterns without locks
- Copy-paste drift — similar blocks that differ in subtle ways (usually a bug copy)
- Time-of-check/time-of-use — checking a condition then acting on stale data
- Implicit assumptions — "this will never be None because..." (it will)

**When you find one, don't just flag it. Explain what breaks:**

> 🔴 BREAKING — `src/processor.py:45`: `items.pop(0)` modifies the list in-place while iterating. Every other element is skipped. This will produce silent data corruption on any input with more than 3 items. Reproduce with: `process([1,2,3,4])` → returns `[2,4]` instead of `[1,2,3,4]`.

### 4. The Regression Check (Steve Special)

This is the most important check in hostile mode. Your local fork may have fixes that the PR author doesn't know about.

```bash
# Has the same file been touched in your local branch?
git log --oneline --all -- src/changed-file.py | head -5
git diff main...HEAD -- src/changed-file.py | head -30

# If yes, compare what the PR does vs what you did
echo "This file was modified locally. Checking for conflicts..."
```

If the PR overwrites a local fix: **"🔴 BREAKING — This PR replaces a working local fix with a different approach. Need to reconcile before merge."**

### 5. Report Format (Hostile)

```
## 🔴 BREAKING (must fix)
N findings that will cause production issues.

## 🟡 PROBLEMS
N findings that degrade quality.

## 🟢 SUGGESTIONS
N nice-to-haves.

## ✅ SURVIVED
What survived hostile mode scrutiny.
```

In hostile mode, the default verdict is REQUEST CHANGES. Only approve if zero `🔴` findings and fewer than three `🟡` findings that the author addressed.

---

## Switch to Normal Mode

Unset the env var:
```bash
unset REVIEW_MODE
# or
REVIEW_MODE=normal hermes review ...
```
