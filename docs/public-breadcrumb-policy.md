# Public Breadcrumb Policy

This project benefits from upstream and community work. When this fork solves a bug or produces a tested workaround, it is appropriate to leave a public breadcrumb where affected users are likely to look.

The goal is service, not promotion.

## When to comment upstream

Comment on an upstream issue or PR when all of these are true:

1. The fork has a fix, workaround, reproduction, or review note directly relevant to that thread.
2. The comment would save a reader time.
3. The comment includes evidence.
4. The comment is honest about whether the behavior is fork-local or upstream-compatible.

## What to include

A good breadcrumb includes:

- one sentence naming the exact bug or concern
- link to the relevant commit, branch, PR, doc, or issue
- verification command and result
- short caveat if the fix is fork-local
- no hype

Template:

```markdown
Status note for anyone hitting this issue:

This is fixed/worked around in the `steezkelly/hermes-agent-self-evolution` fork.

Relevant link:
- <commit-or-doc-url>

Verification:
- command: `<command>`
- result: `<result>`

Caveat: <fork-local/upstream-compatible/etc.>
```

## What not to do

Avoid:

- copy/pasting the same comment across many threads
- commenting on loosely related issues
- saying "use my fork" without a specific fix
- presenting fork experiments as upstream official behavior
- hiding uncertainty

## Comment priority

Highest priority:

1. issues where users are blocked by an install/runtime failure fixed in the fork
2. PRs where a review note can prevent merging a weaker fix
3. issues already referenced by fork fixes
4. stale umbrella issues where a concise status update connects scattered work

Low priority:

- old issues with no active users and no new evidence
- feature discussions where the fork only has speculative ideas

## Current breadcrumb links

- Upstream issue #47: working fork/install path and sklearn dependency fix
- Upstream issue #34: evolved_full validation fix status
- Upstream issue #11: validator body-vs-full-skill fix status
- Upstream PR #51: review note on validation fix and holdout exception caveat

See GitHub issue #7 in this fork for ongoing project-direction tracking.
