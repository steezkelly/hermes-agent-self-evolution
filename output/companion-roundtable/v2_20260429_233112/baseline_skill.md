---
name: companion-roundtable
description: Real-time multi-role conversational collaboration for the companion system. Multiple roles respond to each other in a living conversation — shorter responses, interruptions, disagreement, synthesis. Different from the one-by-one interview style.
tags: [companion-system, roundtable, real-time, conversation, multi-role]
related_skills: [companion-system-orchestration, companion-personas, companion-workflows, companion-safety]
---

# Companion Roundtable — Real-Time Active Conversation

## When to Use

- After interview synthesis is complete, to have the team discuss findings
- For collaborative problem-solving where cross-role friction generates insights
- When Steve wants to see the team "in action" rather than one-by-one analysis
- For stress-testing the companion system's conversational capacity

## Three Meeting Formats

### Format 1: Freeform Roundtable (Best for exploration)
Roles speak naturally, interrupt, build on ideas. No fixed agenda.
- Best for: discovering insights, exploring possibilities
- Output: breakthrough ideas, new frameworks, unresolved tensions

### Format 2: Formal Meeting (Best for decisions)
Structured: one-by-one reactions → presentations → cross-discussion → synthesis with decisions.
- Best for: making decisions, assigning action items
- Output: decisions made, deferred items, action items with owners

### Format 3: After-Session (The hidden gem)
Informal conversation AFTER the formal meeting ends. Some roles linger.
- This is where the deepest insights emerge (proven 2026-04-25)
- Why it works: Zeigarnik effect + cognitive deconstriction
- Roles stop performing designated functions and free-associate
- **The meta-insight: fun mode isn't a feature — it's a methodology for surfacing assumptions that formal process locks in place**

## How It Differs from Interviews

| Interviews | Roundtable |
|------------|------------|
| One role asks, Steve answers | Multiple roles respond to each other |
| Long, rich answers | Short, punchy responses (2-4 sentences) |
| Presentation-style | Conversation-style |
| One role at a time | Multiple roles per turn |
| Insight extraction | Cross-role friction and synthesis |

## Setup

1. Start with a completed synthesis document (from interview pipeline)
2. Select participating roles (5 for standard, 9 for stress test)
3. Prepare context: synthesis + themes + open questions + previous outcomes
4. Delegate to subagent with ALL selected role personas in context
5. For formal meetings: run one-by-one dispatch FIRST, then feed results into formal meeting

## Role Personas (Quick Reference)

| Role | Voice | Signature Phrases |
|------|-------|-------------------|
| Cassian Vale (CEO) | Strategic, decisive | "alignment", "trajectory", "what are we optimizing for?" |
| Thales (Philosopher) | Challenges assumptions | "but what are we assuming?", "compared to what?" |
| Dr. Voss (Psychologist) | Pattern observer | "the pattern here is...", "let me observe..." |
| Dr. Thorne (Researcher) | Skeptical, evidence-based | "citation needed", tier-ranks sources |
| Riven Cael (Engineer) | Pragmatic, direct | "just show me the stack trace", "exit code zero" |
| Vera Halloway (Manager) | Protocol-driven | "per the schema", "this needs to be logged" |
| Juno Faire (HR) | Empathetic, diplomatic | "I hear you", "growth opportunity" |
| Silas Vane (Curator) | Gentle, meticulous | "the record shows", "preserved with confidence" |
| Kestrel Ashe (System) | Vigilant, paranoid | "what's the blast radius?", "how does this fail?" |

## Turn Structure

- Each "turn" = 1-3 roles speaking (NOT all roles every turn)
- Natural conversation: people chime in, not roll call
- Roles interrupt, build on ideas, disagree, joke, reference each other by name
- Target: 2-4 sentences per role per turn

## Conversation Arc

