---
name: github-pr-review
description: Analyzes a GitHub pull request diff for bugs, security issues, and performance problems, then writes constructive inline comments via the GitHub API.
version: 0.2.0-seed-expanded
metadata:
  hermes:
    tags: [github, code-review, security, performance, static-analysis]
    generation:
      seed: "Review a GitHub pull request thoroughly: analyze the diff for bugs, security issues, performance problems, and write constructive inline comments via the GitHub API"
      method: seed-to-skill with GEPA validation
      optimizer_model: "minimax/minimax-m2.7"
      eval_model: "minimax/minimax-m2.7"
      section_metrics:
        overview: { iterations: 2, exit_code: 0 }
        when-to-use: { iterations: 2, exit_code: 0 }
        troubleshooting: { iterations: 2, exit_code: 0 }
        variants: { iterations: 2, exit_code: 0 }
        related-skills: { iterations: 2, exit_code: 0 }
      baseline_sections: [steps, pitfalls, examples, constraints, verification]
      new_sections: [overview, when-to-use, troubleshooting, variants, related-skills]
---

# Github Pr Review

Analyzes a GitHub pull request diff for bugs, security issues, and performance problems, then writes constructive inline comments via the GitHub API.


## Overview

This skill performs comprehensive GitHub pull request reviews by analyzing code changes for bugs, security vulnerabilities, performance issues, and code quality problems. It reads the PR description, examines the diff, and identifies specific lines of code that need attention. The reviewer produces inline comments on the PR via the GitHub API, targeting exact line numbers with actionable feedback. The skill systematically checks common bug patterns (null pointer issues, race conditions, error handling gaps), security risks (injection vulnerabilities, exposed secrets, improper authentication), and performance concerns (N+1 queries, inefficient algorithms, missing caching). Output consists of constructive technical feedback attached directly to the pull request, organized by file and line, enabling developers to address issues before merging.


## When to Use

**When to apply the PR Review skill**

**Typical triggers (use this skill when these conditions are true)**
- A pull request has been opened or updated and the team expects a thorough, multi‑dimensional review (correctness, security, performance, maintainability) with constructive inline comments posted via the GitHub API.
- The PR modifies security‑sensitive code (e.g., authentication, authorization, data validation, payment processing) or introduces a new external dependency, warranting a dedicated security analysis.
- The changes affect performance‑critical paths such as database queries, heavy loops, caching layers, or algorithmic logic, and a performance review is needed before merging.
- The CI pipeline reports failures on complex test cases, and the reviewer wants to add targeted inline guidance for the author to resolve the issues.
- The PR alters an API contract, data transformation, or integration point where correctness and backward‑compatibility must be verified manually.

**Situations where this skill is NOT appropriate (and what to do instead)**
- The pull request contains only trivial changes (e.g., formatting, typo fixes, comment updates) that can be reviewed quickly or approved without deep analysis – use a lightweight review or a direct approval instead.
- The PR is still in Draft or "Work‑in‑Progress" state and the author has not yet requested a formal review – wait until the author marks it ready or remove the draft flag before invoking the review skill.
- You lack the necessary GitHub credentials (no personal‑access‑token or GitHub App token with `repo` or `write:discussion` scope) or you do not have permission to read the repository and post comments – obtain the proper authentication first.

**Prerequisites / preconditions before invoking the skill**
1. **Authenticated GitHub session** – The agent must possess a GitHub token (personal access token or installation token) with at least read access to the repository and write access to PR discussions (`repo` or `write:discussion` scope).
2. **Existing, accessible pull request** – The PR must be in an open, draft, or closed‑but‑unmerged state. Commenting is not supported on already‑merged or deleted PRs.
3. **Retrievable diff** – The diff size must be within GitHub API limits for a single request (typically <10 k lines). For very large diffs, split the review into multiple calls or pre‑process the diff externally before invoking the skill.
4. **Familiarity with codebase norms** – The agent should have access to or knowledge of the repository's coding standards, security guidelines, and performance benchmarks to evaluate the changes accurately.


## Steps

