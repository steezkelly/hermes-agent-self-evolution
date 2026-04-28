---
name: companion-workflows
description: All 8 workflow patterns for the companion system — feedback loops, collaborative investigation, strategic planning, philosopher pipelines, health checks, roundtables, A/B testing, and post-completion audit. Load when planning a multi-agent session or choosing which pattern fits a task.
version: 1.0.0
metadata:
  hermes:
    tags: [companion, workflows, patterns, multi-agent, orchestration]
    related_skills: [companion-system-orchestration, companion-personas, companion-safety]
---

# Companion System Workflows

Seven proven patterns for multi-agent collaboration, plus an audit pattern for post-completion verification. Choose based on task type.

---

## Pattern 1: Agent Feedback Loop (HR Pattern)

Give each persona a grievance or wish. Then dispatch Juno Faire to synthesize feedback into a formal proposal. This produces actionable systemic insights.

**Example:** We asked 5 agents what tool they wished for. All 5 independently complained about memory persistence in different forms — revealing a real architectural gap, not a fictional narrative.

**Steps:**
1. Dispatch all agents with introspection prompt ("introduce yourself + one wish")
2. Collect outputs
3. Dispatch HR agent: "Synthesize feedback into formal improvement proposal"
4. HR writes structured markdown to `~/wiki/plans/`

---

## Pattern 2: Collaborative Multi-Agent Investigation

For complex questions requiring cross-domain analysis, dispatch agents in **waves**:

**Wave 1 — Parallel Investigation:**
- Engineer: Inspect filesystem, configs, source code
- Researcher: Search docs, GitHub, web for intended behavior
- Curator: Audit data integrity, sync state, provenance

**Wave 2 — Save & Sync:**
- Save each agent's findings to their wiki page at `~/wiki/agents/<agent-name>/`
- Mnemosyne triples are session-scoped; for cross-session persistence, write structured findings to wiki

**Wave 3 — Critique & Synthesis:**
- Dispatch critique wave: each agent reviews others' findings from their domain expertise
- Engineer critiques feasibility, Researcher verifies sources, Curator checks integrity
- CEO weighs strategic implications, Manager checks complexity/schema burden
- HR defends/revises original proposal based on feedback

**Wave 4 — Consensus & Documentation:**
- Dispatch documentation agent to write the unified conclusion
- Dispatch recommendation agent to propose next steps
- All outputs saved to wiki with SCHEMA compliance

**Key insight:** When agents critique each other with domain expertise, they surface real constraints (source code limits, data integrity risks, complexity ceilings) that a single agent would miss.

---

## Pattern 3: Strategic Planning Flow

For roadmap/goal planning requests:

```
1. CEO reads wiki state (goals/, plans/, index.md)
2. CEO generates structured plan → ~/wiki/plans/
3. Philosopher interrogates the plan's assumptions (in-session)
4. Manager decomposes plan into sub-tasks
5. Engineer implements technical items
6. Researcher gathers missing information
7. Curator syncs verified facts to wiki
8. Psychologist reviews the full cycle for patterns
```

---

## Pattern 4: Philosopher → Action → Psychologist Pipeline

For decisions with significant weight:

```
1. Philosopher challenges assumptions (pre-decision)
2. User/agent commits to direction
3. Action is executed
4. Psychologist analyzes what happened (post-action)
5. Key insights stored in Mnemosyne (global, importance=0.8)
6. Next session: insights recalled automatically
```

---

## Pattern 5: System Health Check

Periodic or on-demand infrastructure review:

```
1. System agent checks: services, configs, disk, memory, cron jobs
2. Manager reviews findings against conventions
3. CEO assesses if any issue impacts strategic goals
4. Engineer implements fixes
5. System agent re-verifies health
```

---

## Pattern 6: Companion Roundtable

Real-time multi-role conversation where roles discuss topics together. Different from one-by-one dispatch — roles respond to each other, interrupt, disagree, and synthesize.

**Three formats:**
- **Freeform roundtable** — exploration, discovering insights
- **Formal meeting** — one-by-one reactions → presentations → cross-discussion → decisions
- **After-session** — informal conversation after formal meeting adjourns (deepest insights)

