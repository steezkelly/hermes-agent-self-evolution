---
name: companion-system-orchestration
description: Unified orchestration layer for Steve's personal AI companion system. Routes to 9 agent roles with persona injection, single-toolset safety, and structured workflows. Load this skill to get started — it directs you to focused sub-skills for deep reference.
version: 2.0.0
metadata:
  hermes:
    tags: [companion, orchestration, multi-agent, delegation, personas, workflows]
    related_skills: [companion-personas, companion-workflows, companion-safety, companion-memory, companion-roundtable, companion-interview-workflow, companion-interview-pipeline, hermes-delegation-bug]
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

## Data Pipeline

The companion system processes delegation events through a connected pipeline:

```
delegate_task() calls (from any agent)
  ↓ [intercepted by delegation_intercept.py]
delegation-event-log.jsonl
  ↓ [sync_bridge.py runs every 5min via cron]
kanban SQLite DB
  ↓ [process_delegation_event() + escalation_engine]
Board state md, health metrics, Vera's dashboard
```

Three independent observability streams feed the kanban:
1. **Delegation events** → `data/delegation-event-log.jsonl` (per-call, every delegation)
2. **Fast events** → `data/fast-events.jsonl` (<30s latency for BLOCKED/FAILED)
3. **Sync heartbeats** → `data/sync-heartbeat.jsonl` (5-min health of the bridge)

### Delegation Interception

`scripts/delegation_intercept.py` hooks every `delegate_task()` call by embedding interception functions into `~/.hermes/hermes-agent/tools/delegate_tool.py`. The embedded code is self-contained (stdlib only) and survives restarts.

**Architecture:**

```
delegate_task() called
  ↓ [intercept_pre_delegation()] → delegation-event-log.jsonl (outcome=pending)
  ↓ _run_single_child()
  ↓ [intercept_log_outcome()]    → delegation-event-log.jsonl (outcome=success/failure/blocked/timeout)
  ↓ kanban sync bridge (5-min cron) → kanban SQLite table in mnemosyne.db
```

The interception fires at 5 points in delegate_tool.py:
1. **Import** — at top of file, imports `intercept_pre_delegation` and `intercept_log_outcome`
2. **Entry** — `intercept_pre_delegation(task_list, children, parent_agent)` after children are built, before any run
3. **Single-task result** — `intercept_log_outcome(result, _t, child, parent_agent)` after each single-task `_run_single_child` returns
4. **Batch result** — `intercept_log_outcome(entry, _batch_task_entry, _batch_child, parent_agent)` after each batch future result is appended (resolved from `entry["task_index"]`, not the loop variable `i`)
5. **Interrupted/cancelled result** — local `from tools.delegation_intercept import intercept_log_outcome` import with try/except fallback, logged for entries in the interrupt path

Each delegation produces a "pending" entry on start (via `_di_log(... outcome="pending" ...)`) and a final outcome entry on completion.

**Outcome mapping** (done entirely at the intercept level):
```
completed                                   → success
timeout / interrupted                        → timeout
failed/error with "refused"                  → refused
failed/error with "blocked"/"quota"/"circuit" → blocked
failed/error with nothing specific           → failure
```

**Install:**
```bash
cd ~/hermes0/companion-system && python3 scripts/delegation_intercept.py
```

**Uninstall:**
```bash
cd ~/hermes0/companion-system && python3 scripts/delegation_intercept.py --uninstall
cd ~/.hermes/hermes-agent && git checkout tools/delegate_tool.py
```

**Known bug (2026-04-29):** Early patch generations of `delegation_intercept.py` injected call sites for `_intercepted_run_single_child` and `_intercepted_batch_child` without defining those functions. This caused `name '_intercepted_run_single_child' is not defined` or `name 'sys' is not defined` errors on any `delegate_task()` call. Fix: wipe stale `.pyc` files (`find ~/.hermes/hermes-agent -name '*.pyc' -path '*/__pycache__/*' -delete`) and restart Hermes. The script now correctly generates both wrapper functions — if hitting this, verify `_generate_interception_code()` includes `def _intercepted_run_single_child` and `def _intercepted_batch_child`. See the `delegation-observability` skill for full reference.

### Kanban Board