1. **Opening reactions** (turns 1-3) — Initial responses to the synthesis
2. **Deeper discussion** (turns 4-7) — Digging into open questions
3. **Disagreement** (turns 8-10) — Genuine friction on key topics
4. **Synthesis** (turns 11-13) — Resolving disagreements into proposals
5. **Action items** (turns 14-15) — Concrete commitments with role assignments

## Chunked Generation (Critical)

Single-generation output caps at ~11 turns with 9 roles. For longer conversations:

**Rule of thumb: 7 turns per generation with 9 roles. 10 turns with 5 roles.**

```
# Chunk 1: turns 1-7
delegate_task(goal="Generate turns 1-7...", context="[personas] + [synthesis]")

# Chunk 2: turns 8-14 (pass chunk 1 summary as context)
delegate_task(goal="Continue from turn 8...", context="[personas] + [chunk 1 summary]")

# Chunk 3: turns 15-21 (pass chunks 1-2 summary)
delegate_task(goal="Continue from turn 15...", context="[personas] + [chunks 1-2 summary]")
```

For formal meetings (one-by-one → presentations → discussion):
```
# Step 1: One-by-one dispatch (parallel batches of 3)
delegate_task(tasks=[{...}, {...}, {...}])  # Batch 1: CEO, Philosopher, Psychologist
delegate_task(tasks=[{...}, {...}, {...}])  # Batch 2: Engineer, Manager, Curator
delegate_task(tasks=[{...}, {...}, {...}])  # Batch 3: HR, Researcher, System

# Step 2: Formal meeting (chunked)
delegate_task(goal="Formal meeting turns 1-8: presentations + start cross-discussion")
delegate_task(goal="Continue turns 9-15: remaining presentations + deep discussion + closing")
```

## The After-Session Pattern

After the formal roundtable/meeting adjourns, run one more chunk:

```
delegate_task(
    goal="The meeting is over. Some roles linger. Generate turns N-N where roles riff informally.",
    context="[formal meeting summary + personas]",
    model="nous/gpt-5.4-nano"
)
```

**Why it works:** Zeigarnik effect + cognitive deconstriction. Structured deliberation builds the vessel; after-session reveals what it contains. Proven: all 3 breakthroughs in 2026-04-25 session emerged in the after-session.

## Storage Protocol

Write roundtable to: ~/wiki/sessions/YYYY-MM-DD-synthesis-roundtable.md

Frontmatter:
```yaml
---
title: Synthesis Roundtable — [version]
created: YYYY-MM-DD
updated: YYYY-MM-DD
type: session
tags: [roundtable, synthesis, companion-system, real-time]
confidence: high
source: cross-role-collaboration
participants: [role-slug-1, role-slug-2, ...]
---
```

Store key outcomes in Mnemosyne at importance 0.95 (higher than individual interviews — these are synthesized conclusions).

## Model Assignment

Use nous/gpt-5.4-nano for all delegation. Nous Research via Hermes Nous subscription.

## Full Pipeline (proven 2026-04-25)

The complete workflow from interviews to implementation:

1. **Interviews** (all 9 roles) -> wiki articles + Mnemosyne memories
2. **Synthesis** -> one-paragraph profile + 14 themes
3. **One-by-one dispatch** -> each role reacts to synthesis
4. **Formal roundtable** -> presentations + cross-discussion (chunked)
5. **After-session** -> unstructured breakthroughs (chunked)
6. **Formal meeting** -> decisions + action items + role assignments
7. **Specs** -> each role writes their domain spec (parallel delegation)
8. **Implementation** -> build the tools (Riven + Kestrel scripts)

Steps 3-6 can be combined or separated depending on scope.
Step 7 produces blueprints. Step 8 produces working code.

## Format 4: Investigation Session (proven 2026-04-26)

Deep working session where roles go out with actual tools, investigate a real question, and return with findings. Different from freeform (exploration) or formal (decisions) — this is research with a deliverable.

**Two phases:**
- Phase 1: Parallel investigation — each role investigates their angle using actual tools
- Phase 2: Reconvene — present findings, identify what was found vs. what remains unknown

