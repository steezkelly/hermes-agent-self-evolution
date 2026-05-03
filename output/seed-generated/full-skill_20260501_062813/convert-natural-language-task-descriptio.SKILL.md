---
name: convert-natural-language-task-descriptio
description: Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API"
      iterations_per_section: 3
      optimizer_model: "minimax/minimax-m2.7"
      eval_model: "minimax/minimax-m2.7"
      coherence_passed: true
      coherence_issues: "none"
      section_metrics:
        overview:
          exit_code: 0
          elapsed_seconds: 0.0
        when-to-use:
          exit_code: 0
          elapsed_seconds: 0.0
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
        troubleshooting:
          exit_code: 0
          elapsed_seconds: 0.0
        variants:
          exit_code: 0
          elapsed_seconds: 0.0
        related-skills:
          exit_code: 0
          elapsed_seconds: 0.0
      total_elapsed_seconds: None
      timestamp: ""
---

# Convert Natural Language Task Descriptio

Convert natural language task descriptions into structured Linear issues with title, description, priority, team, and assignee fields via the Linear GraphQL API


## Overview

This skill transforms natural language task descriptions into structured Linear issues by parsing input text and mapping it to Linear's issue schema. It extracts key components—title, description, priority, team, and assignee—from unstructured input and formats them according to Linear's requirements. The skill interacts with Linear's GraphQL API to create issues directly within a specified workspace. The core mental model is treating natural language as a flexible input format that gets systematically translated into the structured fields Linear expects, with contextual cues (keywords, urgency indicators, explicit mentions) guiding field population.

## When-To-Use

**Use this skill when:**
- A user provides a task idea or bug description in plain English and needs it created as a formal Linear issue with title, description, priority, team, and assignee populated
- Converting informal task lists or meeting notes into structured, trackable Linear issues
- Rapidly creating properly formatted issues during a conversation without the user needing to know Linear's data model
- Bulk-creating multiple related issues from a natural language task breakdown
- A user wants to create a Linear issue but doesn't have direct Linear access or API knowledge

**Do NOT use this skill when:**
- The user already has an existing Linear issue that just needs updating or modifying—use the Linear Update Issue skill instead
- The goal is to search, query, or retrieve existing issues from Linear—use the Linear Query skill instead
- Creating issues requires complex state management, custom fields, or relationships that this skill cannot infer from natural language alone

**Prerequisites before invoking:**
- Linear API credentials and workspace access must be configured
- The target team and any referenced assignees must exist in the Linear workspace
- The user must provide enough detail in their task description to populate at minimum the title and description fields; priority defaults to "No Priority" if unspecified

## Steps

1. Parse the incoming natural language task description to identify core components: the task title, detailed description, implied priority level, relevant team, and any mentioned assignee.

2. Use the `hermes tool extract-entities` tool to structure the raw text and map identified elements to Linear's required fields (title, description, priority, team, assignee).

3. Validate that required fields are present. If title or description are missing, prompt the user for clarification. Set default priority to "Medium" if not explicitly stated.

4. Construct the GraphQL mutation for creating a Linear issue. Format the payload with all extracted fields mapped to Linear's `IssueCreateInput` schema.

5. Authenticate with the Linear API by retrieving stored credentials using `hermes auth get --service linear`. Verify the session is active before proceeding.

6. Execute the GraphQL mutation against the Linear API endpoint using `hermes call linear-api --mutation "issueCreate" --variables '<structured_payload>'`.

7. Parse the API response to confirm successful issue creation. Extract the new issue identifier and URL from the response payload.

8. Return confirmation to the user with the issue title, identifier, and direct link to the created Linear issue.

## Pitfalls

- **What goes wrong:** The natural language input omits a required Linear field (e.g., title, assignee, or team). **Why it matters:** Linear’s API will reject the mutation, leaving the issue unsaved and breaking downstream tracking. **Mitigation:** Add a pre‑flight validation that detects missing mandatory fields and either fills a safe default (e.g., “Untitled Task”) or asks the user to confirm the missing information before issuing the GraphQL mutation.

- **What goes wrong:** Ambiguous priority wording (e.g., “urgent”, “high priority”) is not translated into Linear’s numeric priority scale. **Why it matters:** Without the correct priority value, the issue may be placed in the wrong queue, causing delayed or mis‑prioritized work. **Mitigation:** Maintain a deterministic mapping table (e.g., “urgent” → 1, “high” → 2, “medium” → 3, “low” → 4) and default to “medium” when the mapping is uncertain.

- **What goes wrong:** The assignee is specified by name or username but no corresponding Linear user ID exists or the name matches multiple users. **Why it matters:** Assigning to a non‑existent or ambiguous user results in a validation error, and the issue may be left unassigned or incorrectly assigned. **Mitigation:** Resolve the name against the Linear user list via a preliminary query; if no match is found, flag the issue for manual assignment or assign to a default “unassigned” placeholder.