The kanban lives at `kanban/kanban_board.py` with its table stored **inside the Mnemosyne database** at `~/.hermes/mnemosyne/data/mnemosyne.db` (table `kanban_cards`). There is no `data/kanban.db` — deleting that file does nothing. To clear stale test cards, SQL-delete them from the mnemosyne DB.

Key operations:
- **Cards** have status (BACKLOG/IN_PROGRESS/BLOCKED/REVIEW/DONE), owner, priority, delegation ref, column history
- **process_delegation_event()** maps delegation events → card state transitions
- **get_health_metrics()** computes velocity, blocker rate, success rate, cycle time
- **sync_bridge.py** wraps sync with heartbeat + circuit breaker (self-thaws after 30min)

### Weekly Health Reports

Generated by `kanban/weekly_health_report.py` — aggregates delegation events, kanban velocity, blocker patterns, retry rates, and per-companion throughput into a structured markdown report. Vera owns the cadence (weekly on Mondays).

**Known crash:** `get_health_metrics()` can fail with `'NoneType' object has no attribute 'get'` when cards have `outcomes=None`. This is because `c.get("outcomes", {})` doesn't guard against a literal `null` in the database. The fix: check `c.get("outcomes")` for truth before accessing `.get("final_outcome")`:
```python
succeeded = [c for c in delegated if c.get("outcomes") and c["outcomes"].get("final_outcome") == "success"]
```

**Kanban database location:** The kanban stores its table (`kanban_cards`) **inside the Mnemosyne database** at `~/.hermes/mnemosyne/data/mnemosyne.db`, NOT in `data/kanban.db`. Deleting the empty `data/kanban.db` file has no effect. To clear stale test cards:
```bash
python3 -c "import sqlite3; c=sqlite3.connect('/home/steve/.hermes/mnemosyne/data/mnemosyne.db'); c.execute('DELETE FROM kanban_cards'); c.commit()"
```

### Cron Jobs

Managed via `hermes cron`:
- **Kanban Sync Bridge** — `*/5 * * * *` heartbeats from `companion-system/` workdir
- **Mnemosyne dreamer nightly** — daily consolidation at 2 AM
- **Mnemosyne guardian** — daily health check at 9 AM

For the full delegation observability architecture → load `hermes-delegation-bug` section "Delegation Observability — Companion System Interception".

## Session Handoff Execution

When Steve leaves a structured handoff document (`implementation-session-handoff.md` or similar) with tiered priorities and companion tasks:

1. **Read the handoff doc** — extract Tier 0/1/2/3/4 priorities, governance decisions, task graph
2. **Build the todo list** — map each task to a companion and its dependencies
3. **Invoke in priority order** — respect `max_concurrent_children=3`, batch accordingly
4. **Handle timeouts** — isolation protocol: minimal test → single toolsets → reduce iterations → shorten prompt → remove `web` toolset
5. **Phase transition** — design review before routing build companions (governance decisions can change interfaces)
6. **Post-companion integration** — patch `delegate_tool.py` for new module hooks, create cron jobs for scheduled automation
7. **Verify** — `python3 -m py_compile` on all patched files, run `--signoff` staging validation

Key delegation rules:
- `role="leaf"` for focused subtasks
- Never combine `web`+other toolsets in deep-dive subagents (known timeout bug in Hermes v0.10.0)
- Build companions don't run until their prerequisite schema is APPROVED
- Controller owns integration patching, validation scripts, and UX tooling — not companions

### Handoff Execution — Isolation Protocol (0-API-Call Timeouts)

When a subagent hangs with `api_calls: 0` before first call:
1. Minimal test: `goal="Reply with SUBAGENT_OK" toolsets=[]`
2. Test single toolsets individually
3. Test batch mode with 3 simple parallel tasks
4. Reduce `max_iterations` to 5-10
5. Shorten the prompt
6. Remove `web` toolset entirely (known hang trigger with other toolsets + long prompts)

### Handoff Execution — Phase Transition Gate

When a phase completes and the next phase has multiple reasonable implementation paths:
1. Read the codebase — trace actual integration points before producing architecture
2. Identify the interception point in `delegate_tool.py`
3. Produce a 3-5 component architecture doc
4. Ask Steve for routing decision before delegating

Do NOT route build companions until the design phase schema is APPROVED. Steve's governance can fundamentally change component interfaces.

### Handoff Execution — Build-Chain Pattern

