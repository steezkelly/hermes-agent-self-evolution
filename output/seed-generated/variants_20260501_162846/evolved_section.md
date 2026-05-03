There are three primary variants for PR review that focus on different concerns:

**1. Security-Focused Review**
This variant prioritizes scanning for vulnerabilities, hardcoded secrets, injection risks, and dependency issues. It applies a threat-modeling lens to all changed code.
- **When to use**: Reviews of PRs touching authentication, payment processing, user data handling, or external API integrations.
- **Trade-offs**: May be overly cautious for internal utility code; can increase review time due to deeper dependency analysis.

**2. Performance-Focused Review**
This variant examines algorithmic efficiency, N+1 query patterns, missing indexes, unoptimized loops, and caching opportunities in the diff.
- **When to use**: PRs introducing new database queries, data processing pipelines, or high-traffic endpoints.
- **Trade-offs**: Requires domain context about expected data volumes; may miss functional bugs while focusing on optimization.

**3. Quick Triage Review**
This variant performs a lightweight pass to identify obvious blockers, contract violations, or breaking changes without deep analysis.
- **When to use**: Time-sensitive PRs, large refactors needing preliminary approval, or when assigning a specialist reviewer.
- **Trade-offs**: Lower detection rate for subtle issues; should not replace thorough review for critical paths.

The base approach (full-spectrum review) remains the default for most PRs, while variants serve as targeted specializations for high-risk areas or constrained timeboxes.