---
name: github-pr-review
description: Analyzes a GitHub pull request diff for bugs, security issues, and performance problems, then writes constructive inline comments via the GitHub API.
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Review a GitHub pull request thoroughly: analyze the diff for bugs, security issues, performance problems, and write constructive inline comments via the GitHub API"
      iterations_per_section: 1
      optimizer_model: "deepseek/deepseek-v4-pro"
      eval_model: "deepseek/deepseek-v4-flash"
      coherence_passed: true
      coherence_issues: "none"
      section_metrics:
        steps:
          exit_code: 0
          elapsed_seconds: 0.0
        pitfalls:
          exit_code: 0
          elapsed_seconds: 0.0
        examples:
          exit_code: 0
          elapsed_seconds: 0.0
        constraints:
          exit_code: 0
          elapsed_seconds: 0.0
        verification:
          exit_code: 0
          elapsed_seconds: 0.0
      total_elapsed_seconds: None
      timestamp: ""
---

# Github Pr Review

Analyzes a GitHub pull request diff for bugs, security issues, and performance problems, then writes constructive inline comments via the GitHub API.


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
- **Ignoring existing code style and project conventions**: (a) The AI proposes changes that conflict with the project’s linting rules, formatting, or naming conventions. (b) Such comments are less likely to be accepted, reducing the usefulness of the review and potentially degrading code quality if blindly applied. (c) Mitigation: Before commenting, fetch the project’s ESLint/Pylint/.editorconfig or similar configuration, and adhere to established style guidelines; if the PR already has style inconsistencies, note them only when egregious.
- **API misuse leading to incomplete or broken comments**: (a) The skill may exceed GitHub API rate limits, submit malformed comment payloads, or comment on outdated commit SHAs. (b) This results in failed reviews, partial feedback, or comments that point to lines that no longer exist. (c) Mitigation: Implement robust error handling with retries and exponential backoff; always target the latest commit SHA; batch comments to respect rate limits and use pagination for large diffs.
- **Premature performance suggestions**: (a) The AI recommends micro-optimizations (e.g., replacing loops with list comprehensions, caching trivial values) without evidence of actual performance bottlenecks. (b) These suggestions reduce code readability and may introduce subtle bugs, while providing negligible speed gains. (c) Mitigation: Only raise performance concerns when the diff contains obvious inefficiencies (e.g., O(n²) algorithms, repeated API calls in loops) or when profiling data is available; otherwise focus on correctness and clarity.
- **Failing to detect security-sensitive patterns (e.g., hardcoded secrets, injection vectors)**: (a) The AI overlooks hardcoded API keys, SQL injection risks, or unsafe deserialization because it treats them as regular code changes. (b) This leaves the codebase vulnerable to attacks that automated scanning should catch. (c) Mitigation: Integrate a dedicated secrets scanner (e.g., detect-secrets, truffleHog) and static analysis for injection flaws (e.g., Bandit, ESLint security rules) as pre-filters; flag any matched findings with high priority and never suggest inline secrets.

## Examples

**Example 1: Identifying a missing null check in TypeScript**  
**Input:** A pull request adds `getUserDisplayName(user: User | null): string` that directly accesses `user.name` without null validation.  
**Output/Result:** The skill posts an inline comment on the `user.name` line: “Consider handling the null case – `user?.name ?? 'Anonymous'` prevents a potential runtime error.” It also adds a PR summary comment: “Found 1 null safety issue: missing check in `getUserDisplayName`”.

**Example 2: Finding a SQL injection vulnerability in Node.js**  
**Input:** A PR includes an API route that builds a query with `SELECT * FROM users WHERE id = ${req.query.id}`.  
**Output/Result:** The skill posts an inline comment with severity **critical**: “Use parameterized queries (e.g., `?` placeholder) or an ORM to prevent SQL injection. See OWASP A03:2021.” A PR‑level comment adds: “1 security vulnerability detected – SQL injection in `/users/:id`.”

**Example 3: Spotting an N+1 query in Rails**  
**Input:** A view controller iterates `User.all.each { |u| u.orders.recent }`, causing a separate query per user.  
**Output/Result:** The skill comments on that line: “Eager load orders with `User.includes(:orders)` to eliminate N+1 – reduces database calls from O(N) to O(1).” A performance note is added to the PR: “N+1 query detected in `UsersController#index`.”

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
   - **Pass**: The agent’s inline comment correctly identifies the specific issue (e.g., points out the off-by-one or missing validation) and suggests a reasonable fix.  
   - **Fail**: The agent either does not comment on the bug, misidentifies the issue, or provides an irrelevant or incorrect recommendation.

2. **Test that irrelevant files are ignored**  
   - **Setup**: Create a PR that includes both code changes and a non‑code change (e.g., a `.gitignore` update, a documentation typo, or an image).  
   - **Pass**: The agent writes comments only on the code diff lines that have bugs, security concerns, or performance problems. No comment is placed for the non‑code file or for clean code lines.  
   - **Fail**: The agent comments on the non‑code file, comments on lines with no issues, or misses a genuine problem in the code.