1. Retrieve the pull request details and diff using the GitHub API. Use `http_request` to GET the pull request endpoint (`https://api.github.com/repos/{owner}/{repo}/pulls/{number}`) and the files endpoint (`/pulls/{number}/files`) to obtain the diff.
2. Parse the diff to identify changed files and line-level changes. Extract file paths and the patch (diff) content from the API response.
3. For each changed file, run static analysis tools via `run_shell` to detect potential bugs, security vulnerabilities, and style issues. For example, execute `run_shell('pylint {file_path}')` or `run_shell('bandit -r {file_path}')`.
4. Manually inspect the diff for subtle logic errors, missing edge cases, insecure practices (e.g., SQL injection, XSS), and performance concerns (e.g., repeated database calls, large object creation).
5. For each issue found, construct an inline comment by sending a `POST` request to `/repos/{owner}/{repo}/pulls/{number}/comments` with the comment body, file path, commit SHA, and line number. Use the `http_request` tool.
6. After all inline comments, create an overall review by posting to `/repos/{owner}/{repo}/pulls/{number}/reviews` with a summary comment and the event set to `COMMENT`. This wraps the individual comments into a formal review.
7. Ensure all comments are constructive, specific, and offer actionable suggestions. Include proposed code improvements when applicable.
8. Handle pagination if the PR contains many files or comments: loop through `next` links in the API response headers to retrieve all pages.
9. Log each step and the HTTP responses for traceability using Hermes logging.
10. Verify that the review was submitted successfully by checking the API response status codes (e.g., 201 for comments, 200 for review creation).


## Pitfalls

- **Over-reliance on pattern matching without context**: (a) The AI may flag code as buggy or insecure based on surface-level patterns, missing actual domain logic or project-specific conventions. (b) This produces false positives that waste reviewer time or false negatives that let real issues slip. (c) Mitigation: Always cross-reference findings with any available documentation, configuration files, or previous PR discussions; limit automated suggestions to well-defined, low-risk patterns and require human verification for critical categories like security.
- **Ignoring existing code style and project conventions**: (a) The AI proposes changes that conflict with the project's linting rules, formatting, or naming conventions. (b) Such comments are less likely to be accepted, reducing the usefulness of the review and potentially degrading code quality if blindly applied. (c) Mitigation: Before commenting, fetch the project's ESLint/Pylint/.editorconfig or similar configuration, and adhere to established style guidelines; if the PR already has style inconsistencies, note them only when egregious.
- **API misuse leading to incomplete or broken comments**: (a) The skill may exceed GitHub API rate limits, submit malformed comment payloads, or comment on outdated commit SHAs. (b) This results in failed reviews, partial feedback, or comments that point to lines that no longer exist. (c) Mitigation: Implement robust error handling with retries and exponential backoff; always target the latest commit SHA; batch comments to respect rate limits and use pagination for large diffs.
- **Premature performance suggestions**: (a) The AI recommends micro-optimizations (e.g., replacing loops with list comprehensions, caching trivial values) without evidence of actual performance bottlenecks. (b) These suggestions reduce code readability and may introduce subtle bugs, while providing negligible speed gains. (c) Mitigation: Only raise performance concerns when the diff contains obvious inefficiencies (e.g., O(n²) algorithms, repeated API calls in loops) or when profiling data is available; otherwise focus on correctness and clarity.
- **Failing to detect security-sensitive patterns (e.g., hardcoded secrets, injection vectors)**: (a) The AI overlooks hardcoded API keys, SQL injection risks, or unsafe deserialization because it treats them as regular code changes. (b) This leaves the codebase vulnerable to attacks that automated scanning should catch. (c) Mitigation: Integrate a dedicated secrets scanner (e.g., detect-secrets, truffleHog) and static analysis for injection flaws (e.g., Bandit, ESLint security rules) as pre-filters; flag any matched findings with high priority and never suggest inline secrets.


## Examples

**Example 1: Identifying a missing null check in TypeScript**
**Input:** A pull request adds `getUserDisplayName(user: User | null): string` that directly accesses `user.name` without null validation.
**Output/Result:** The skill posts an inline comment on the `user.name` line: "Consider handling the null case – `user?.name ?? 'Anonymous'` prevents a potential runtime error." It also adds a PR summary comment: "Found 1 null safety issue: missing check in `getUserDisplayName`".

