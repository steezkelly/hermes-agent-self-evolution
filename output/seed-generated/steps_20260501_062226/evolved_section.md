1. Parse the incoming natural language task description to identify core components: the task title, detailed description, implied priority level, relevant team, and any mentioned assignee.

2. Use the `hermes tool extract-entities` tool to structure the raw text and map identified elements to Linear's required fields (title, description, priority, team, assignee).

3. Validate that required fields are present. If title or description are missing, prompt the user for clarification. Set default priority to "Medium" if not explicitly stated.

4. Construct the GraphQL mutation for creating a Linear issue. Format the payload with all extracted fields mapped to Linear's `IssueCreateInput` schema.

5. Authenticate with the Linear API by retrieving stored credentials using `hermes auth get --service linear`. Verify the session is active before proceeding.

6. Execute the GraphQL mutation against the Linear API endpoint using `hermes call linear-api --mutation "issueCreate" --variables '<structured_payload>'`.

7. Parse the API response to confirm successful issue creation. Extract the new issue identifier and URL from the response payload.

8. Return confirmation to the user with the issue title, identifier, and direct link to the created Linear issue.