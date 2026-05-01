1. Receive the natural language task description as input.
2. Parse the description to extract the required fields: title, description, priority (e.g., urgent, high, medium, low), team (name or ID), and assignee (email or ID). Use an LLM to reliably extract structured data if needed.
3. If any field is missing, infer reasonable defaults (e.g., priority=medium) or ask the user for clarification.
4. Map the extracted values to Linear’s GraphQL schema: `title`, `description`, `priority` (as integer: 0=urgent, 1=high, 2=medium, 3=low), `teamId`, and `assigneeId` (or `assigneeEmail`).
5. Construct a GraphQL mutation string for issue creation. For example:
   ```graphql
   mutation {
     issueCreate(input: {
       title: "Extracted title",
       description: "Extracted description",
       priority: 2,
       teamId: "team-uuid",
       assigneeId: "user-uuid"
     }) {
       issue {
         id
         title
         url
       }
     }
   }
   ```
6. Execute the mutation using the Hermes CLI tool:
   `hermes api linear graphql --mutation '<mutation_string>'`
7. Capture the JSON response and check for errors. If the mutation fails, retry with corrected values or alert the user.
8. Parse the successful response to extract the created issue’s ID, title, and URL.
9. Return a confirmation message to the user, including the Linear issue link.