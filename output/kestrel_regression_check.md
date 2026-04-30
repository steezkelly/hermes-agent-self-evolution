# Kestrel Regression Check Report

**Generated:** 2026-04-29 21:06:33

## Summary

| Skill | Original Baseline | Current Evolved | Change vs Original | Status |
|-------|------------------|-----------------|-------------------|--------|
| companion-memory | 0.6263 | 0.5481 | -0.0782 | REGRESSION |
| companion-safety | 0.5651 | 0.6194 | +0.0543 | IMPROVEMENT |
| companion-interview-pipeline | 0.5808 | 0.5859 | +0.0051 | NO_REGRESSION |

## Detailed Results

### companion-memory

- **Status:** REGRESSION
- **Eval Source:** golden
- **Original Baseline Score:** 0.6263
- **Current Evolved Score:** 0.5481
- **Change:** -0.0782 (-7.82%)
- **Note:** Evolution pipeline could not improve over original baseline; current best is lower than original

### companion-safety

- **Status:** IMPROVEMENT
- **Eval Source:** golden
- **Original Baseline Score:** 0.5651
- **Current Evolved Score:** 0.6194
- **Change:** +0.0543 (+5.43%)
- **Note:** Evolution improved the skill by 5.43%

### companion-interview-pipeline

- **Status:** NO_REGRESSION
- **Eval Source:** golden
- **Original Baseline Score:** 0.5808
- **Current Evolved Score:** 0.5859
- **Change:** +0.0051 (+0.51%)
- **Note:** Small improvement but below 1% threshold - no significant regression

## Methodology

- Read original baseline metrics from `output/<skill>/*/metrics.json`
- Ran v2_dispatch with golden data (10 iterations, minimax/minimax-m2.7)
- Compared evolved best_score against original baseline_score
- Thresholds: >+1% = IMPROVEMENT, <-1% = REGRESSION, else NO_REGRESSION

## Run Details

### companion-memory
- Original run: 20260427_220339 (synthetic eval, baseline_score=0.6263, evolved_score=0.6013)
- Current run: v2_20260429_210632 (golden eval, baseline=0.468, evolved=0.548)
- Pareto rejected evolved variants in all 3 attempts

### companion-safety
- Original run: 20260428_013007 (golden eval, baseline_score=0.5651, evolved_score=0.5392)
- Current run: v2_20260429_210632 (golden eval, baseline=0.559, evolved=0.619)
- Pareto rejected evolved variants in all 3 attempts

### companion-interview-pipeline
- Original run: 20260428_013608 (golden eval, baseline_score=0.5808, evolved_score=0.5527)
- Current run: v2_20260429_210633 (golden eval, baseline=0.505, evolved=0.586)
- Pareto rejected evolved variants in all 3 attempts