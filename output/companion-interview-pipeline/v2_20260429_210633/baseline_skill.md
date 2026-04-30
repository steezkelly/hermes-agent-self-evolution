---
name: companion-interview-pipeline
description: Interview pipeline where each of the 9 companion roles asks Steve questions about broad topics. Insights stored in Mnemosyne + wiki, building a richer collective personality. Run single roles or full pipeline.
tags: [interview, companion-system, personality, workflow]
related_skills: [companion-system-orchestration, companion-interview-workflow, companion-memory, companion-personas]
---

# Companion Interview Pipeline

## When to Use
- Steve wants to be interviewed by a companion role
- Building collective personality/knowledge for the team
- Exploring Steve's values, thinking patterns, or domain-specific preferences

## Quick Start (Single Role)

```bash
# 1. Generate questions
python3 ~/hermes0/scripts/spawn-agent.py <role> "Generate 2 interview questions for Steve about <topic>"

# 2. Delegate with persona + model override
delegate_task(
    goal="Generate 2 interview questions for Steve about <topic>",
    context="<persona context from spawn-agent.py output>",
    model="<role's model from spawn-agent.py>",
    toolsets=["<role's toolsets>"]
)

# 3. Present questions to Steve

# 4. After Steve answers, store in Mnemosyne
mnemosyne_remember(content="[Role] interview: [topic] — [insight]", importance=0.9, scope="global", source="insight")

# 5. Write Obsidian article to ~/wiki/sessions/YYYY-MM-DD-<role>-interview.md

# 6. Delegate to Psychologist for pattern analysis + follow-up questions
delegate_task(
    goal="Analyze Steve's answers and generate 3 follow-up questions",
    context="<Steve's answers + persona context>",
    model="xiaomi/mimo-v2.5-pro",
    toolsets=["web"]
)

# 7. Repeat until role is satisfied (max 3 rounds)
```

## Role Model Assignments

| Role | Model | Toolsets |
|------|-------|----------|
| CEO, Philosopher, Psychologist | xiaomi/mimo-v2.5 | file / web / web |
| Manager, HR, Curator | xiaomi/mimo-v2.5 | file / file / web |
| Researcher, Engineer, System | xiaomi/mimo-v2.5 | web / terminal+file / terminal+file |

**NOTE:** Use mimo-v2.5 for all delegation. mimo-v2.5-pro costs 2x for "little gain." Minimax may be unavailable - fallback to mimo-v2.5.

## Question Count
- Default: 2 questions per round (Steve's answers run long)
- Follow-ups: 3 questions from Psychologist
- Max rounds per role: 3

## Storage Protocol

### Mnemosyne
```
mnemosyne_remember(
    content="[Role] interview: [topic] — [key insight]",
    importance=0.9,
    scope="global",
    source="insight"
)
```

### Triples
```
mnemosyne_triple_add(
    subject="Steve",
    predicate="[domain]-[type]",
    object="[insight]"
)
```

### Wiki
```
~/wiki/sessions/YYYY-MM-DD-[role]-interview.md
```

Frontmatter required:
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

### Progress Tracker
Update `~/wiki/sessions/interview-progress.md` after each role interview.

## Interviewed Roles (as of 2026-04-25)
- Philosopher (2 rounds) — done
- Psychologist (1 round) — done
- Researcher (1 round) — done
- Engineer (1 round) — done
- Manager (1 round) — done
- HR (1 round) — done
- CEO (1 round) — done
- Curator (1 round) — done
- System (1 round) — done

ALL 9 ROLES COMPLETE — first round finished 2026-04-25.

## Post-Interview: Synthesis

After all 9 roles complete first round:

1. Read all 9 interview wiki articles
2. Write synthesis document: ~/wiki/sessions/YYYY-MM-DD-interview-synthesis.md
   - "Steve in one paragraph" summary
   - Core identity pillars (cross-role themes)
   - Behavioral tendencies table
   - All cross-cutting themes numbered
   - Open questions for the team
3. Store in Mnemosyne at importance 0.9
4. Add knowledge graph triples for key insights

## Post-Interview: Roundtable (Conversational Collaboration)

See skill: companion-roundtable for the real-time multi-role conversation mode.

Quick version:
- Pick 5-9 roles for the roundtable
- Delegate to subagent with all personas + synthesis context
- 15-turn target with 9 roles requires CHUNKED GENERATION (7-turn segments)
- Single-generation output limit is ~11 turns with 9 roles
- Write roundtable to ~/wiki/sessions/YYYY-MM-DD-synthesis-roundtable.md
- Store key outcomes in Mnemosyne at importance 0.95

## Pitfalls
- spawn-agent.py output includes line numbers from read_file — strip them before writing back
- delegate_task model override patch is in delegate_tool.py — reapply after Hermes updates
- Persona injection requires passing the full CHARACTER INSTRUCTION block in context
- Steve's answers are long and rich — 2 questions is the sweet spot