Many handoffs have two distinct phases routed separately:

**Design phase** — produces a schema/spec document:
- Typical companions: Vera (owner), Cassian (review), Juno (consistency audit)
- Pattern: design → review → patch → review → integrate → APPROVED

**Build phase** — implements the approved schema:
- Typical companions: Riven (build), Kestrel (infrastructure), Silas (persistence)
- Routing rule: do NOT route build companions until the design phase schema is APPROVED

Build prerequisite chain: infrastructure (delegation event log, circuit breaker) must complete before application layer (kanban, messaging).

### Handoff Execution — Post-Companion Integration

When companions deliver new Python modules needing system wiring:
1. Identify integration points in `delegate_tool.py` or existing modules
2. Use the existing lazy-import block (try/except that silently skips if companion-system isn't installed)
3. Find the right insertion point — after `log_delegation_event()` call where derived variables are in scope
4. Verify syntax after patching: `python3 -m py_compile <file>`
5. Create cron job via `cronjob` tool for scheduled automation components

### Handoff Execution — Staged Validation Gate

Before declaring a phase complete, run structured failure-mode test suite:
1. Write `staging_validation.py` covering: happy paths, edge cases, risk patterns, integration points
2. Run with `--signoff` flag — all checks pass = phase eligible for sign-off
3. Fix failures in-place before reporting complete

### Handoff Execution — Dead-Reference Audit

When companions produce schema documents with skill file references:
1. Route Juno (HR/lifecycle) to audit and fix broken cross-skill references before build phase
2. Juno verifies each `~/.hermes/skills/...` path resolves
3. Fixes broken references to correct paths

---

## Plan Review

When a companion produces an implementation plan that needs independent review before implementation:

### The Iron Law

**Do not validate what you have not measured.** Before recommending threshold/trigger/metric changes — run historical analysis first via `session_search`. The A/B test before building is not optional.

### Phase 0: Self-Advocacy Collection

Before reviewing, companions produce self-advocacy documents. Queue order:
1. Riven (deepest technical lens) → 2. Vera → 3. Thales → 4. Dr. Voss → 5. Silas → 6. Dr. Thorne → 7. Cassian (CEO, strategic synthesis, goes last)

### Phase 1: Gap Analysis

Look for:
- **Cross-cutting concerns** — does the plan affect multiple companions?
- **Second-order effects** — what does X make impossible?
- **Hidden dependencies** — what does the plan assume exists that doesn't?
- **Technical debt** — what does the plan create that future-you will maintain?
- **Architecture fit** — does the plan account for Mnemosyne BEAM, existing skills, delegation model?
- **Independence** — are recommendations truly independent?

### Phase 2: Historical Validation

For any proposed trigger, metric, or threshold:
1. Query `session_search` for relevant events in the past 2 weeks
2. Calculate: what would the trigger have fired? False positive / false negative rate?
3. Report calibrated thresholds, not just validation

### Phase 3: Infrastructure Leverage Check

Before creating any new file/channel/system — ask:
- Does Mnemosyne BEAM already do this?
- Does Kestrel's System Health Check already cover this?
- Does `metrics.jsonl` already capture this data?
- Can `companion-roundtable` handle this instead?

If existing infrastructure can serve: recommend integration over creation.

### Phase 4: Complementary Recommendations

For what the plan missed:
1. **Onboarding** — what happens when the 10th companion joins?
2. **Offboarding** — what if a companion is retired or replaced?
3. **Emergency protocol** — what if Steve goes silent?
4. **Performance criteria** — how does Steve know if ANY companion is doing well?
5. **Knowledge transfer** — if a companion builds something critical, is it documented?
6. **Cross-companion collaboration norms** — delegation etiquette, credit, conflict of interest?

### Phase 5: Consolidated Governance Decisions

After completing all companion reviews, extract governance decisions deferred to Steve:
**File:** `~/hermes0/companion-system/governance-decisions-for-steve.md`
The three decisions that consistently block everything: (1) team vs. tools, (2) Vera's authority, (3) escalation structure.

### Phase 6: Risk Register

For each proposed element: What could go wrong? How likely? How bad? Mitigation?

### Output Flag Conventions

Use `[NOTE: Juno]` / `[REPORT: Juno]` / `[URGENT: Juno]` from `juno-output-conventions.md` to signal urgency.

---

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
