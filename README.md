# 🧬 Agent Evolution Lab

> Formerly a fork of `NousResearch/hermes-agent-self-evolution`. This repository is now being shaped into an agent evolution lab: a workbench for improving autonomous-agent skills, tools, prompts, datasets, and evaluation loops from real usage evidence.

**Working thesis:** agents should not be static prompt bundles. They should improve from traces, tests, review comments, bug reports, human corrections, and deployment evidence.

This project uses DSPy + GEPA (Genetic-Pareto Prompt Evolution), constraint gates, session-derived datasets, and regression tests to evolve Hermes Agent artifacts while avoiding fake progress such as ghost improvements, type drift, and metric-only wins.

**No GPU training required.** Everything operates through API/local model calls — mutating text, evaluating results, and selecting variants.

## Direction docs

- [Philosophy](docs/philosophy.md) — the evidence-led agent-improvement thesis
- [Project Direction](docs/project-direction.md) — naming, scope, and fork posture
- [Public Breadcrumb Policy](docs/public-breadcrumb-policy.md) — when/how to tell upstream users about fork fixes
- [Migration Plan](docs/plans/agent-evolution-lab-migration.md) — staged path from fork identity to Agent Evolution Lab

## How It Works

```
Read current skill/prompt/tool ──► Generate eval dataset
                                        │
                                        ▼
                                   GEPA Optimizer ◄── Execution traces
                                        │                    ▲
                                        ▼                    │
                                   Candidate variants ──► Evaluate
                                        │
                                   Constraint gates (tests, size limits, benchmarks)
                                        │
                                        ▼
                                   Best variant ──► PR against hermes-agent
```

GEPA reads execution traces to understand *why* things fail (not just that they failed), then proposes targeted improvements. ICLR 2026 Oral, MIT licensed.

## Quick Start

```bash
# Install this fork/lab branch
git clone https://github.com/steezkelly/hermes-agent-self-evolution.git
cd hermes-agent-self-evolution
pip install -e ".[dev]"

# Point at your hermes-agent repo
export HERMES_AGENT_REPO=~/.hermes/hermes-agent

# Evolve a skill (synthetic eval data)
python -m evolution.skills.evolve_skill \
    --skill github-code-review \
    --iterations 10 \
    --eval-source synthetic

# Or use real session history from Claude Code, Copilot, and Hermes
python -m evolution.skills.evolve_skill \
    --skill github-code-review \
    --iterations 10 \
    --eval-source sessiondb
```

## What It Optimizes

| Phase | Target | Engine | Status |
|-------|--------|--------|--------|
| **Phase 1** | Skill files (SKILL.md) | DSPy + GEPA | ✅ Implemented (16 production runs) |
| **Phase 2** | Tool descriptions | DSPy + GEPA | ✅ Implemented (pipeline complete, added 2026-04-29) |
| **Phase 3** | System prompt sections | DSPy + GEPA | 🔲 Planned |
| **Phase 4** | Tool implementation code | Darwinian Evolver | 🔲 Planned |
| **Phase 5** | Continuous improvement loop | Automated pipeline | 🔲 Partial (ingest_captured CLI) |

## Engines

| Engine | What It Does | License |
|--------|-------------|---------|
| **[DSPy](https://github.com/stanfordnlp/dspy) + [GEPA](https://github.com/gepa-ai/gepa)** | Reflective prompt evolution — reads execution traces, proposes targeted mutations | MIT |
| **[Darwinian Evolver](https://github.com/imbue-ai/darwinian_evolver)** | Code evolution with Git-based organisms | AGPL v3 (external CLI only) |

## Guardrails

Every evolved variant must pass:
1. **Full test suite** — `pytest tests/ -q` must pass 100%
2. **Size limits** — Skills ≤15KB, tool descriptions ≤500 chars
3. **Caching compatibility** — No mid-conversation changes
4. **Semantic preservation** — Must not drift from original purpose
5. **PR review** — All changes go through human review, never direct commit

## Full Plan

See [PLAN.md](PLAN.md) for the original architecture, evaluation data strategy, constraints, benchmarks integration, and phased timeline.

For the fork's current identity and migration path, see:

- [Philosophy](docs/philosophy.md)
- [Project Direction](docs/project-direction.md)
- [Migration Plan](docs/plans/agent-evolution-lab-migration.md)

## License

MIT — © 2026 Nous Research
