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