- **What goes wrong:** The team field is omitted or refers to a non‑existent team identifier. **Why it matters:** Linear issues without a valid team are rejected or placed in a default orphan team, breaking team‑based reporting and access controls. **Mitigation:** Require a team identifier from the user or fall back to a predefined default team ID; validate the team exists by querying the Linear API before mutation.

- **What goes wrong:** The description generated from natural language exceeds Linear’s character limit or contains unescaped special characters (e.g., quotes, backslashes). **Why it matters:** Oversized or malformed descriptions cause API validation failures or render incorrectly in the UI. **Mitigation:** Truncate the description to a safe length (e.g., 10,000 characters) and apply escaping (e.g., JSON‑style string escaping) before inserting it into the GraphQL payload.

- **What goes wrong:** Duplicate detection is missing, leading to multiple identical issues being created for the same natural language request. **Why it matters:** Redundant issues clutter the backlog, waste Linear quota, and confuse team members. **Mitigation:** Hash the normalized task description and check against a short‑term cache (e.g., in‑memory Set or Redis) before creating the issue; reject creation if a duplicate hash is found.

- **What goes wrong:** GraphQL API errors (e.g., authentication failures, rate limiting, schema mismatches) are not handled gracefully. **Why it matters:** Unhandled errors can crash the agent or leave issues in an inconsistent state. **Mitigation:** Wrap API calls with retry logic (exponential back‑off for 429 errors) and parse the `errors` field in the response; on persistent failure, log the error, alert the user, and abort the mutation.

- **What goes wrong:** Using incorrect GraphQL field names (e.g., `priority` instead of `priorityLevel`) causes the mutation to be rejected. **Why it matters:** The issue won’t be created, and debugging a silent field name mismatch wastes time. **Mitigation:** Cross‑reference the mutation payload with the latest Linear schema; define a constant mapping of logical field names to exact GraphQL field names before constructing the mutation.

- **What goes wrong:** Input contains potentially malicious characters that could be interpreted as GraphQL injection (e.g., nested braces, mutation keywords). **Why it matters:** Injection can corrupt the query, expose data, or cause unexpected side‑effects. **Mitigation:** Sanitize all string inputs by escaping special GraphQL characters and using parameterized queries (variables) instead of string interpolation.

- **What goes wrong:** The agent does not capture the returned issue ID after successful creation, preventing follow‑up actions (e.g., linking, updating status). **Why it matters:** Subsequent steps that depend on the issue ID fail, breaking end‑to‑end workflow automation. **Mitigation:** Immediately extract the `id` from the GraphQL response and store it in the agent’s context for use by downstream tasks.

## Examples

- **Example 1: Simple feature request**
  - Input: "Create a way for users to reset their password via email"
  - Output:
    - Title: "Implement password reset via email"
    - Description: "Users need the ability to reset their password by receiving a reset link via email. This includes designing the email template, implementing the reset flow, and setting token expiration rules."
    - Priority: Medium
    - Team: Backend
    - Assignee: Unassigned

- **Example 2: Bug report with context**
  - Input: "the login button keeps crashing on mobile, saw this happen on iOS Safari around 3pm today, customers are mad"
  - Output:
    - Title: "Fix login button crash on mobile Safari"
    - Description: "Users experience app crash when tapping the login button on iOS Safari. Issue reproduced around 15:00. Impact: customer-facing degradation."
    - Priority: High
    - Team: Frontend
    - Assignee: Unassigned

- **Example 3: Vague task requiring structured interpretation**
  - Input: "make onboarding better"
  - Output:
    - Title: "Redesign user onboarding flow"
    - Description: "Current onboarding experience needs improvement to increase activation rate. Scope includes: reduced friction in initial setup, clearer progress indicators, and better first-run tutorial."
    - Priority: Low
    - Team: Product
    - Assignee: Unassigned

## Constraints

