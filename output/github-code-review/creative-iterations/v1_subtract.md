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

# GitHub Code Review

## Essence

Code review is: **read the diff, find the bugs, report them.**

Everything else is ceremony. This skill strips to that core.

---

## The Only Three Steps

### 1. Get what changed

```bash
# Everything
git diff main...HEAD

# Just the names
git diff main...HEAD --name-only

# Specific area
git diff main...HEAD -- src/auth/
```

For a PR:
```bash
gh pr diff 123
# or
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER/files
```

### 2. Find problems

Hit these five categories, fast:

| Check | Command |
|-------|---------|
| Security holes | `git diff main...HEAD \| grep -in "password\|token.*=\|api_key"` |
| Debug leftovers | `git diff main...HEAD \| grep -in "print(\|console.log\|TODO\|FIXME\|debugger"` |
| Merge conflicts | `git diff main...HEAD \| grep -n "<<<<<<\|>>>>>>"` |
| Bloat | `git diff main...HEAD --stat \| sort -k2 -rn \| head -5` |
| Logic errors | Read the actual diff with read_file for context |

### 3. Report

```
## CRITICAL
- path/to/file.py:42 — SQL injection, raw query

## WARNINGS
- path/to/file.py:88 — missing null check

## SUGGESTIONS
- path/to/test.py:10 — add edge case test

## OK
- Clean separation, good naming
```

That's it. If the diff is clean, say so.
