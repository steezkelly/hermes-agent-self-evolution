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