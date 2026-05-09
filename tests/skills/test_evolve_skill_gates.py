"""Tests for optional evolution gate execution."""

from pathlib import Path

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult
from evolution.skills.evolve_skill import _run_pytest_gate_if_requested


class RecordingValidator:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run_test_suite(self, hermes_repo):
        self.calls.append(hermes_repo)
        return self.result


def test_pytest_gate_is_skipped_when_run_pytest_is_false(tmp_path):
    config = EvolutionConfig(run_pytest=False)
    config.hermes_agent_path = tmp_path
    validator = RecordingValidator(
        ConstraintResult(True, "test_suite", "should not run")
    )

    result = _run_pytest_gate_if_requested(validator, config)

    assert result is None
    assert validator.calls == []


def test_pytest_gate_runs_against_configured_hermes_repo_when_enabled(tmp_path):
    config = EvolutionConfig(run_pytest=True)
    config.hermes_agent_path = tmp_path
    gate_result = ConstraintResult(True, "test_suite", "All tests passed")
    validator = RecordingValidator(gate_result)

    result = _run_pytest_gate_if_requested(validator, config)

    assert result == gate_result
    assert validator.calls == [tmp_path]


def test_pytest_gate_returns_failure_result_when_tests_fail(tmp_path):
    config = EvolutionConfig(run_pytest=True)
    config.hermes_agent_path = tmp_path
    gate_result = ConstraintResult(False, "test_suite", "Test suite failed", "1 failed")
    validator = RecordingValidator(gate_result)

    result = _run_pytest_gate_if_requested(validator, config)

    assert result == gate_result
    assert not result.passed
