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