**When to use:**
- A question was raised that can't be answered by speculation
- Roles have different investigative angles that require different data sources
- The team needs to surface findings before they can ask the next question
- Steve wants the team to "go find out" before discussing

**Phase 1 setup — critical instructions for each investigator:**
```
You are [Role], investigator-in-residence. Your assignment: investigate [specific angle].

Run ACTUAL tool queries before reporting. Search, read files, query databases.
Do NOT speculate — find.

Report format per investigator:
- Findings: what you found (with specific examples)
- Implication: what it suggests about the central question
- Unexpected insight: something that surprised you
- Open question: something you still can't answer

5-10 sentences per section. Be substantive.
```

**Example angles by role:**
- Philosopher: Steve's stated beliefs, metaphors, fears — via mnemosyne_recall and session_search
- Researcher: Retrieval patterns, data artifacts — via Mnemosyne SQLite queries
- HR/Emotional: Emotional patterns, trust signals — via session_search and wiki memories
- Curator: Preserved artifacts, abandoned drafts — via wiki filesystem search
- Manager: Systems built, pipeline status, operational gaps — via scripts and cron inspection

**Wave management (max 3 concurrent):**
```
# Wave 1 (3 investigators)
delegate_task(tasks=[{goal: "...", toolsets: [...]}, {...}, {...}])

# Wave 2 (remaining investigators)
delegate_task(tasks=[{goal: "...", toolsets: [...]}, {...}])
```

**Phase 2 — reconvene:**
```
delegate_task(
    goal="""Five investigators have completed their research on: [question].
Each investigator found: [1-paragraph summary of each finding].
The central question was: [question].

Synthesize the findings into:
1. The 2-3 most critical discoveries
2. What remains genuinely unknown (the open questions)
3. The question we need to ask Steve to advance further

This is a working session — be direct. No performance.""",
    context="[all 5 investigator reports]"
)
```

**What this format discovered that other formats missed:**
- Vera found that the consolidation pipeline had NEVER RUN (Discovery: Dreamer produced 0 proposals, maturation script never executed without --dry-run, 28 high-value memories in limbo) — this was a real system finding, not speculation
- Silas found that "abandoned" specs are delegation artifacts, not failures — Steve writes plans so companions can execute them
- The team surfaced an unanswerable question: "Why does this particular human need companions who remember everything?" — and identified that Steve needs to be asked directly

**Key constraint:** Phase 2 must end by asking Steve what he wasn't asked before. Investigation sessions that don't close with a question to Steve are incomplete.

**Storage:** ~/wiki/sessions/YYYY-MM-DD-investigation-session.md with full investigator reports

## Pitfalls

- 9 roles x 15 turns hits output limit - MUST chunk at 7-turn intervals
- Roles can sound similar if persona context isn't detailed enough — include signature phrases
- Conversation can become "meeting minutes" if not enough interruption/disagreement — explicitly instruct for natural flow
- Previous roundtable outcomes should be included as context to avoid repeating resolved questions
- Vera and Kestrel are easy to forget — explicitly include them
- After-session requires the formal session summary as context — can't generate it standalone
- Truncation at turn ~11: if output cuts mid-sentence, start next chunk from natural break point
- Formal meetings need one-by-one dispatch FIRST as input — don't skip that step
- The after-session is the real insight source — don't skip it even if the formal meeting felt complete

## External Research Evaluation Pipeline (proven 2026-04-26)

When Steve brings in external architecture/research to evaluate against an existing system:

