---
name: mnemosyne-self-evolution-tools
description: Build standalone diagnostic tools for Mnemosyne using Python stdlib only — snapshot-based trend tracking, quality scoring, and comprehensive test suites. Use when creating tools that monitor, report on, or evolve the Mnemosyne memory system.
tags: [mnemosyne, python, diagnostics, testing, self-evolution]
category: companion-system
---

# Background Process Completion Analyzer

## Task Overview

You will receive notifications about background processes that have completed. Your job is to analyze these completions and provide structured, informative summaries.

## Input Format

```
[IMPORTANT: Background process proc_<ID> completed (exit code <N>).
Command: <command_string>
Output:
<output_content>
]
```

## Key Components to Extract

1. **Process ID**: Unique identifier (e.g., `proc_b4c6e5befb2e`)
2. **Exit Code**: Numeric code indicating termination status
   - `0` = Success
   - `1` = General error/failure
   - `-15` = SIGTERM (process was terminated/killed)
   - Other negative codes = killed by signal
3. **Command**: The original command that was run (extract skill name, iterations, parameters)
4. **Output**: The stdout/stderr from the process

## Exit Code Interpretation

| Exit Code | Meaning | Analysis Approach |
|-----------|---------|-------------------|
| 0 | Complete success | Summarize positive outcomes, validate results |
| 1 | Failure/error | Find and explain the error, suggest fixes |
| -15 (SIGTERM) | Terminated externally | Note interruption, check for partial results |
| 137 | OOM killed | Memory issues, suggest optimization |
| 124 | Timeout | Operation took too long, suggest timeouts |

## Output Structure Template

```
## Process Completion Summary

**Process**: proc_<ID>
**Exit Code**: N (Status Description)
**Duration**: If inferable from output

### Command Analysis
- **Skill**: <name>
- **Parameters**: <key parameters extracted>

### Key Outcomes
<List of notable results or events>

### Status Assessment
<Overall success/failure/interrupted assessment>

### Issues Found (if any)
<Errors, warnings, or concerns>

### Recommendations (if applicable)
<Suggestions for next steps or fixes>
```

## Domain Knowledge: Evolution Scripts

### Evolution Parameters
- `--skill <name>`: Which skill is being evolved
- `--iterations N`: Number of iterations (often 10 for quick tests)
- `--eval-source`: Evaluation source (sessiondb, synthetic)
- `--optimizer-model`, `--eval-model`: Model names
- `--stats-csv`: Output file for statistics

### Common Evolution Output Patterns

1. **DSPy GEPA Optimization**:
   - Shows "Iteration X:" with scores
   - Pareto front programs shown as `{0, 1, 2...}`
   - Best valset aggregate score: ~0.60-0.70 typical
   - Optimization time in seconds

2. **Validation Checks**:
   - `size_limit`: Under 50,000 chars
   - `growth_limit`: Under +20%
   - `skill_structure`: Valid frontmatter + body
   - All pass = ✅

3. **Holdout Evaluation**:
   - Baseline vs Evolved scores
   - Change metric (positive = improvement)

### Common Errors

1. **ValueError from `relative_to()`**:
   - Cause: Path resolution issue when skill path is outside hermes-agent directory
   - Fix: Use safe wrapper that falls back to absolute path
   ```python
   def safe_relative_path(path: Path, base: Path) -> str:
       try:
           return str(path.relative_to(base))
       except ValueError:
           return str(path.resolve())
   ```

2. **SIGTERM (-15) Interruption**:
   - Process was externally killed (timeout, manual, cron)
   - May have partial results
   - Check stats CSV for any data written

3. **Python Import Errors**:
   - Often related to venv/system Python mismatch
   - numpy ABI mismatches with fastembed
   - Check if using correct Python version

## Analysis Best Practices

1. **Always verify exit code matches the narrative** - don't assume success from positive output if exit code is non-zero

2. **Check for errors in output** - tracebacks indicate failure even with exit 0 in some cases

3. **Extract concrete metrics** when available:
   - Scores (0-1 scale)
   - Time durations
   - Iteration counts
   - File sizes

4. **Identify partial completion** - processes interrupted may have written partial data to stats files

5. **Look for "IMPORTANT" markers** in output - these often indicate significant events

6. **Provide actionable recommendations** - don't just describe what happened, suggest what to do next

## Quality Checklist

- [ ] Process ID and exit code clearly stated
- [ ] Command parameters extracted correctly
- [ ] Key outcomes identified from output
- [ ] Errors traced to root cause (when applicable)
- [ ] Interpretation matches exit code
- [ ] Recommendations are specific and actionable
- [ ] Formatting is clear and structured