**Key rules:**
- 7 turns per generation chunk with 9 roles (single-generation caps at ~11 turns)
- 1-3 roles per turn, 2-4 sentences per role
- Each role speaks 2-5 times across full conversation
- After-session produces breakthroughs that formal session can't

**Full documentation:** See skill `companion-roundtable`

---

## Pattern 7: A/B Test Architectural Decisions

When the team proposes an architectural pattern, test it empirically before committing.

**Proven workflow (2026-04-25):**
1. Team proposes: "4-tier scoring for memory retrieval"
2. Philosopher challenges: "Is the tier abstraction actually better?"
3. Engineer builds A/B test harness (memory-ab-test.py)
4. Test runs: flat beats tiered (p=0.0004)
5. Team discusses finding, makes recommendations
6. Engineer applies fix (2-line change)
7. ADR logged: "Tiers classify; they don't rank"

**Key insight:** Test assumptions before building on them. The A/B test caught premature optimization — tiers are good for management but bad for retrieval scoring.

**Full documentation:** See `ab-test-design.md` in the companion-system repo or ask the agent to search for it.

---

## Pattern 8: Post-Completion Audit Using Companion Roles

For verifying finished work across multiple dimensions. The work is already done — this pattern checks for what was missed.

**Proven workflow (2026-04-27):** After a scripts optimization pass, 3 roles audited in parallel:

### Roles and Audit Lenses

| Role | Audit Lens | What They Check |
|------|-----------|-----------------|
| **Manager (Vera Halloway)** | Protocol compliance | Filing conventions, log completeness, procedure adherence |
| **Curator (Silas Vane)** | Documentation accuracy | File consistency, cross-references, skill documentation |
| **Researcher (Dr. Aris Thorne)** | Factual correctness | Claims against source material, data accuracy, inconsistencies |

Other lenses depending on the work type:
- **Engineer** — Code quality, architecture, edge cases
- **Psychologist** — User experience impact, cognitive load
- **System** — Infrastructure impact, config drift, resource usage

### Steps

1. **Define audit scope** — What was done? What dimensions matter? (code, docs, facts, config, process)
2. **Select roles** — Pick the audit lens(es) that match the work's risk profile
3. **Delegate in parallel** — Each role gets:
   - Context: what was done, what changed
   - Their lens: what to check, what sources to verify against
   - A structured goal: produce a checklist of findings with verdicts
4. **Synthesize results** — Collect all findings. Categorize:
   - **FIX** — unambiguous errors (wrong facts, missing logs, broken links)
   - **IMPROVE** — subjective improvements (could be clearer, more complete)
   - **PASS** — verified correct
5. **Apply fixes** — Address all FIX items; optionally address IMPROVE items
6. **Re-verify** — Run lint, re-check affected areas

### When to Use

- After a complex multi-phase task where mistakes could have accumulated
- After a refactoring or migration that touched many files
- Before declaring a project phase complete
- When Steve says "audit that" or "check my work"

### Key Insight

Parallel delegation is critical. Each role sees different things — Vera catches a missing log entry, Aris catches a factual error in a page Silas verified is well-formatted. No single role covers all dimensions. Let them work independently, then synthesize results. Spending 3-5 minutes of API budget on parallel audits catches issues that would ripple for hours.

### Comparison to Pattern 2 (Collaborative Investigation)

| Dimension | Pattern 2 | Pattern 8 |
|-----------|-----------|-----------|
| **Direction** | Forward: solve unknown problem | Backward: verify completed work |
| **Assumption** | We don't know the answer | The answer exists, check it |
| **Role interaction** | Sequential waves, cross-critique | Parallel independent, then synthesize |
| **Output** | Understanding + solution | Fix list + verification |

## Choosing a Pattern

| If the task is... | Use pattern |
|-------------------|-------------|
| Getting feedback from the system | 1. Feedback Loop |
| Deep investigation of a problem | 2. Collaborative Investigation |
| Roadmap or goal planning | 3. Strategic Planning |
| High-stakes decision | 4. Philosopher → Action → Psychologist |
| System maintenance/health | 5. System Health Check |
| Brainstorming or live discussion | 6. Roundtable |
| Evaluating an architectural choice | 7. A/B Test |
| Verifying completed work across dimensions | 8. Post-Completion Audit |
