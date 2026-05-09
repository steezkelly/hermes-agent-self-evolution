# Architecture

Agent Evolution Lab is part of a three-part system. This document describes
how those parts fit together and what lives in this repository.

## Three-part architecture

```
                          ┌──────────────────────────────┐
                          │       HERMES AGENT           │
                          │       (NousResearch)         │
                          │                              │
                          │  Runtime / trace producer    │
                          │  - Skills, tools, memory     │
                          │  - Session transcripts       │
                          │  - Cron, gateway, delegation │
                          │  - Trajectory export         │
                          └──────────┬───────────────────┘
                                     │
                                     │ session JSONL,
                                     │ skill text,
                                     │ tool descriptions
                                     ▼
┌────────────────────────────────────────────────────────────┐
│                   AGENT EVOLUTION LAB                      │
│                   (this repo)                              │
│                                                            │
│  Evidence loop / auditable improvement                     │
│  - Trace ingestion & normalization                         │
│  - Failure detection (fixture demos)                       │
│  - Attention routing (signal → action item)                │
│  - Eval dataset building                                   │
│  - GEPA/DSPy skill optimization                            │
│  - Constraint gates (tests, size, growth, structure)       │
│  - Pipeline orchestration & reporting                      │
│  - PR draft generation (manual merge required)             │
└──────────┬─────────────────────────────────────────────────┘
           │
           │ action_queue.json,
           │ promotion_dossier.md,
           │ artifact_manifest.json
           ▼
┌──────────────────────────────┐
│     HERMES-BOOTSTRAP         │
│     (steezkelly)             │
│                              │
│  Appliance / habitat         │
│  - NixOS modules             │
│  - systemd oneshots/timers   │
│  - Users, permissions, paths │
│  - Retention, fail-closed    │
│  - Boundary validators       │
│  - Manual/default-off only   │
└──────────────────────────────┘
```

### Who owns what

| Component | Owns | Does NOT own |
|-----------|------|--------------|
| **Hermes Agent** | Runtime, tools, skills, memory, cron, gateway, delegation, session/trace export, artifact version stamping | Evidence semantics, improvement decisions, mutation logic |
| **Agent Evolution Lab** (this repo) | Trace ingestion, normalization, redaction, eval generation, holdouts, candidates, gates, diagnostics, reports, action queue generation, promotion dossiers | Live agent behavior, production deploys, credential management |
| **Hermes-Bootstrap** | NixOS/systemd wrapper, permissions, directories, retention, default-off/manual services, local invocation, fail-closed boundary validation | Evidence semantics, queue ranking, promotion dossier wording, mutation/gate logic |

The rule: if a component decides what improvement means, what counts as
regression, how action items are ranked, or what text belongs in a promotion
dossier — that component is the Evolution Lab.

## Module inventory

### Failure detectors (fixture demos)

Each module detects one class of agent failure. They follow the baseline-vs-candidate
pattern: baseline fails on the target failure, candidate detects/improves it.

| Module | Detects | Output |
|--------|---------|--------|
| `action_routing_demo.py` | Agent produces long strategic briefing instead of concise action queue with ready-to-paste prompts | `run_report.json` |
| `session_import_demo.py` | Agent fails to import and normalize external session transcripts | `run_report.json` |
| `tool_underuse_demo.py` | Agent gives verbose prose instructions instead of using available CLI tools | `run_report.json` |
| `skill_drift_demo.py` | Evolved skill text drifts from its original purpose | `run_report.json` |

### Ingestion and bridge

| Module | What it does |
|--------|-------------|
| `real_trace_ingestion.py` | Converts live Hermes session JSONL into structured eval examples with LLM-judge scoring |
| `attention_router_bridge.py` | Converts ingestion findings into action items bucketed by: `needsSteve`, `autonomous`, `blocked`, `stale` |
| `external_importers.py` | Reads Claude Code, Copilot, and other external session sources |

### Optimization engine

