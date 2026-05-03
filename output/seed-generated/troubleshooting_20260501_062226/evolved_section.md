- **If the skill returns an "Invalid API key" error**, the Linear API key may be expired, revoked, or misconfigured. Check that the `LINEAR_API_KEY` environment variable contains a valid personal API key from your Linear workspace settings. Regenerate the key if necessary at Linear Settings → API → Personal API Keys.

- **If issue creation fails with "Team not found" or "Assignee not found"**, the skill is referencing a team ID or user ID that doesn't exist in your Linear workspace. Verify the exact spelling and casing of team and assignee names. Use team identifiers (e.g., `eng`, `design`) from your Linear workspace rather than full team names.

- **If priority is always set to "No priority" despite user intent**, the natural language priority (e.g., "urgent", "high priority") may not map cleanly to Linear's numeric scale (0-4). When in doubt, explicitly specify priority as `urgent` (maps to 0), `high` (maps to 1), `medium` (maps to 2), or `low` (maps to 3).

- **If you're hitting rate limits (429 errors)**, the skill is making rapid successive GraphQL requests. Build a 2-3 second delay between issue creation calls, or batch multiple related issues into a single request if your workflow allows it. Check the `X-RateLimit-Remaining` header in responses to monitor quota.

- **If the extracted title is empty or truncated**, the natural language input may lack a clear imperative statement or subject. Ensure your input begins with a clear task description (e.g., "Fix login bug" rather than "The login bug that needs fixing"). Titles exceeding 255 characters will be silently truncated.

- **If required fields are missing in the created issue**, Linear's schema requires a `teamId` for all issues. If no team is specified in the input, the skill defaults to the workspace's primary team. Always include a team reference to avoid creating issues in unexpected locations.

- **If assignee mention doesn't resolve to a user**, Linear requires exact email or user ID matches for assignees. Mentions like "@john" or partial names won't resolve. Use the user's full email address or their Linear user ID (e.g., `user_id: "abc123"`) for reliable assignment.