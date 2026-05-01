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

## Why

Bad code goes to prod. Good review catches it. This skill is the filter.

The user isn't asking for a rubber stamp. They're asking for the things they missed — the null pointer they didn't see, the credential they left in a debug line, the refactor that silently changes behavior. A review that finds nothing found nothing.

---

## How to Review

### Stage 1: Orient

Get the shape of the change before reading any code.

```bash
# Local
git diff main...HEAD --stat     # files and line counts
git log main..HEAD --oneline    # what the commits say they do

# PR
gh pr view 123 --json title,body,files,additions,deletions
# or
curl -s https://api.github.com/repos/$OWNER/$REPO/pulls/$PR_NUMBER | jq '{title, state, additions, deletions, changed_files}'
```

**Ask yourself:** Is this small and focused, or is it a multi-brain dump? Large PRs hide more bugs per line than small ones. Adjust scrutiny accordingly.

### Stage 2: Scan for landmines

These are the things that cause production incidents. Hit them before reading for quality.

```bash
# Pattern 1 — secrets left in code
git diff main...HEAD | grep -Ein "(password|secret|api.?key|token|credential)\s*[=:]\s*['\"][^'\"]+"

# Pattern 2 — dead code / debug artifacts  
git diff main...HEAD | grep -Ein "(TODO|FIXME|HACK|XXX|debugger|console\.log|print\(|pprint|var_dump|dd\()"

# Pattern 3 — merge conflicts (someone didn't resolve properly)
git diff main...HEAD | grep -Ein "(<{7}|>{7}|={7})"

# Pattern 4 — silent catches (bugs hiding behind empty except)
git diff main...HEAD | grep -Ein "except\s*:" | grep -v "pass\|log\|raise"

# Pattern 5 — hardcoded config (env-specific paths, URLs, ports)
git diff main...HEAD | grep -Ein "(localhost|127\.0\.0\.1|:3000|:8080|password=|--password)"
```

### Stage 3: Read for correctness

This is where the real work happens. You read the diff with read_file for context.

For each file that changed:
1. Read the full file (not just the diff) — bugs hide in lines that didn't change
2. Trace the logic: what are the inputs, what are the outputs, is there any path where data is lost or corrupted
3. Check edge cases: empty collections, null values, boundary conditions, concurrent access
4. Check the tests: do the tests actually test the right thing, or do they test the implementation?

**Steve's specific concern:** Does this PR overwrite or conflict with local-only changes? Your fork may have fixes that upstream doesn't. A PR that "fixes" something already fixed locally is a regression.

### Stage 4: Quality & performance

| Signal | What to look for |
|--------|-----------------|
| Naming | Is `temp`, `data`, `result` doing too much? |
| Duplication | Does this reimplement something that exists? |
| Scope | Are variables scoped tighter than they need to be? |
| Coupling | Does this change touch things it shouldn't? |
| Performance | N+1 queries, blocking calls in loops, O(n²) in hot paths |
| Async | Missing awaits, unhandled promise rejections, no timeout |

### Stage 5: Report

**Three buckets, no filler:**

**🔴 BREAKING** — will cause incorrect behavior, data loss, or a security incident. Must be fixed before merge.

**🟡 PROBLEMS** — should be fixed for quality, but won't cause immediate failure. Technical debt being introduced.

**🟢 SUGGESTIONS** — nice-to-haves. Edge cases to add, comments to clarify, patterns to consider.

If everything is clean: **"LGTM. [Number] files changed, [N] insertions, [N] deletions. No issues found."**

---

## PR Review End-to-End

```bash
# 1. Set up
REMOTE_URL=$(git remote get-url origin)
OWNER=$(echo "$REMOTE_URL" | sed 's|.*github.com[:/]||; s|/.*||')
REPO=$(echo "$REMOTE_URL" | sed 's|.*/||; s|\.git||')

# 2. Get the PR  
gh pr diff $1 | head -200  # quick scan
gh pr view $1 --json title,body,files,additions,deletions

# 3. Check out locally for real review
git fetch origin pull/$1/head:review-$1 && git checkout review-$1
git diff main...HEAD --stat

# 4. Run the scans (from Stage 2 above)

# 5. Read key files with read_file for full context

# 6. Post results — back to main when done
git checkout main && git branch -D review-$1
```

For submitting feedback, use gh:
```bash
gh pr review $1 --request-changes --body "$(cat)"
# or --approve / --comment
```
