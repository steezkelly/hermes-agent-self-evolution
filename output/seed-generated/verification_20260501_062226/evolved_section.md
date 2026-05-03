## Overview  
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