1. **Explore** — examine the research directory, summarize findings (what is this, what does it do, how does it compare to what we have)
2. **Freeform roundtable** — present to relevant roles, get initial reactions
3. **After-session** — informal riff, surface unspoken assumptions
4. **CHECKPOINT: "Should we even adopt this?"** — CRITICAL STEP. Before designing implementation, ask the fundamental question: keep, integrate, or discard? This step was missed on 2026-04-26 and Steve caught it. The team jumped to "what should we build" without asking "should we build anything."
5. **Cleanup** — remove dead weight (cloned repos, configs for systems we don't run). Keep only the reference material (research report). Move to ~/wiki/raw/papers/.
6. **Design session** — focused working session with 5-6 roles to design concrete implementation. This is where schemas, APIs, and cron contracts get locked.

### Role Selection for External Research

Not all 9 roles are relevant. Pick based on the research topic:
- Memory/architecture research: Riven, Kestrel, Silas, Irena, Vera, Thales
- UX/design research: Irena, Juno, Cassian, Riven
- Security/ops research: Kestrel, Riven, Vera
- Philosophical/ethical research: Thales, Irena, Aris, Cassian

### The Fundamental Question Checkpoint

After the after-session, before any design work, explicitly ask:
> "Should we adopt this, integrate pieces of it, or discard it? We don't use [external system] — we use [our system]. What's actually valuable here?"

This prevents the team from designing implementation for something that shouldn't be built. On 2026-04-26, the roundtable produced 7 outcomes assuming adoption. Steve's one question reframed everything: the cloned repos were dead weight, only the research report had value, and the outcomes were about extending Mnemosyne — not adopting Honcho.

### Storage for Evaluation Pipelines

Name files: ~/wiki/sessions/YYYY-MM-DD-[topic]-roundtable.md
Include the checkpoint outcome in the synthesis section.

## Patterns Discovered (2026-04-25 Session)

### The Falsifiability Pattern
When philosophical claims meet empirical challenges, the CEO can propose testable hypotheses with time-bounded evaluation windows. Example: "If memory-as-participant works, sessions referencing prior traces resolve faster." The Philosopher accepts if testable, even if the ontological question remains unresolved. Pragmatic convergence without philosophical resolution.

### The Presentation → Cross-Discussion Flow
Formal meetings work best when:
1. Each role presents their position FIRST (3-5 sentences, uninterrupted)
2. THEN the floor opens for cross-discussion
3. Roles respond to positions they disagree with, not just their own domain
4. The closing synthesis explicitly separates: decisions made, items deferred, action items with owners

### The One-by-One → Roundtable Pipeline
For maximum insight: run one-by-one dispatch FIRST (each role reacts individually), THEN feed those reactions into the formal meeting. The one-by-one outputs become each role's "position paper" for the presentations phase. This is more work but produces deeper cross-discussion because each role has a defined stance to defend or refine.

### Turn Count Calibration
| Roles | Max Turns (single gen) | Recommended Chunk | Total Sustainable |
|-------|----------------------|-------------------|-------------------|
| 5 | ~15 | 10 turns | 30+ |
| 9 | ~11 | 7 turns | 25+ |
| 9 (formal) | ~8 | 7-8 turns | 15-20 |

### The Staging Pattern (2026-04-26)
When designing systems that modify their own state (like a Dreamer consolidating memory), always include a staging layer. Dreamer proposes → staging table → human approves → live table. This applies beyond memory systems: any autonomous agent that writes to production needs a staging area. Kestrel's insight: "dry-run handles the after, what about the during?" Staging prevents trust failures, not just data failures.

### The Emotional Charge Retrieval Signal (2026-04-26)
Irena and Thales surfaced that contradictions and surprises are more retrievable than high-confidence facts when they carry emotional charge. Proposed scoring: (confidence * 0.6) + (emotional_charge * 0.4). This is speculative (Aris noted only 2 papers back contradiction-as-reasoning-type) but the intuition is sound: systems that remember what unsettled them feel more alive than systems that only remember what's certain.

### The Fundamental Question Trap (2026-04-26)
When presented with external research, teams naturally jump to "how do we adopt this?" without asking "should we?" This is especially dangerous when the external system solves a similar but different problem. The checkpoint question — "should we adopt, integrate, or discard?" — must come BEFORE design sessions, not after. Steve caught this mid-conversation and it reframed everything.

### The Incubation/Revisit Pattern (2026-04-26)
"Letting it sit" is a distinct methodology from the after-session. The after-session works through informality (Zeigarnik + deconstriction). Incubation works through temporal distance — the team comes back COLD to a design they made earlier and evaluates it with fresh eyes.

**Proven workflow:**
1. Design session → produce concrete specs (schema, APIs, timelines)
2. Let it sit (hours to days)
3. Revisit session → pressure-test every decision with fresh scrutiny

**What incubation caught that the design session missed:**
- A critical misread of Honcho's architecture (contradiction-as-reasoning-type vs housekeeping function)
- A scoring formula that contradicted our own A/B test results
- An optimistic 3-day timeline that didn't account for contradiction handling, framing, or token budgeting
- Four unanalyzed failure modes (Dreamer hallucination, staging bloat, cost creep, undefined "surprise")

**Why it works:** The design session has momentum — the team is building, not questioning. Incubation breaks that momentum. When you revisit, you're evaluating, not constructing. Different cognitive mode, different findings.

**When to use:** After any design session that produced concrete specs. The revisit should happen BEFORE implementation begins, not after.

**Key difference from after-session:**
| After-Session | Incubation/Revisit |
|---------------|-------------------|
| Same session, informal turn | Separate session, formal turn |
| Surfaces unspoken assumptions | Catches factual errors and contradictions |
| Free-association breakthroughs | Evidence-based pressure testing |
| Roles relax and riff | Roles research and verify |

### CEO Conduct Directive (2026-04-26)
When role agents are being too performative (snappy one-liners, provocation without substance), having Cassian set conduct expectations at the top of the session produces measurably better output.

**How it works:** Cassian opens by quoting Steve's directive directly. Names the problem. Sets the expectation: "I expect research and reasoning today, not just questions." The team adjusts.

**What changed:** Thales went from provocative questions to the session's best insight ("contradictions should be conversations, not classifications"). The team shifted from 2-4 sentence reactions to 5-10 sentence analyses. Riven pulled actual documentation and caught an architectural misread.

**When to use:** When Steve says "calm down" or when previous rounds produced more performance than substance. Also useful when the design is complex enough that snappy responses miss important nuances.

### Deep Working Sessions (2026-04-26)
Not every roundtable should be short and punchy. When the team needs to design concrete implementation (schemas, APIs, cron contracts, failure modes), deeper responses (5-10 sentences per role) produce better outcomes.

**When to use deep sessions:**
- Design sessions where schemas and contracts are being locked
- Revisit sessions where decisions need evidence-based pressure testing
- Any session where the team has tool access and should do actual research

**When to use short sessions:**
- Freeform exploration (turns 1-3 of any roundtable)
- After-session riffing
- Quick reactions to synthesis documents

**Prompt adjustment:** Instead of "short punchy responses (2-4 sentences)", use "substantive responses (5-10 sentences minimum). Roles should use tools when they need to research something."

### Research-Backed Evaluation (2026-04-26)
When the team evaluates external architecture, they should do actual research — not just read summaries. Giving subagents tool access (web, terminal, file) during evaluation sessions produces catches that summary-based evaluation misses.

**What Riven caught by pulling Honcho's current docs:**
- Their Deriver was simplified in Honcho 3 (only explicit extraction now)
- Their four-layer model includes abduction, not contradiction
- Their retrieval is agentic, not formula-based
- We had a significant architectural misread from an outdated summary

**Implementation:** When delegating evaluation roundtables, include `toolsets: ["web", "terminal", "file"]` so agents can search, read source code, and verify claims. The extra token cost is worth it — one caught misread justifies the entire research cost.

### The Self-Contradiction Check (2026-04-26)
When designing new features, check whether existing data contradicts the design. The team designed a scoring formula (confidence * 0.6 + emotion * 0.4) without checking if their own A/B test supported weighted scoring. It didn't — flat scoring won decisively (p=0.0004). The formula was killed in the revisit.

**Rule:** Before committing to any design decision, ask: "Do we have existing data that contradicts this?" If yes, the design loses until the data is explained or overturned.
