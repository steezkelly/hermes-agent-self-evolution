- **What goes wrong:** Not fetching the complete diff due to pagination limits or oversized PRs.  
  **Why it matters:** Critical changes can be missed, leading to undetected bugs, security issues, or performance problems.  
  **Mitigation/Check:** Implement pagination logic (e.g., `page`/`per_page` parameters) and ensure all changed files are retrieved before analysis.

- **What goes wrong:** Ignoring the PR description and linked issues, resulting in lack of context.  
  **Why it matters:** Without understanding the intent, comments may misidentify problems or propose irrelevant improvements.  
  **Mitigation/Check:** Always fetch the PR title, description, and any linked tickets or documents at the start of the review.

- **What goes wrong:** Overlooking binary or non‑text file changes (e.g., images, compiled assets).  
  **Why it matters:** Security vulnerabilities or performance regressions hidden in binary updates can be missed.  
  **Mitigation/Check:** Flag the presence of binary files and comment on the need for version updates or security scans.

- **What goes wrong:** Missing known security anti‑patterns (e.g., unsafe deserialization, hard‑coded secrets).  
  **Why it matters:** Exploitable vulnerabilities may be shipped to production, compromising the system.  
  **Mitigation/Check:** Combine static analysis tool output with manual inspection of high‑risk patterns; reference secure coding guidelines in comments.

- **What goes wrong:** Flagging code as a performance bottleneck without concrete evidence (e.g., missing profiling data).  
  **Why it matters:** Irrelevant performance remarks waste developer time and can erode trust in the review.  
  **Mitigation/Check:** Base performance comments on algorithmic complexity analysis, known slow patterns, or existing benchmark results.

- **What goes wrong:** Writing vague or non‑constructive comments (“This looks bad”, “Why is this here?”).  
  **Why it matters:** Reviewers receive no actionable guidance, leading to confusion and delayed fixes.  
  **Mitigation/Check:** Follow a comment template: describe the issue, explain its impact, and suggest a concrete alternative or reference to best practices.

- **What goes wrong:** Posting comments on outdated lines after a force‑push or rebased branch.  
  **Why it matters:** Comments appear on unrelated code, creating noise and misdirecting discussion.  
  **Mitigation/Check:** Re‑fetch the latest diff immediately before posting comments and verify line numbers match the current commit.

- **What goes wrong:** Exceeding GitHub API rate limits while posting many comments or retrieving large diffs.  
  **Why it matters:** Review process stalls; comments may be dropped, leaving issues unaddressed.  
  **Mitigation/Check:** Implement exponential backoff, batch comments where possible, and monitor `X‑RateLimit‑Remaining` headers.

- **What goes wrong:** Sending duplicate comments because the review script runs multiple times without tracking state.  
  **Why it matters:** Duplicates create clutter, confuse authors, and may be misinterpreted as repeated concerns.  
  **Mitigation/Check:** Maintain a list of already‑posted comment IDs and skip re‑posting for the same line/text.

- **What goes wrong:** Failing to verify test coverage for newly added code.  
  **Why it matters:** Missing tests increase the risk of regressions and uncovered edge cases.  
  **Mitigation/Check:** Check for new test files, ensure CI includes relevant test runs, and comment on any gaps.

- **What goes wrong:** Overlooking secret or sensitive data accidentally committed in the diff.  
  **Why it matters:** Credentials or PII exposed in the repository can lead to security breaches.  
  **Mitigation/Check:** Scan diff for common secret patterns (API keys, tokens) and immediately flag for removal.

- **What goes wrong:** Ignoring backward‑compatibility impacts of API or schema changes.  
  **Why it matters:** Consumers of the API may break unexpectedly, causing production incidents.  
  **Mitigation/Check:** Review API modification comments and note any required version bumps or migration steps.

- **What goes wrong:** Relying solely on automated tools without manual validation of logical errors.  
  **Why it matters:** Tools can miss business‑logic bugs or context‑specific issues that require human understanding.  
  **Mitigation/Check:** Use automated scans for initial triage, then follow up with a focused manual review of logic‑critical sections.

- **What goes wrong:** Not confirming that CI/CD pipelines have actually run on the PR.  
  **Why it matters:** Unverified code may pass review but fail in CI, delaying deployment and causing build issues.  
  **Mitigation/Check:** Verify that all status checks are present and passing before approving; comment if checks are missing.