# GEPA v2 Kanban Board

**Last updated:** 2026-04-30
**Total skills:** 15

---

## DEPLOYED (1)

- **companion-interview-workflow** — Δ=0.0000 best=0.1134 runs=4 [high] eval=golden

## VALIDATING (1)

- **mnemosyne-self-evolution-tools** — Δ=0.0717 best=0.0717 runs=1 [medium] eval=golden [`PASSED`]

## REGRESSION (1)

- **companion-workflows** — Δ=0.0000 best=0.0000 runs=4 [high] eval=golden [`regr=2`]

## BACKLOG (8)

- **hermes-agent** — Δ=0.0000 best=0.0000 runs=11 [high] eval=synthetic
- **ceo-orchestration** — Δ=0.0267 best=0.0267 runs=3 [medium] eval=synthetic [`recent`]
- **companion-system-orchestration** — Δ=0.0000 best=0.0000 runs=5 [medium] eval=synthetic [`recent`]
- **companion-interview-pipeline** — Δ=0.0000 best=0.0000 runs=4 [low] eval=synthetic [`recent`]
- **companion-memory** — Δ=0.0000 best=0.0000 runs=2 [low] eval=synthetic [`recent`]
- **companion-safety** — Δ=0.0000 best=0.0000 runs=3 [low] eval=synthetic [`recent`]
- **mnemosyne-maintenance** — Δ=0.0000 best=0.0000 runs=3 [low] eval=synthetic [`recent`]
- **systematic-debugging** — Δ=0.0000 best=0.0000 runs=6 [low] eval=synthetic

## STALE (4)

- **companion-memory-tiers** — Δ=0.0000 best=0.0000 runs=2 [low] eval=golden
- **companion-personas** — Δ=0.0000 best=0.0000 runs=2 [low] eval=golden
- **companion-roundtable** — Δ=0.0059 best=0.0000 runs=2 [low] eval=golden
- **github-code-review** — Δ=0.0000 best=0.0000 runs=3 [low] eval=sessiondb [`regr=1, PASSED`]

---
## Summary

- DEPLOYED: 1
- VALIDATING: 1
- REGRESSION: 1
- BACKLOG: 8
- STALE: 4

---
## Notes

- plateau = holdout delta 0.000 (synthetic improvement candidate but no holdout confirmation)
- REGRESSION = genuine holdout regression or collapse from golden baseline
- golden = curated eval set; synthetic = LLM-generated test cases
