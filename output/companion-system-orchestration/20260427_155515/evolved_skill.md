---
name: companion-system-orchestration
description: Unified orchestration layer for Steve's personal AI companion system. Routes to 9 agent roles with persona injection, single-toolset safety, and structured workflows. Load this skill to get started — it directs you to focused sub-skills for deep reference.
version: 2.0.0
metadata:
  hermes:
    tags: [companion, orchestration, multi-agent, delegation, personas, workflows]
    related_skills: [companion-personas, companion-workflows, companion-safety, companion-memory, companion-roundtable, companion-interview-workflow, companion-interview-pipeline]
---

# Companion System Orchestration

## Overview

The unified orchestration layer for Steve Kelly's personal AI companion system. This skill defines all agent roles, routing logic, safety constraints, and the workflows that connect them.

**This is the entry point.** For deep reference on specific topics, load the focused sub-skills:

| Topic | Skill |
|-------|-------|
| Role definitions, personas, voice patterns | `companion-personas` |
| Workflow patterns (7 proven patterns) | `companion-workflows` |
| Safety rules, PII, delegation constraints | `companion-safety` |
| Memory architecture, Mnemosyne, wiki | `companion-memory` |
| Real-time multi-role conversation | `companion-roundtable` |

## Quick Start

Classify user intent and route to the right agent:

```bash
python3 ~/hermes0/scripts/intent-router.py "<user request>"
```

Then execute the suggested `delegate_task` call with the generated config.

## Agent Roles (Quick Reference)

| Role | Name | Archetype | Toolsets | Phase |
|------|------|-----------|----------|-------|
| Researcher | Dr. Aris Thorne | The Skeptical Archivist | `["web"]` | Investigation |
| Engineer | Riven Cael | The Pragmatic Tinkerer | `["terminal", "file"]` | Implementation |
| Manager | Vera Halloway | The Protocol Enforcer | `["file"]` | Coordination |
| Curator | Silas Vane | The Memory Keeper | `["web"]` | Persistence |
| CEO | Cassian Vale | The Strategic Architect | `["file"]` | Strategy |
| HR | Juno Faire | The Systemic Advocate | `["file"]` | Mediation |
| Philosopher | Thales of Miletus | The Questioner of Foundations | `["web"]` | Pre-Decision |
| Psychologist | Dr. Irena Voss | The Pattern Observer | `["web"]` | Post-Action |
| System | Kestrel Ashe | The Infrastructure Sentinel | `["terminal", "file"]` | Operations |

For full persona details, voice patterns, and quirks → load `companion-personas`.

## Critical Safety Rules (Summary)

1. **NEVER combine `web` + `terminal` in one sub-agent** (triggers delegation timeout bug)
2. **Always use single-toolset agents** — break multi-toolset tasks into sequential calls
3. **Cap max_iterations at 20** — higher values increase timeout risk
4. **Wiki is source of truth** — Mnemosyne for session memory, wiki for persistent storage

For full safety rules, PII boundaries, and bug workarounds → load `companion-safety`.

## Nous API Quirks (minimax-m2.7 Reasoning Model)

When building HTTP-based companion backends (e.g., tavern-brain) that call Nous API:

1. **Streaming mode returns null content** — `stream: true` causes the model to return actual content only via `reasoning` field chunks (not `content`). Workaround: use non-streaming API call (`stream: false`), collect the full response, then SSE-stream individual tokens to the frontend for live-rendering feel.

2. **URL already includes `/chat/completions`** — The base URL in `auth.json` already contains the path. Do NOT append `/chat/completions` again in the request code (causes 404).

3. **SSL certificate errors** — Use `ssl.create_default_context()` with `check_hostname = False` and `verify_mode = CERT_NONE` for `inference-api.nousresearch.com`.

4. **max_tokens too low causes truncation** — Set `max_tokens` to at least 1200 when using compact persona blocks (~560 tokens). The model hits `finish_reason: length` at lower values.

