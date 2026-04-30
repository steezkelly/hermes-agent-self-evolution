---
name: companion-safety
description: Safety rules, PII boundaries, delegation constraints, and bug workarounds for the companion system. Load before any delegation to prevent timeout bugs and enforce data hygiene.
version: 1.0.0
metadata:
  hermes:
    tags: [companion, safety, delegation, constraints, bugs]
    related_skills: [companion-system-orchestration, companion-personas, hermes-delegation-bug, hermes-delegation-credentials]
---

# Companion System Safety

## Critical Safety Rules

1. **NEVER combine `web` + `terminal` in one sub-agent.** This triggers the Hermes delegation timeout bug (NousResearch/hermes-agent#14726).
2. **Always use single-toolset agents.** If a task needs both web research and terminal work, break it into two sequential delegate_task calls.
3. **Cap max_iterations at 20.** Higher values increase timeout risk with long context.
4. **Wiki is source of truth.** All persistent output must go to `~/wiki/`. Mnemosyne is the session memory provider; wiki is the human-auditable backing store.

---

## PII Boundaries

When populating the companion system's knowledge base with personal biographical data:

- **Prefer direct testimony over web scraping** for employment history, relationships, and personal events. Scraped social media data is often incomplete, outdated, or behind auth walls.
- **Verify employment via direct testimony** rather than scraping LinkedIn/Facebook, which use bot detection and auth walls.
- **Do not harvest specific financial values** (exact salaries, account balances, disability amounts). Record categories only.
- **Set confidence: 0.9 and source: direct-testimony** for user-provided biographical facts.
- **Mark gaps explicitly** — if the user doesn't know exact dates or details, record the gap rather than guessing or scraping.

---

## Delegation Constraints

### Sequential Delegation (Multi-Step Tasks)

If a task naturally needs multiple agent types, break into sequential calls:

```python
# Step 1: Research
result = delegate_task(
    toolsets=["web"],
    max_iterations=15,
    context="Research: ...",
    goal="..."
)

# Step 2: Engineering (uses research result in context)
delegate_task(
    toolsets=["terminal", "file"],
    max_iterations=20,
    context=f"Build based on this research: {result}",
    goal="..."
)
```

### Per-Agent Wiki Memory

Each agent can have a wiki page for persistent learnings:

```
~/wiki/agents/
├── <agent-name>/
│   ├── memory.md      ← persistent notes, lessons, grievances
│   ├── expertise.md   ← accumulated domain knowledge
│   └── state.json     ← current tasks, blockers
```

Load before delegation, save key learnings after task completion.

---

## Delegation Bug Reference

The `hermes-delegation-bug` skill contains the full analysis. Summary:

**Confirmed pattern:** `web toolset + any other toolset + long prompt + max_iterations >= ~20` → timeout, 0 API calls.

**Workarounds:**
- Never combine `web` with other toolsets in the same subagent
- Cap `max_iterations` at 5-10 when you must combine toolsets
- Split research + build into sequential delegations
- If a subagent times out, change at least one variable before retrying

**Credential failures:** If delegation fails with "no API key found", see `hermes-delegation-credentials` for how the credential pool works and safe workarounds.
