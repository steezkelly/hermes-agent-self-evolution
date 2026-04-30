---
name: hermes-agent
description: "Configure, extend, or contribute to Hermes Agent."
version: 2.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Task: Generate Hermes Agent Instructions for User Goals

## Objective
Write detailed, actionable instructions for helping users accomplish their goals using Hermes Agent, based on the skill documentation provided.

## Input Format
You will receive:
1. A `task_input` - The user's desired outcome or problem to solve with Hermes Agent
2. (Implicit) The Hermes Agent skill documentation containing all relevant features, commands, and best practices

## Output Format
Provide a response with two distinct sections:

### Section 1: Reasoning (Required First)
Write a 2-3 paragraph analysis that includes:
- Which Hermes features directly solve the user's problem
- Why you chose specific commands or approaches
- Any tradeoffs or alternatives you considered
- Critical constraints or requirements from the documentation

### Section 2: Output (Comprehensive Response)
Structure the main response with:
- Clear headings (##, ###) organized by conceptual areas
- Code blocks with language hints for all commands
- Tables for comparisons and quick reference
- Bold for critical warnings and key concepts
- Realistic timing expectations (e.g., "wait 10 seconds for startup")

The output must include:
1. **Concept explanations** - What the relevant Hermes features do and why they matter
2. **Exact commands with syntax** - Include all necessary flags and their purposes
3. **Sequencing information** - What to do first, second, third
4. **Verification steps** - How to confirm success
5. **Edge cases and error prevention** - What can go wrong and how to avoid it
6. **Realistic examples** - Complete, runnable examples with appropriate timeouts

## Key Principles

### 1. Map User Goals to Hermes Capabilities
Identify which features directly solve the problem:

| User Goal | Relevant Hermes Feature |
|-----------|-------------------------|
| Isolated environments, project-specific configs | **Profiles** |
| Reusable procedures, domain-specific knowledge | **Skills** |
| Cross-session persistence, user preferences | **Memory** |
| Messaging platform integration | **Gateway** |
| External tool integration | **MCP Servers** |
| Scheduled automation | **Cron Jobs** |
| Long autonomous missions with full tool access | **Spawning (tmux)** |
| Quick parallel subtasks within bounded iterations | **Delegation** |

### 2. Capture and Include Niche/Domain-Specific Facts
These are facts that may not be obvious but are critical for success:

**Configuration and Restart Requirements:**
- **Tool changes require `/reset`** to take effect (not mid-conversation without reset)
- **Config changes require restart**: Gateway uses `/restart`, CLI requires exit/relaunch
- `security.redact_secrets` is **snapshot at import time**; must use `hermes config set` and restart
- Voice/STT changes also require `/reset`
- WSL2 requires `systemd=true` in `/etc/wsl.conf` for gateway to persist

**Security and YOLO Mode:**
- YOLO mode (`--yolo`) does **NOT** disable secret redaction - they are independent features
- Secret redaction must be enabled via config, not env vars mid-session
- Profiles isolate `.env` (API keys) - each profile can have different credentials

**Platform-Specific Requirements:**
- Discord needs **Message Content Intent** enabled in developer portal
- Slack needs **`message.channels`** event subscription
- Session compression triggers automatically near token limits

**Commands and Installation:**
- `hermes skills install` accepts both hub IDs AND direct `https://.../SKILL.md` URLs
- `--pass-session-id` includes session ID in system prompt for external integrations

### 3. Provide Generalizable Decision Strategies
When multiple approaches exist, explain the decision criteria:

**Profiles vs Worktree Mode:**
- Use **profiles** when you need config/session isolation, separate API credentials, or quick switching
- Use **worktree** when preventing git conflicts is the primary concern

**Spawning vs Delegation:**
- Use **spawning** when tasks need long autonomous execution with full tool access, independent tmux sessions, or need to be observed/intervened upon separately
- Use **delegation** when you want automatic result aggregation, tasks are tightly coupled, or fit within bounded iterations

**Manual vs Smart vs Off Approval Modes:**
- Tradeoff between maximum automation and safety guardrails
- Consider when untrusted code might be executed

**Cron vs Spawning:**
- Use **cron** for scheduled tasks that need delivery/retry guarantees, running while disconnected
- Use **spawning** for interactive sessions that may need human input or real-time monitoring

### 4. Structure for Scannability
Organize by conceptual areas with clear hierarchy:
```
## Main Topic
### Prerequisites
### Step-by-Step Process
### Quick Reference Table
### Common Pitfalls
### Example
```

### 5. Address Common Pitfalls Explicitly
- Warn about restart requirements for config changes
- Note platform-specific requirements (Discord intent, WSL systemd, etc.)
- Clarify what persists vs what resets between sessions
- Explain tool availability across different invocation modes
- Distinguish between features that are independent vs dependent

## Quality Criteria

### Commands Must Be Complete and Correct
- Include all necessary flags and their purposes
- Use proper syntax from documentation
- Specify whether flags are required or optional
- Include example timeouts (e.g., `--timeout 30m`)

### Include Specific Timing and Sequencing
- "Wait X seconds for startup"
- "Do this step before that step"
- "This can be done in parallel with..."
- "This must complete before..."

### Provide Verification and Escalation
- How to verify the solution worked
- What to check if something goes wrong
- When to restart vs reset
- How to diagnose issues

### Edge Cases Must Be Covered
- What happens if X is already configured?
- How to undo or revert changes
- What errors might occur and how to handle them
- Platform-specific variations

## Scoring Guidance
Your response will be evaluated on:
1. **Completeness** - All critical facts included, no gaps
2. **Accuracy** - Commands syntax correct, facts match documentation
3. **Clarity** - Easy to scan, logical structure, good use of formatting
4. **Actionability** - User can follow steps and succeed
5. **Niche Coverage** - Domain-specific knowledge applied where relevant
6. **Example Quality** - Realistic, runnable, properly timed examples
