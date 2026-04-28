---
name: systematic-debugging
description: "4-phase root cause debugging: understand bugs before fixing."
version: 1.1.0
author: Hermes Agent (adapted from obra/superpowers)
license: MIT
metadata:
  hermes:
    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    related_skills: [test-driven-development, writing-plans, subagent-driven-development]
---

# Systematic Debugging Skill - Evaluation Task

## Task Description

You are evaluating agent statements and actions against the systematic debugging skill. For each input, you must:

1. **Identify violations** - Pinpoint which specific principles, phases, red flags, or rationalizations from the skill are being violated
2. **Provide corrected response** - Write what the agent SHOULD say/do that aligns with the systematic debugging skill
3. **Explain the reasoning** - Connect each correction back to specific skill principles

## Response Structure

For each evaluation, provide:

### 1. Violations Identified
- Quote the exact violating statement or describe the violating action
- Cite the specific skill principle being violated (include section names, quotes, or red flags)
- Explain WHY this violates the principle

### 2. Corrected Response
- Write the specific statement(s) or action(s) the agent should take instead
- Ground each correction in the skill's phases or principles
- Include concrete next steps aligned with the systematic approach

### 3. Reasoning Summary
- Brief explanation of why the corrected approach follows the skill
- Include relevant statistics or principles from the skill (e.g., first-time fix rates, Iron Law)

## Critical Principles to Enforce

### The Iron Law
> NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST

Any statement proposing fixes before investigation violates this core principle.

### Phase Order Enforcement
- Phase 1 (Root Cause Investigation) MUST complete before Phase 2
- Phase 4 Step 1 requires: "Create Failing Test Case — MUST have before fixing"
- Never skip phases, even when agent claims confidence in the solution

### Red Flags Requiring STOP
Apply to statements containing:
- "Quick fix" or "investigate later" mindset
- Guessing rather than investigating
- Multiple changes bundled together
- "I know exactly what's wrong" without evidence
- Skipping tests with "I'll verify manually"
- Proposing solutions before tracing data flow
- "One more fix attempt" after multiple failures
- Each fix revealing problems in different places (→ architectural issue)

### Common Rationalizations Table
When you see rationalizations from this table, flag them:

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |

## Domain-Specific Facts to Reference

### Skill Statistics
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate with process: ~95%
- First-time fix rate without process: ~40%

### Phase Completion Criteria
**Phase 1 must achieve:**
- [ ] Error messages fully read and understood
- [ ] Issue reproduced consistently
- [ ] Recent changes identified and reviewed
- [ ] Evidence gathered (logs, state, data flow)
- [ ] Problem isolated to specific component/code
- [ ] Root cause hypothesis formed

**Phase 2 must achieve:**
- [ ] Working examples located
- [ ] Differences from broken code identified
- [ ] Dependencies understood

### Phase 4 Step 5 - When 3+ Fixes Failed
Pattern indicating architectural problem:
- Each fix reveals new shared state/coupling in a different place
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and question fundamentals with the user**

## Evaluation Approach

1. **Read the task_input carefully** - What did the agent say or do?
2. **Map violations to skill sections** - Quote specific principles violated
3. **Write the corrected response** - Model what a skill-compliant agent would say/do
4. **Apply the full process** - Show how the agent should have followed Phase 1 → 2 → 3 → 4

## Output Format for Each Evaluation

### Violations Identified
[List each violation with skill citation and explanation of why it violates the principle]

### Corrected Response
[What the agent SHOULD say/do, including specific actions aligned with the appropriate phase]

### Reasoning Summary
[Brief explanation connecting to skill principles and statistics]

## Scoring Criteria

Your evaluation will be scored on:
- **Completeness**: All violations identified, not just the most obvious one
- **Precision**: Exact quotes from task_input matched to exact skill principles
- **Corrected Response Quality**: Specific, actionable guidance that follows the skill's phase structure
- **Reasoning Quality**: Connection to Iron Law, statistics, and phase order enforcement
