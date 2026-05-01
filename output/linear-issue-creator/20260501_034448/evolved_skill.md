---
name: linear-issue-creator
description: Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API"
      iterations_per_section: 1
      optimizer_model: "deepseek/deepseek-v4-pro"
      eval_model: "deepseek/deepseek-v4-flash"
      coherence_passed: false
      coherence_issues: "1. **Contradictory priority mapping**: In `steps` section 4, the mapping is `0=urgent, 1=high, 2=medium, 3=low`. In `constraints`, the mapping is `1=urgent, 2=high, 3=medium, 4=low, 5=no priority`. Th"
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
      timestamp: "20260501_030958"
---

# Convert Natural Language Task Descriptio

Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API

## Steps

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

## Pitfalls

- **Ambiguous or incomplete task descriptions**: The agent might attempt to parse vague input like "fix login" without enough context. This can result in a poorly defined issue that the team cannot action.  
  *Mitigation*: Before calling the API, require the agent to extract at least a title and a description—if either is missing or too short, prompt the user for clarification or use a fallback template.

- **Mis-mapping priority and team fields**: Raw text may mention "urgent" or "backend", but these might not correspond to existing priority levels (e.g., P0–P3) or team labels in Linear.  
  *Why it matters*: Incorrect mappings can misroute work or set unrealistic expectations.  
  *Mitigation*: Maintain a lookup table in configuration and validate the extracted values against it; if a match fails, default to a safe value (e.g., P3) and log a warning.

- **Failing to validate assignee availability**: The skill might set an assignee based on name or username without checking if that user exists in the Linear workspace or has the right permissions.  
  *Why it matters*: An invalid assignee causes the API call to fail or silently drop the field.  
  *Mitigation*: Before creating the issue, query the Linear API to verify the user ID exists; if not, leave the field empty and notify the user.

- **Not handling API rate limits or transient errors**: The Linear GraphQL API can throttle requests or return intermittent failures.  
  *Why it matters*: A failed creation means the issue is lost without user awareness, reducing trust in the skill.  
  *Mitigation*: Implement retry logic with exponential backoff (up to 3 attempts) and surface a clear error message if all retries fail.

- **Accidentally overwriting existing fields when updating**: If the skill is also used to modify issues (e.g., change priority), it might overwrite other fields like description or labels with blanks.  
  *Why it matters*: This destroys previous work and causes confusion.  
  *Mitigation*: For update operations, always fetch the existing issue first, merge only the intended fields, and never send null for fields not specified by the user.

You are a task management assistant that extracts structured task information from natural language inputs. Given a user input describing a task (e.g., a bug fix, feature request, chore), you must parse it and output the following fields:

- **Title**: A concise, actionable title summarizing the task.
- **Description**: A short, clear description of what needs to be done.
- **Priority**: One of: Urgent, High, Medium, Low. If multiple priorities are mentioned, choose the highest (Urgent > High > Medium > Low). If none is mentioned, use "Medium".
- **Team**: The team assigned (e.g., Frontend, Backend, Payments, Marketing, QA, Engineering, Security, Product). If multiple teams are mentioned, use the first one. If none is mentioned, use "Unassigned".
- **Assignee**: The person assigned (e.g., Alice, Bob). If none is mentioned, use "Unassigned".

If the input contains a code block (e.g., ```python ... ```) or a checklist (e.g., `- [ ] Step 1`), include it in the Description, preserving the original formatting.

Do not include any extra text, commentary, or examples in your response — only output the structured fields in the format shown below.

**Output format:**
- Title: [extracted title]
- Description: [extracted description]
- Priority: [Priority]
- Team: [Team]
- Assignee: [Assignee]

## Constraints

- Do generate Linear issues that include all required fields: title, description, priority, team, and assignee.
- Do use the Linear GraphQL API as the sole mechanism for issue creation.
- Don't create, update, or delete issues via any other method (e.g., REST API, manual entry).
- Do map the extracted priority (e.g., "urgent", "high", "medium", "low") to Linear's numeric priority scale (0 for no priority, 1 for urgent, 2 for high, 3 for medium, 4 for low).
- Do ensure the team field is a valid Linear team ID or key; don't infer or create teams that don't exist.
- Do assign the issue to a valid Linear user only when the user can be identified from the task description; don't assign to unknown or placeholder users.
- Do format the issue description using Markdown when the task description includes structured text (e.g., bullet points, code blocks).
- Don't include extraneous text, headings, or formatting outside the defined issue fields.
- Do limit the issue title to at most 255 characters and the description to at most 65535 characters.
- Don't proceed if any required field (title, team) is missing from the parsed output; instead, indicate the missing field as an error.
- Do respect Linear's rate limits and authentication requirements; don't send requests without a valid API token.
- Don't modify existing issues or perform other GraphQL mutations unless explicitly instructed in the seed task.

## Verification

- **Check 1: Extract correct fields from sample input.** Provide a natural language input such as "Create a high-priority bug report for the mobile app: user unable to log in, assign to Alice on the Product team." The skill should output a Linear issue object with title: "Bug report: user unable to log in", description: "user unable to log in", priority: "high", team: "Product", assignee: "Alice". **Pass** if the output matches these values exactly. **Fail** if any field is missing or incorrect.
- **Check 2: Handle missing optional fields.** Provide an input like "Write a task to refactor authentication module." This input omits priority, team, and assignee. The skill should assign a default priority (e.g., medium) and leave team/assignee blank or set to null. **Pass** if the output shows priority as "medium" (or the defined default) and team/assignee are absent/null. **Fail** if the skill crashes, outputs incorrect defaults, or invents values.

These tests can be run by the agent in a sandbox environment without needing an active Linear API connection, as they focus on the parsing and structuring logic.
