# Contributing to Agent Evolution Lab

An experimental workbench for evolving autonomous-agent skills, tools, prompts,
datasets, and evaluation loops from real usage evidence.

## Setup

```bash
git clone https://github.com/steezkelly/hermes-agent-self-evolution.git
cd hermes-agent-self-evolution
python -m venv .venv-review
source .venv-review/bin/activate
pip install -e ".[dev]"
```

## Running tests

```bash
# Full suite (from repo root with venv active)
python -m pytest tests/ -q

# Targeted run (specific module)
python -m pytest tests/core/test_pipeline_runner.py -v

# With coverage
python -m pytest tests/ -q --cov=evolution --cov-report=term-missing
```

Tests redirect `HERMES_HOME` to temp directories automatically — they never
touch your real `~/.hermes/`.

Expected: all tests pass, zero allowed failures. Warnings from dependency
paths (DSPy `InputField`/`OutputField` `prefix` deprecation) are known noise —
not regressions.

## How to add a new Foundry module

Every Foundry module follows the same shape. Copy this pattern:

### 1. Create the module: `evolution/core/your_failure_detector.py`

```python
"""Detect <failure class>: <one-line description>.

What it catches: <concrete example of the failure>
Output: run_report.json at --out/<module_name>/
Safety: no network, no external writes, no GitHub, no production mutation.
"""

import json
from pathlib import Path

import click
from evolution.core.run_report import run_report


@click.command()
@click.option("--out", required=True, type=Path, help="Output directory")
@click.option("--no-network", is_flag=True, required=True,
              help="Safety gate: disallow network calls")
@click.option("--no-external-writes", is_flag=True, required=True,
              help="Safety gate: disallow external writes")
def main(out: Path, no_network: bool, no_external_writes: bool) -> None:
    """Run the failure detector and emit run_report.json."""
    # Safety: verify flags are respected (fail-closed)
    if not no_network or not no_external_writes:
        raise click.UsageError(
            "Both --no-network and --no-external-writes are required"
        )

    module_dir = out / "your_failure_detector"
    module_dir.mkdir(parents=True, exist_ok=True)

    # --- BASELINE ---
    baseline_result = {"passed": False, "failures": ["Baseline: no detection logic"]}
    baseline_report = run_report(
        out=module_dir,
        mode="fixture",
        task_type="your_failure_detector",
        baseline=baseline_result,
        candidate=None,
        safety={"network_allowed": False, "external_writes_allowed": False},
    )
    baseline_report.write()

    # --- CANDIDATE ---
    # Replace with actual detection logic:
    candidate_result = {"passed": True, "failures": []}
    candidate_report = run_report(
        out=module_dir,
        mode="fixture",
        task_type="your_failure_detector",
        baseline=baseline_result,
        candidate=candidate_result,
        safety={"network_allowed": False, "external_writes_allowed": False},
    )
    candidate_report.write()
    candidate_report.assert_candidate_passed()

    print(f"Report at {module_dir / 'run_report.json'}")


if __name__ == "__main__":
    main()
```

### 2. Create tests: `tests/core/test_your_failure_detector.py`

```python
from click.testing import CliRunner


def test_baseline_fails():
    from evolution.core.your_failure_detector import main

    runner = CliRunner()
    result = runner.invoke(main, [
        "--out", "/tmp/test-out",
        "--no-network", "--no-external-writes",
    ])
    assert result.exit_code == 0
    # Additional assertions: check run_report.json veridict, safety block, etc.


def test_safety_flags_required():
    from evolution.core.your_failure_detector import main

    # Missing --no-network must exit nonzero
    result = CliRunner().invoke(main, [
        "--out", "/tmp/test-out",
        "--no-external-writes",
    ])
    assert result.exit_code != 0

    # Missing --no-external-writes must exit nonzero
    result = CliRunner().invoke(main, [
        "--out", "/tmp/test-out",
        "--no-network",
    ])
    assert result.exit_code != 0
```

### 3. Register in the pipeline runner

Add your module to `evolution/core/pipeline_runner.py`'s `_FIXTURE_RUNNERS` list.

## Module shape requirements

Every Foundry module must:

- **Click CLI entry point** with `--out`, `--no-network`, `--no-external-writes`
- **Baseline vs Candidate** pattern — baseline must fail on the target failure
  class; candidate must pass after detection/improvement
- **run_report.json output** via `evolution.core.run_report.run_report()` with:
  - `schema_version` (int, >= 1)
  - `mode` (string, e.g. "fixture" or "real_trace")
  - `task_type` (string, the module name)
  - `baseline` block with `passed` (bool) and `failures` (list)
  - `candidate` block with `passed` and `failures`
  - `safety` block with all flags explicitly false
- **Fail-closed safety**: refuse to run without `--no-network --no-external-writes`

## What NOT to do

Hard boundaries — violations break the safety model:

- **No network calls** — no `requests.get()`, no `urllib`, no SDK API calls
- **No GitHub writes** — no `gh pr create`, no `git push`, no REST writes
- **No production mutation** — no file writes outside `--out`, no `systemctl start`,
  no herm-es config changes, no cron edits
- **No credential access** — never read `.env`, `config.yaml`, or `auth.json`
- **No external sends** — no Telegram/Discord/email delivery, no ntfy push,
  no webhook POST

What IS allowed inside `--out`:
- Writing `run_report.json`, `action_queue.json`, `pipeline_run.json`
- Writing `eval_examples.json`, `promotion_dossier.md`, `artifact_manifest.json`
- Creating per-module subdirectories

If a module needs input data, accept it via explicit CLI flags (e.g. `--trace`).
Never auto-discover or auto-ingest.

## PR conventions

- **Branch naming**: `feat/<description>`, `fix/<description>`, `docs/<description>`
- **Create as draft** — all PRs start draft until tests pass locally
- **One concern per PR** — if multiple modules changed, they should detect the
  same failure class
- **Include test evidence in the PR body** — paste exact `pytest` command and result
- **Squash merge** into `main` (default for feature branches)

## Commit conventions

```
type: concise subject line

Optional body with details.
```

Types: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Key rules

- Never break existing module contracts — `run_report.json` shape is stable
- Safety flags are non-optional on every CLI entry point
- Pipeline runner's `_FIXTURE_RUNNERS` list is the registry of record
- Tests must verify both happy path AND fail-closed safety (missing flags → nonzero exit)
