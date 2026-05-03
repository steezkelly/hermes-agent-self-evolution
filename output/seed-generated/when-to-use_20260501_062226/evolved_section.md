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