- Do ensure the title is a non‑empty string with a maximum length of 256 characters.
- Don't include HTML, script tags, or any unsafe markup in the title; use plain text or basic markdown only.
- Do provide a description field; if omitted, set it to an empty string and limit its length to 10 000 characters.
- Do set priority using only the Linear‑allowed values: "urgent", "high", "normal", "low", or "none". Don't use any other priority strings.
- Do assign the issue to a valid team identifier (team ID or slug) that exists in your Linear workspace. Don't reference a non‑existent team.
- Do assign the issue to a valid assignee identifier (user ID or email) that is a member of the target team. Don't assign to unknown users.
- Do use the official Linear GraphQL endpoint (https://api.linear.app/graphql) and store the API key securely (e.g., in an environment variable). Never expose the key in logs or responses.
- Don't perform any mutations other than the issue‑creation mutation unless explicitly requested; avoid delete, update, or state‑transition operations.
- Do implement error handling for GraphQL responses, check for an "errors" field, and retry requests that receive HTTP 429 up to three times with exponential back‑off.
- Don't exceed the Linear API rate limits; enforce a maximum of 10 creation requests per minute per API key.
- Do sanitize all user‑provided input before embedding it in GraphQL variables to prevent injection attacks.
- Don't log or store raw API keys or credentials; mask them in any diagnostic output.
- Do validate that all required fields (title, priority, team) are present before sending the mutation; reject the request if any are missing.
- Don't include personal data beyond what is necessary for the task; respect privacy and data‑handling policies.
- Do return a structured response containing the created issue’s identifier (id) and its Linear URL, or a clear error message if creation fails.
- Don't retain any user input beyond the scope of the current issue creation; discard all temporary data after processing.

## Verification

To confirm that the skill correctly transforms free‑form task descriptions into valid Linear issues, run the following lightweight checks. Each test includes a sample input, the expected outcome, and clear pass/fail criteria. These tests can be executed manually by a user or automated via a simple script.

## Test 1 – Parsing natural language input  
**Input**  
`"Fix the login bug for the mobile app. Priority: high. Team: backend. Assignee: alice."`  

**Expected output (structured JSON)**  
```json
{
  "title": "Fix the login bug for the mobile app",
  "description": "Fix the login bug for the mobile app",
  "priority": "high",
  "team": "backend",
  "assignee": "alice"
}
```  

**Pass criteria**  
- All five fields (`title`, `description`, `priority`, `team`, `assignee`) are present.  
- The `title` matches the first sentence of the input.  
- The `priority` is a recognized Linear priority string (e.g., `"high"`).  
- The `team` and `assignee` values are non‑empty strings.  

**Fail criteria**  
- Any required field is missing or empty.  
- The `priority` value is not mapped to a valid Linear priority.  
- Unexpected extra fields appear in the output.  

## Test 2 – GraphQL mutation construction  
**Input**  
Use the JSON from Test 1 as the argument.  

**Expected behavior**  
The skill generates a GraphQL mutation that looks like:  
```graphql
mutation {
  issueCreate(input: {
    title: "Fix the login bug for the mobile app",
    description: "Fix the login bug for the mobile app",
    priority: 3,
    teamId: "<backend-team-id>",
    assigneeId: "<alice-user-id>"
  }) {
    issue {
      id
      identifier
    }
    success
  }
}
```  

**Pass criteria**  
- The mutation includes all required fields (`title`, `description`, `priority`, `teamId`, `assigneeId`).  
- The `priority` is expressed as an integer that Linear accepts (e.g., `3` for “high”).  
- The mutation syntax is valid (no missing braces, correct argument names).  

**Fail criteria**  
- The mutation is missing any required argument.  
- The `priority` is still a string instead of an integer.  
- GraphQL syntax errors are present (e.g., mismatched brackets).  

## Test 3 – End‑to‑end integration (optional but recommended)  
**Setup**  
- Obtain a test Linear API key and a test workspace.  
- Provide the same natural‑language input as in Test 1.  

**Pass criteria**  
- The API returns a `200 OK` with a JSON body containing `issueCreate { issue { id identifier } success true }`.  
- The created issue appears in the Linear UI with the correct title, description, priority, team, and assignee.  

**Fail criteria**  
- The API returns an error (e.g., `401 Unauthorized`, `400 Bad Request`).  
- The issue is not visible in Linear, or field values differ from the input.  

## Test 4 – Error handling for incomplete input  
**Input**  
`"Create an issue about performance."`  

**Expected behavior**  
The skill should return a clear error message indicating which fields are missing (`priority`, `team`, `assignee`) and should not attempt to create a Linear issue.  

**Pass criteria**  
- The response contains an error object with a message listing the missing fields.  
- No GraphQL mutation is issued.  

**Fail criteria**  
- The skill attempts to create an issue with empty or default values, or crashes.  

## Running the tests  
1. **Manual testing** – Paste the sample inputs into the skill’s conversation and compare the generated JSON / GraphQL with the expectations above.  
2. **Automated testing** – Use a simple script that:  
   - Sends the sample natural‑language strings to the skill,  
   - Captures the JSON output and the generated GraphQL,  
   - Asserts that the pass criteria are met (e.g., using `jq` or a small Python/JS test harness).  
3. **Integration testing** – If a test Linear workspace is available, execute the full pipeline and verify the issue appears in the Linear UI.  

By completing these checks you can be confident that the skill correctly transforms natural language task descriptions into valid Linear issues and handles both success and error cases as expected.

## Troubleshooting

- **If the skill returns an "Invalid API key" error**, the Linear API key may be expired, revoked, or misconfigured. Check that the `LINEAR_API_KEY` environment variable contains a valid personal API key from your Linear workspace settings. Regenerate the key if necessary at Linear Settings → API → Personal API Keys.

- **If issue creation fails with "Team not found" or "Assignee not found"**, the skill is referencing a team ID or user ID that doesn't exist in your Linear workspace. Verify the exact spelling and casing of team and assignee names. Use team identifiers (e.g., `eng`, `design`) from your Linear workspace rather than full team names.

- **If priority is always set to "No priority" despite user intent**, the natural language priority (e.g., "urgent", "high priority") may not map cleanly to Linear's numeric scale (0-4). When in doubt, explicitly specify priority as `urgent` (maps to 0), `high` (maps to 1), `medium` (maps to 2), or `low` (maps to 3).

- **If you're hitting rate limits (429 errors)**, the skill is making rapid successive GraphQL requests. Build a 2-3 second delay between issue creation calls, or batch multiple related issues into a single request if your workflow allows it. Check the `X-RateLimit-Remaining` header in responses to monitor quota.

- **If the extracted title is empty or truncated**, the natural language input may lack a clear imperative statement or subject. Ensure your input begins with a clear task description (e.g., "Fix login bug" rather than "The login bug that needs fixing"). Titles exceeding 255 characters will be silently truncated.

- **If required fields are missing in the created issue**, Linear's schema requires a `teamId` for all issues. If no team is specified in the input, the skill defaults to the workspace's primary team. Always include a team reference to avoid creating issues in unexpected locations.

- **If assignee mention doesn't resolve to a user**, Linear requires exact email or user ID matches for assignees. Mentions like "@john" or partial names won't resolve. Use the user's full email address or their Linear user ID (e.g., `user_id: "abc123"`) for reliable assignment.

## Variants

This skill has several useful variations depending on the complexity of the input and desired precision:

**1. Standard Full Extraction**
The base approach that extracts all five fields (title, description, priority, team, assignee) from natural language. Use this when the input provides clear details about who should handle the task and what the priority should be.

**2. Smart Assignment Variant**
Leverages additional context analysis to make informed assignment decisions when explicit assignee information isn't provided. This variant examines task keywords, estimated complexity, and team member specializations to suggest appropriate assignees. Trade-off: Adds processing time and may require access to team member skill profiles.

**3. Batch Conversion Variant**
Designed for when a user provides multiple task descriptions at once (e.g., "Create issues for: 1. Fix login bug, 2. Update docs, 3. Add dark mode"). This variant processes each item sequentially while maintaining consistency in priority interpretation and formatting. Trade-off: If one issue fails validation, the entire batch may need manual review.

**4. Minimal Quick-Capture Variant**
Extracts only the essential title and description, defaulting priority to "Medium" and assignee to an unassigned state. Use this for rapid task capture when detailed routing isn't immediately necessary. Trade-off: Requires follow-up work to properly route and prioritize tasks.

For most integrations, the Standard Full Extraction provides the best balance of structure and automation, with the Smart Assignment Variant offering enhanced autonomy when assignees aren't explicitly named.

## Related-Skills

- **Task Prioritization Assistant** – Teaches how to translate urgency cues and deadline hints from natural‑language task descriptions into the correct `priority` value for the Linear API. Knowing how priorities are derived makes the creation step more accurate.

- **Team & User Directory Lookup** – Shows how to resolve human‑readable team names and assignee mentions to the corresponding Linear IDs (`team` and `assignee`). This skill is a prerequisite for populating those fields reliably during issue creation.

- **Linear Issue Querying & Management** – Covers reading, updating, commenting on, and closing existing issues via the GraphQL API. After a new issue is created, this skill lets you verify, modify, or chain additional actions based on the created issue.

- **Webhook & Automation Triggers** – Demonstrates how to register webhooks or trigger downstream automations (e.g., Slack notifications, CI pipeline starts) when an issue is created. It builds on the creation skill to extend automation beyond the API call itself.

- **Reporting & Metrics Aggregation** – Provides methods to pull issue data for generating summaries, burndown charts, or cycle‑time analytics. While optional, it benefits teams that want to monitor the output of the creation workflow over time.

**Natural learning / combination order**

1. **Team & User Directory Lookup** – Map names to IDs first.  
2. **Task Prioritization Assistant** – Determine priority levels next.  
3. **Linear Issue Creation (core skill)** – Use the resolved IDs and priorities to create the issue.  
4. **Linear Issue Querying & Management** – Verify or modify the issue after creation.  
5. **Webhook & Automation Triggers** – Add post‑creation notifications/automations (optional).  
6. **Reporting & Metrics Aggregation** – Analyze the created issues for insights (advanced).