**Example 2: Finding a SQL injection vulnerability in Node.js**
**Input:** A PR includes an API route that builds a query with `SELECT * FROM users WHERE id = ${req.query.id}`.
**Output/Result:** The skill posts an inline comment with severity **critical**: "Use parameterized queries (e.g., `?` placeholder) or an ORM to prevent SQL injection. See OWASP A03:2021." A PR‑level comment adds: "1 security vulnerability detected – SQL injection in `/users/:id`."

**Example 3: Spotting an N+1 query in Rails**
**Input:** A view controller iterates `User.all.each { |u| u.orders.recent }`, causing a separate query per user.
**Output/Result:** The skill comments on that line: "Eager load orders with `User.includes(:orders)` to eliminate N+1 – reduces database calls from O(N) to O(1)." A performance note is added to the PR: "N+1 query detected in `UsersController#index`."


## Constraints

- Do analyze every file in the pull request diff, not just the summary or title.
- Do comment on each identified issue inline using the GitHub API, referencing the exact line and file affected.
- Don't leave vague comments; each comment must explain the problem, its potential impact, and a concrete suggestion for improvement.
- Don't comment on trivial stylistic preferences unless they are directly related to bugs, security, or performance.
- Don't approve or merge the pull request unless explicitly authorized by the user.
- Do respect the repository's existing coding style and conventions unless they introduce a security or performance risk.
- Don't use any credentials or API tokens directly in the code; rely on environment variables or secure secrets management.
- Do limit comments to actionable feedback; avoid subjective or opinion-based remarks.
- Don't reveal any sensitive information (e.g., passwords, API keys) in comments, even if present in the diff.
- Do verify that your suggestions are constructive and encourage improvement; never use harsh or disrespectful language.


## Verification

To verify the correctness of this skill, perform the following lightweight checks:

1. **Test with a known buggy PR**
   - **Setup**: Supply a small, targeted pull request (e.g., a deliberate off-by-one error or missing input sanitization) on a public or test repository where the agent has write access.
   - **Pass**: The agent's inline comment correctly identifies the specific issue (e.g., points out the off-by-one or missing validation) and suggests a reasonable fix.
   - **Fail**: The agent either does not comment on the bug, misidentifies the issue, or provides an irrelevant or incorrect recommendation.

2. **Test that irrelevant files are ignored**
   - **Setup**: Create a PR that includes both code changes and a non‑code change (e.g., a `.gitignore` update, a documentation typo, or an image).
   - **Pass**: The agent writes comments only on the code diff lines that have bugs, security concerns, or performance problems. No comment is placed for the non‑code file or for clean code lines.
   - **Fail**: The agent comments on the non‑code file, comments on lines with no issues, or misses a genuine problem in the code.


## Troubleshooting

- **GitHub API authentication fails or returns 401/403 errors**
  - *Cause*: Invalid, expired, or insufficient GitHub token with wrong scopes. The token needs `repo` scope for private repos or `public_repo` for public repos.
  - *Recovery*: Verify the token has the correct scopes, regenerate it if expired, and ensure `GITHUB_TOKEN` environment variable is properly set. For GitHub Apps authentication, confirm the app installation has appropriate repository permissions.

- **API rate limiting (403 errors with "rate limit exceeded")**
  - *Cause*: Exceeding GitHub's API rate limits (5,000 requests/hour for authenticated requests). Large diffs or frequent polling trigger this quickly.
  - *Recovery*: Implement exponential backoff in retry logic, reduce analysis frequency, or request a higher rate limit by authenticating via a GitHub App instead of personal tokens. Cache previously fetched PR data to minimize redundant API calls.

- **Inline comments fail to post on specific lines or files**
  - *Cause*: Attempting to comment on lines that were modified in subsequent commits, or on files that were renamed/deleted. GitHub's diff view anchors become invalid.
  - *Recovery*: Use the `position` parameter with the correct commit SHA rather than line numbers when commenting, or fetch the latest diff before posting. For renamed files, identify them by their new path and adjust comments accordingly.

