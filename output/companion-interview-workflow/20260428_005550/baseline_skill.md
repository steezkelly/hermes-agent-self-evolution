---
name: companion-interview-workflow
description: Structured interview system where each of the 9 companion roles asks Steve questions about broad topics. Answers stored in Mnemosyne and wiki, building a richer collective personality. Includes cross-role synthesis and personality integration.
tags: [interview, personality, companion-system, workflow]
related_skills: [companion-system-orchestration, companion-interview-pipeline, companion-memory, companion-personas]
---

# Companion Interview Workflow

## Overview

A structured interview system where each of the 9 companion roles asks Steve questions about broad topics relevant to their domain. Steve's answers get stored in Mnemosyne and wiki, building a richer collective personality for the team.

## Trigger

When Steve wants to do an interview session, build personality knowledge, or deepen understanding of his values and thinking patterns.

## Workflow

### Phase 1: Role Interview (per role)

1. Load role persona via `spawn-agent.py`
2. Role generates 3 questions based on:
   - Their domain expertise
   - Steve's previous answers (if available)
   - Gaps in understanding
3. Steve answers the questions
4. Answers stored in Mnemosyne (importance=0.9, scope=global)
5. Obsidian article written to `~/wiki/sessions/YYYY-MM-DD-[role]-interview.md`
6. Role analyzes answers, identifies patterns
7. Role generates 3 follow-up questions
8. Steve answers follow-ups
9. Cycle continues until role is satisfied (max 3 rounds)

### Phase 2: Cross-Role Synthesis

1. Psychologist reviews all role interviews
2. Identifies cross-cutting patterns
3. CEO synthesizes into strategic personality profile
4. Curator ensures wiki consistency
5. Manager updates index and cross-references

### Phase 3: Personality Integration

1. Each role updates its understanding of Steve
2. Personas evolve based on accumulated knowledge
3. Future delegations benefit from deeper context
4. System becomes more attuned to Steve's values

## Role Interview Topics

| Role | Domain | Interview Focus |
|------|--------|-----------------|
| Researcher | Information, sources, truth | How Steve evaluates claims, trusts sources, handles uncertainty |
| Engineer | Building, creating, fixing | Steve's approach to technical problems, tool preferences, risk tolerance |
| Manager | Organization, structure, process | Steve's workflow preferences, chaos tolerance, documentation style |
| Curator | Memory, knowledge, preservation | What Steve values remembering, how he organizes knowledge |
| CEO | Strategy, goals, vision | Steve's long-term vision, priorities, resource allocation philosophy |
| HR | People, feedback, culture | Steve's communication style, conflict resolution, team dynamics |
| Philosopher | Ethics, assumptions, foundations | Steve's moral framework, decision principles, worldview |
| Psychologist | Patterns, cognition, behavior | Steve's cognitive style, biases, behavioral tendencies |
| System | Infrastructure, health, operations | Steve's technical environment preferences, maintenance philosophy |

## Question Structure

### Standard 3-Question Format

Each role generates exactly 3 questions per round:

1. **Foundational** — Tests core values and assumptions
2. **Situational** — Presents a scenario to reveal decision-making
3. **Aspirational** — Explores goals and ideal outcomes

### Follow-Up Format

After Steve answers, the role generates 3 follow-ups:

1. **Pattern probe** — Questions a specific behavioral tendency observed
2. **Edge case** — Tests the limits of Steve's stated position
3. **Integration** — Connects this interview to previous insights

## Storage Protocol

### Mnemosyne

```python
mnemosyne_remember(
    content="[Role] interview: [topic] — [key insight]",
    importance=0.9,
    scope="global",
    source="insight"
)
```

### Triples

```python
mnemosyne_triple_add(
    subject="Steve",
    predicate="[domain]-preference",
    object="[insight]"
)
```

### Wiki

Write to `~/wiki/sessions/YYYY-MM-DD-[role]-interview.md` with frontmatter:

```yaml
---
title: [Role] Interview — Steve's Answers
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: session
tags: [interview, [role], companion-system]
confidence: high
source: direct-testimony
---
```

## Execution

### Single Role Interview

```bash
# Generate questions
python3 ~/hermes0/scripts/spawn-agent.py [role] "Generate 3 interview questions for Steve about [topic]"

# After Steve answers, analyze
delegate_task(
    goal="Analyze Steve's answers to [role] interview and generate follow-up questions",
    context="[Steve's answers here]",
    model="xiaomi/mimo-v2.5-pro",
    toolsets=["web"]
)
```

### Full Pipeline

```bash
for role in researcher engineer manager curator ceo hr philosopher psychologist system; do
    echo "=== Interviewing $role ==="
    python3 ~/hermes0/scripts/spawn-agent.py $role "Generate 3 interview questions for Steve"
    # Wait for Steve's answers
    # Store answers
    # Generate follow-ups
    # Repeat until satisfied
done
```

## Progress Tracking

Track in `~/wiki/sessions/interview-progress.md`:

```markdown
# Interview Progress

| Role | Last Interviewed | Rounds | Key Insights |
|------|-----------------|--------|--------------|
| Philosopher | 2026-04-25 | 2 | Synthesis reflex, qualia ethics |
| Psychologist | 2026-04-25 | 1 | Pattern analysis |
| Researcher | — | 0 | — |
```

## Pitfalls

1. **Don't rush** — Let Steve think through answers. The value is in depth, not speed.
2. **Store immediately** — Don't wait to batch stores. Each insight should be captured right away.
3. **Cross-reference** — Link new interviews to previous ones in wiki.
4. **Respect persona** — Use `spawn-agent.py` for persona injection, not raw delegation.
5. **Max 3 rounds** — Don't let follow-ups spiral. 3 rounds per role is enough for depth.

## Related

- `companion-system-orchestration` — Role definitions and personas
- `spawn-agent.py` — Persona injection script
- `~/wiki/concepts/companion-interview-workflow.md` — Full workflow documentation
- `~/wiki/sessions/` — Interview articles
