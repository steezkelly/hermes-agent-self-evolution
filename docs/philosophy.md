# Agent Evolution Lab Philosophy

Agent Evolution Lab is not just a prompt optimizer.

It is a workbench for building agents that can improve from evidence: usage traces, failures, review comments, tests, metrics, datasets, and human corrections.

The philosophical shift is from "make a skill better once" to "build an instrumented improvement loop that can tell when an agent actually got better."

## Core thesis

Agents should not be treated as static prompt bundles.

A useful agent system has living procedural memory:

- skills that change when reality proves them wrong
- tools whose descriptions improve from observed misuse
- datasets mined from real tasks, not only synthetic examples
- tests and gates that prevent fake progress
- public breadcrumbs so other users can benefit from fixes
- a single evidence trail connecting bug, fix, metric, and release

## What changed from the upstream seed

The upstream project is named `hermes-agent-self-evolution` and focuses on DSPy + GEPA optimizing Hermes Agent artifacts.

This fork keeps that lineage but expands the focus:

- from isolated skill files to skills, tools, prompts, datasets, traces, and release gates
- from "GEPA made a score go up" to "can we prove a behavior improved?"
- from synthetic-only evals to real-session capture and dataset enrichment
- from opaque optimizer runs to reproducible evidence logs
- from upstream-dependent progress to a downstream lab with its own direction

## Operating principles

### 1. Evidence before enthusiasm

Every claimed improvement should have at least one of:

- a failing test that now passes
- a metric table with baseline/candidate comparison
- a minimized reproduction
- a linked commit and verification command
- a before/after artifact diff
- a real task trace showing changed behavior

If there is no evidence, call it a hypothesis, not a result.

### 2. No ghost improvements

An optimizer score is not enough.

The system must prove the deployed artifact changed in the intended location and preserved its purpose. If the evaluator improves while the artifact stays the same, that is a bug, not success.

### 3. Preserve purpose, improve procedure

Evolution should make an artifact better at its job, not silently change the job.

A code-review skill should become a better code-review skill, not a generic consultant prompt. A deployment skill should become safer and more complete, not more verbose and less operational.

### 4. Public breadcrumbs, not spam

When the fork fixes a bug that upstream users are discussing, leave a targeted comment with:

- the exact issue addressed
- a link to the fix
- the verification command/result
- a clear note if the behavior is fork-local

Do not post generic fork promotion.

### 5. Fork main is the lab; upstream PRs are narrow

The fork's `main` branch can carry broad experiments, datasets, docs, and generated artifacts.

Upstream PRs should be made from small branches based on `upstream/main`, each containing one reviewable fix.

### 6. Prefer boring gates over clever demos

A boring gate that catches false progress is more valuable than a flashy optimizer demo. Tests, constraints, reproducibility, and audit trails are the product.

### 7. Human taste remains part of the loop

The system can propose, score, and validate improvements, but human review decides what counts as better. The lab should reduce review burden, not pretend review disappeared.

## Product direction

Agent Evolution Lab should become a practical system for:

1. capturing real agent work
2. converting useful traces into evaluation datasets
3. proposing artifact improvements
4. testing candidates against behavioral gates
5. recording evidence
6. shipping narrow improvements into live agent systems
7. publishing useful fixes back to affected communities

## Name stance

Working project name: `agent-evolution-lab`

Current GitHub repository remains `steezkelly/hermes-agent-self-evolution` until the README, docs, issues, and links fully support the new identity.

## One-line positioning

An experimental workbench for evolving autonomous-agent skills, tools, prompts, datasets, and evaluation loops from real usage evidence.
