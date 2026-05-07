# Project Direction: Agent Evolution Lab

This fork started as `NousResearch/hermes-agent-self-evolution`, but the active work is now broader than the upstream seed project.

The fork is becoming an experimental workbench for evolving autonomous-agent skills, tools, prompts, datasets, and evaluation loops from real usage evidence.

## Current repository

Current URL:

https://github.com/steezkelly/hermes-agent-self-evolution

Current working description:

Agent evolution lab: evolve autonomous-agent skills, tools, prompts, datasets, and evaluation loops from real usage evidence.

## Why this is more than a fork

The fork now includes substantial work across:

- GEPA/DSPy skill evolution pipeline hardening
- ghost-improvement prevention and extraction fixes
- validation and deploy gates
- dataset generation and enrichment flows
- captured-session ingestion
- metrics/debugging scripts
- fork-local test stabilization
- companion/orchestration planning hooks
- targeted public breadcrumb comments back to upstream issues when fixes are directly relevant

Latest verified baseline at the time this direction note was created:

- commit: `a7117d25e1dbcc0462d69b8b117d4b1c0ff9cb5c`
- command: `pip install -e '.[dev]' && pytest -q`
- result: `266 passed, 11 warnings`

## Public communication policy

It is useful and allowed to tell others about the fork when the comment is directly relevant to an issue or PR.

Default rule: comment only when the reader of that specific issue would save time from the information.

See [Public Breadcrumb Policy](public-breadcrumb-policy.md) for the full policy and comment template.

## Philosophy

Agent Evolution Lab is not just a prompt optimizer. It is a workbench for building agents that can improve from evidence: usage traces, failures, review comments, tests, metrics, datasets, and human corrections.

See [Agent Evolution Lab Philosophy](philosophy.md) for the full philosophy shift.

## Rebrand candidates

### 1. agent-evolution-lab

Clear, broad, understandable. Best if the repo becomes a general-purpose experimental workbench for autonomous agent improvement.

### 2. hermes-evolution-lab

Keeps Hermes lineage explicit. Best if discoverability from Hermes users matters more than broad positioning.

### 3. companion-evolution-lab

Better if the end product becomes persistent companion improvement rather than just skill/tool optimization.

### 4. autopoiesis-lab

Systems-theoretic and distinctive: self-creation/self-maintenance. Strong identity, weaker immediate discoverability.

### 5. skillforge

Short and memorable. Focuses on skill generation/optimization, but may understate data/eval/orchestration work.

### 6. evolvable-agents

Direct and search-friendly. Frames the project as infrastructure for agents that improve over time.

## Current recommendation

Use `agent-evolution-lab` unless there is a strong reason to retain Hermes in the repository name.

Suggested positioning:

> An experimental workbench for evolving autonomous-agent skills, tools, prompts, datasets, and evaluation loops from real usage evidence.

## Migration plan

1. Keep the current fork URL while the README and docs explain the broader scope.
2. Add a top-of-README note describing the fork's new direction.
3. Use targeted upstream issue comments only when a fix/workaround directly applies.
4. After the name and positioning feel stable, rename the GitHub repo.
5. Keep narrow upstream-compatible fixes on branches based on `upstream/main`; keep broad fork evolution on fork main.

## Non-goals

- Do not spam upstream with generic fork promotion.
- Do not present fork experiments as upstream-supported behavior.
- Do not rename before the repo itself explains what it has become.
