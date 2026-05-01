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