- **Pull request diff is empty, truncated, or fails to load**
  - *Cause*: The PR contains only merge commits, is a draft with no visible changes, or the base branch lacks accessibility. Binary files (images, compiled assets) are included without text conversion.
  - *Recovery*: Use `?diff=unified` or `?diff=split` query parameters, filter out binary file patterns, and verify the PR author has pushed changes to the head branch. Check if the PR is in draft state and handle accordingly.

- **Duplicate or conflicting comments appear on the same line**
  - *Cause*: Running the review agent multiple times without clearing previous comments, or race conditions when posting multiple comments simultaneously via the API.
  - *Recovery*: Track posted comment IDs and skip duplicates, or use the `DELETE /repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}` endpoint to clean up before re-running. Implement idempotent comment posting by checking existing comments before creating new ones.

- **Known gotcha: Comment threading behavior**
  - GitHub creates new threads for each file/line combination. Replying to an existing thread requires the `reply` endpoint, not the standard `create` endpoint. Failing to account for this results in orphaned comments or notification chaos.

- **Known gotcha: Security review limitations**
  - Static analysis of diffs cannot detect runtime vulnerabilities, environment-specific issues, or dependency confusion attacks. Flagged "issues" may be intentional configuration or false positives in generated code. Always recommend human security expert review for high-stakes changes.


## Variants

There are three primary variants for PR review that focus on different concerns:

**1. Security-Focused Review**
This variant prioritizes scanning for vulnerabilities, hardcoded secrets, injection risks, and dependency issues. It applies a threat-modeling lens to all changed code.
- **When to use**: Reviews of PRs touching authentication, payment processing, user data handling, or external API integrations.
- **Trade-offs**: May be overly cautious for internal utility code; can increase review time due to deeper dependency analysis.

**2. Performance-Focused Review**
This variant examines algorithmic efficiency, N+1 query patterns, missing indexes, unoptimized loops, and caching opportunities in the diff.
- **When to use**: PRs introducing new database queries, data processing pipelines, or high-traffic endpoints.
- **Trade-offs**: Requires domain context about expected data volumes; may miss functional bugs while focusing on optimization.

**3. Quick Triage Review**
This variant performs a lightweight pass to identify obvious blockers, contract violations, or breaking changes without deep analysis.
- **When to use**: Time-sensitive PRs, large refactors needing preliminary approval, or when assigning a specialist reviewer.
- **Trade-offs**: Lower detection rate for subtle issues; should not replace thorough review for critical paths.

The base approach (full-spectrum review) remains the default for most PRs, while variants serve as targeted specializations for high-risk areas or constrained timeboxes.


## Related Skills

- **Automated Static Analysis Integration** – Leverages linters and static‑analysis tools to automatically surface potential bugs, code smells, and style violations, giving you a baseline of quality before you dive into manual review.
- **Security Vulnerability Scanning** – Focuses on identifying known CVEs in dependencies, secret leaks, and insecure coding patterns, complementing the PR review by adding a deep‑dive security lens.
- **Performance Profiling and Benchmarking** – Detects algorithmic inefficiencies, memory bloat, and latency regressions, allowing you to comment on performance concerns alongside functional ones.
- **CI/CD Pipeline Monitoring** – Provides real‑time visibility into build status, test coverage, and deployment checks, ensuring you only spend time on PRs that have passed foundational CI gates.
- **Issue and Pull‑Request Triage** – Prioritizes reviews based on linked issues, labels, and project milestones, helping you allocate effort where it matters most.

**Suggested learning order**
1. **CI/CD Pipeline Monitoring** – Understand the overall health of the branch and what automated checks are in place.
2. **Automated Static Analysis Integration** – Learn how to run and interpret static‑analysis results that feed into CI.
3. **Security Vulnerability Scanning** – Build on static analysis to add security‑focused checks.
4. **Performance Profiling and Benchmarking** – Add a performance perspective after security basics are solid.
5. **Issue and Pull‑Request Triage** – Tie it all together by learning how to prioritize and scope reviews based on impact and project context.