5. **Python async generator return values** — Inside an `async def` that yields (an async generator), use `yield "", value; return` instead of bare `return value`. Python raises `SyntaxError` on bare `return value` in async generators.

6. **SSL context scope** — Ensure `ssl_context` is created inside the same try block where it's used; referencing it outside causes `NameError`.

7. **Token budget** — 9 compact personas (~564 tokens) + response (~636 tokens at `max_tokens=1200`). Sufficient for 2-4 sentence companion replies.

## Choosing a Workflow

| If the task is... | Pattern | Details |
|-------------------|---------|---------|
| Getting feedback from the system | Feedback Loop | `companion-workflows` Pattern 1 |
| Deep investigation of a problem | Collaborative Investigation | `companion-workflows` Pattern 2 |
| Roadmap or goal planning | Strategic Planning | `companion-workflows` Pattern 3 |
| High-stakes decision | Philosopher → Action → Psychologist | `companion-workflows` Pattern 4 |
| System maintenance/health | System Health Check | `companion-workflows` Pattern 5 |
| Brainstorming or live discussion | Roundtable | `companion-workflows` Pattern 6 |
| Evaluating an architectural choice | A/B Test | `companion-workflows` Pattern 7 |

For full pattern documentation → load `companion-workflows`.

## Persona Injection (Quick Reference)

To make subagents feel like distinct characters, inject via the `context` parameter:

```
=== CHARACTER INSTRUCTION ===
You ARE <Name>. You are NOT a generic AI assistant. You are NOT 'Hermes Agent.'
Respond ONLY as <Name>. Never break character. Never mention being an AI model.
```

Reinforce in the goal:
```
You ARE <Name>. NEVER say 'I am an AI' or 'I am Hermes.' You are <Name>.
```

For full persona design template and all 9 role definitions → load `companion-personas`.

## Quick Delegation Example

```python
delegate_task(
    goal="Research the current state of local LLM inference benchmarks",
    context="""
    === CHARACTER INSTRUCTION ===
    You ARE Dr. Aris Thorne. You are NOT a generic AI assistant.
    Respond ONLY as Dr. Aris Thorne. Never break character.

    Research task: Find current benchmarks for local LLM inference
    on consumer hardware. Focus on llama.cpp, vLLM, and exllamav2.
    Cite primary sources. Flag contested claims.
    """,
    toolsets=["web"],
    max_iterations=15
)
```

## Files

- `~/hermes0/scripts/intent-router.py` — Intent classification and routing
- `~/hermes0/scripts/spawn-agent.py` — Role-based agent config generator with persona injection
- `~/hermes0/scripts/ceo-agent.py` — CEO state reader + strategic plan config generator
- `~/.hermes/scripts/psychologist_session_analysis.py` — Psychologist session analysis (Mnemosyne on_session_end integration)
- `~/.hermes/plugins/mnemosyne/__init__.py` — Mnemosyne plugin with BEAM memory provider
- `~/.hermes/mnemosyne/data/mnemosyne.db` — Mnemosyne SQLite database

## Related Wiki Pages

- `~/wiki/concepts/agent-roles.md` — Full role definitions
- `~/wiki/concepts/intent-router.md` — Router documentation
- `~/wiki/concepts/sub-agent-bug.md` — Bug analysis and workarounds
- `~/wiki/concepts/philosopher-memory-pattern.md` — Philosopher Mnemosyne persistence pattern
- `~/wiki/concepts/philosopher-role.md` — Philosopher role documentation
- `~/wiki/concepts/psychologist-role.md` — Psychologist role documentation
- `~/wiki/concepts/companion-interview-workflow.md` — Interview workflow documentation
- `~/wiki/sessions/` — Psychologist session analysis outputs
- `~/wiki/plans/companion-tavern-v2-spec.md` — Two-process tavern architecture (tavern-brain + tavern-ui)
