# Roadmap

## Completed

### Foundation (merged to `main`)

| Milestone | When | What |
|-----------|------|------|
| Active trunk | 2026-05-09 | Consolidated evolution gates, constraint validators, GEPA/DSPy integration, fitness scoring, benchmark gates — all from the upstream split stack (PRs #55-#61) into one mergeable unit (#8) |
| Repo structure | 2026-05-09 | Moved one-off runners into `scripts/`, archived stale experiments, added kanban sync bridge between GEPA's custom board and Hermes built-in kanban (#2, #3) |
| Documentation | 2026-05-09 | Technical documentation covering skill evolution, constraints, dataset building, and pipeline architecture (#4) |
| Diagnostics + batches | 2026-05-09 | Metric discrimination diagnostics to detect ghost improvements; batch GEPA dataset operations for multi-skill runs (#5, #6) |

### Fixture demos (deterministic failure detectors)

Each demo proves a failure class exists before attempting to fix it:

| Demo | When | Failure class | PR |
|------|------|--------------|----|
| Action-router | 2026-05-09 | Agent produces long strategic briefing instead of concise action queue with ready-to-paste prompts | #11 |
| Session-import | 2026-05-09 | Agent fails to import and normalize external session transcripts | #12 |
| Tool-underuse | 2026-05-09 | Agent gives verbose prose instead of using available CLI tools | #13 |
| Skill-drift | 2026-05-09 | Evolved skill text drifts from its original purpose | #14 |

All four demos pass deterministically. Baseline fails on the target failure class;
candidate detects/improves it.

### Evidence loop (real-trace pipeline)

| Module | When | What | PR |
|--------|------|------|----|
| Real-trace ingestion | 2026-05-09 | Converts live Hermes session JSONL into structured eval examples with LLM-judge scoring. Supports `--no-network --no-external-writes` safety flags | #15 |
| Attention-router bridge | 2026-05-09 | Converts ingestion findings into bucketed action items (`needsSteve`, `autonomous`, `blocked`, `stale`) with ready-to-paste next_prompt per item | #16 |
| Pipeline runner | 2026-05-09 | Unified CLI: runs all 4 fixture demos (fixture mode) or real-trace ingestion + attention bridge (real_trace mode). Emits aggregated `pipeline_run.json` with verdict, metrics, and safety block | #17 |

### Bootstrap appliance (hermes-bootstrap repo)

| Component | When | What |
|-----------|------|------|
| Fixture wrappers | 2026-05-09 | NixOS `writeShellApplication` + systemd services for all 4 fixture demos, real-trace ingestion, and session-import — all manual/default-off, fail-closed |
| Session-end chain | 2026-05-09 | `hermes sessions export` → temp JSONL → Foundry real-trace ingest → attention-router bridge. Manual/default-off only. Validator checks mechanical output boundaries (#31) |
| Phase 2 delivery | 2026-05-09 | ntfy-based delivery brief dry-run validated. Live send confirmed (single receipt). Opt-in/default-off NixOS timer validated — timer only activates when explicitly configured |

### Test infrastructure

- **360 tests** passing (full suite, including all fixture demos, ingestion, bridge, pipeline runner, constraints, fitness, dataset builder, evolution gates)
- All tests deterministic: no network, no external state, no flaky dependencies
- Warnings are DSPy deprecation noise (`prefix` in `InputField`/`OutputField`) — not regressions

---

## Next

### Immediate (in progress or blocked)

| Item | Status | Notes |
|------|--------|-------|
| GEPA observatory + content evolution | CONFLICTING | PR #1 — 25 files, needs merge resolution against current `main`. Adds section-level evolution, ROI tracking, calibrator, health checks, appeals system |
| Cross-session coordination | Active | 4 sessions working on this repo simultaneously. Needs clear lanes and merge ordering |
| Documentation | Active | CONTRIBUTING.md, ARCHITECTURE.md, ROADMAP.md (this PR). More needed: honest README rewrite, contributor landing page |

### This quarter

| Item | Why |
|------|-----|
| Live NixOS drill | Run the full stack on an actual NixOS machine: session export, real-trace ingestion, attention-router bridge, action queue generation. Prove the chain works end-to-end outside unit tests |
| Multi-skill evolution batch | Run GEPA optimization across multiple skills in one batch. Compare per-skill holdout deltas. Report skipped/failed reasons. Establish whether the pipeline produces real yield or just variance |
| Bootstrap promotion path hardening | Wire pipeline_runner output into the bootstrap promotion path. Validate that `pipeline_run.json → action_queue.json → promotion_dossier.md` flows through without semantic drift |
| Cross-session action queue | When multiple sessions produce action items, merge/dedupe into a single sorted queue. Avoid duplicate work and conflicting prompts |

---

## Stretch

### Medium-term

| Item | Why |
|------|-----|
| Upstream contribution path | Identify narrow, non-fork-specific fixes from this lab that should go upstream to `NousResearch/hermes-agent-self-evolution`. Create small branches from `upstream/main` |
| Plugin architecture | Let contributors add custom failure detectors without touching `pipeline_runner.py`. Register via discovery pattern |
| Continuous improvement loop | Scheduled evolution cycles: cron triggers ingest → detect → optimize → gate → report → draft PR. Currently manual; path to automation is clear |
| Dashboard / control-plane surfaces | From eventlog projections (already spec'd in hermes-agent skill references). Show live pipeline health, gate results, action queue status |

### Long-term (speculative, not committed)

| Item | Notes |
|------|-------|
| Real-task outcome measurement | Close the gap between "LLM judge likes this text" and "agent actually succeeded at the task." Requires production instrumentation that doesn't exist yet |
| Multi-project evolution | Skills that improve across different Hermes instances and projects. Requires cross-instance trace sharing and federated eval |
| Tool implementation evolution | Beyond text descriptions — evolve actual tool code. Higher risk, requires Darwinian Evolver integration and very strong test guardrails |

---

## How to read this roadmap

- **Completed** — merged to `main`, tests passing, verified
- **Next** — actively being worked or blocked on a known issue
- **Stretch** — planned but not started; depends on earlier milestones

Items move from stretch to next when: a clear acceptance criterion exists, the
dependency is resolved, and someone is actively working on it.

The roadmap is a living document. It changes as evidence accumulates.