| Module | What it does |
|--------|-------------|
| `evolve_skill.py` | Main GEPA/DSPy skill evolution entry point. Wires dataset builder, fitness metric, constraint gates, pytest gate, holdout gate, baseline validation, and run report |
| `fitness.py` | LLM-judge rubric-based fitness scoring for skill variants |
| `dataset_builder.py` | Synthetic eval dataset generation + golden dataset loading |
| `constraints.py` | Constraint validator: test suite gate, size limits, growth limits, structural checks |
| `constraints_v2.py` | Extended constraint validator with sklearn-based semantic preservation checks |
| `benchmark_gate.py` | Programmable promotion gate with configurable thresholds and optional benchmark commands |

### Pipeline and reporting

| Module | What it does |
|--------|-------------|
| `pipeline_runner.py` | Unified CLI orchestrator: runs all fixture demos (fixture mode) or real-trace ingestion + attention bridge (real_trace mode), aggregates into `pipeline_run.json` |
| `run_report.py` | Standardized `run_report.json` artifact with schema_version, baseline/candidate blocks, safety flags |
| `pr_builder.py` | Generates draft PR body from evolution results |

### Cross-cutting

| Module | What it does |
|--------|-------------|
| `config.py` | Evolution configuration (paths, model settings, gate thresholds) |
| `types.py` | Shared type definitions |
| `nous_auth.py` | Nous API authentication routing |
| `router.py` | Provider/model dispatch routing |
| `gepa_v2_dispatch.py` | GEPA optimizer version dispatch |
| `evolve_skill_v2.py` | Evolution pipeline v2 with plugin architecture |
| `pareto_selector.py` | Multi-objective variant selection |
| `posthoc_analyzer.py` | Post-evolution statistical analysis |
| `backtrack.py` | Evolution backtrack/rollback support |

## Data flow

```
┌──────────────────────┐
│  Hermes session      │   hermes sessions export → session.jsonl
│  (or fixture trace)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  real_trace_         │   Parse JSONL, redact secrets,
│  ingestion.py        │   generate eval_examples.json
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  attention_router_   │   Classify findings into buckets,
│  bridge.py           │   emit action_queue.json with
│                      │   ready-to-paste next_prompt per item
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  pipeline_runner.py  │   Aggregate all reports into
│                      │   pipeline_run.json with verdict,
│                      │   metrics, safety block
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Steve               │   Reviews action items,
│  (human)             │   decides what to do next
└──────────────────────┘
```

For fixture mode, the data flow is simpler: each of the 4 fixture demos runs
independently against deterministic trace fixtures, pipeline_runner aggregates
their run_report.json files, and the combined pipeline_run.json confirms
all detectors pass.

## The compounding loop

The Evolution Lab is built around a small compounding loop:

```
one repeated failure → one eval → one better artifact → one measured win → one manual promotion
```

This is not a "closed learning loop" in the RL sense — there are no gradient
updates, no policy gradients, no learned reward models. It is a **prompt
optimization pipeline with auditable improvement gates**.

What makes it compound:

1. **Fixtures capture failures** — deterministic trace-based demos prove a failure
   class exists before we try to fix it
2. **Ingestion builds evidence** — real-trace ingestion converts live sessions into
   structured eval examples
3. **Bridges produce action items** — attention-router bridge turns raw findings
   into bucketed, prioritized, ready-to-paste prompts
4. **Gates prevent fake progress** — constraint validator, pytest gate, benchmark
   gate, holdout gate all must pass before promotion
5. **Manual promotion closes the loop** — a human decides whether the candidate
   artifact is actually better than baseline

The differentiator is **auditable improvement**, not self-improving agent behavior.
Hermes Agent already owns agent behavior. This lab owns the question: "can we prove
this change made the agent better at its job?"

## Safety model

Every module enforces these invariants:

- `--no-network --no-external-writes` required on every CLI entry point
- Fail-closed: missing a safety flag → nonzero exit
- All writes confined to `--out` directory
- `run_report.json` safety block explicitly declares `network_allowed: false`,
  `external_writes_allowed: false`, `github_writes_allowed: false`,
  `production_mutation_allowed: false`
- No credential access, no `.env` reads, no `config.yaml` scraping
- No auto-deploy — human always makes the final merge decision
