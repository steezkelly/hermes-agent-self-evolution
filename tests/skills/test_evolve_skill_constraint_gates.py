"""Tests for evolution constraint gates."""

import click
import pytest

from evolution.core.constraints import ConstraintResult
from evolution.skills.evolve_skill import (
    _require_constraints_pass,
    _validate_baseline_constraints,
)


class RecordingValidator:
    def __init__(self):
        self.calls = []

    def validate_all(self, artifact_text, artifact_type):
        self.calls.append((artifact_text, artifact_type))
        return [ConstraintResult(True, "skill_structure", "Skill has valid frontmatter")]


def test_baseline_validation_uses_full_raw_skill_not_body_only():
    validator = RecordingValidator()
    skill = {
        "raw": "---\nname: test\ndescription: Test skill\n---\n\n# Test\nBody",
        "body": "# Test\nBody",
    }

    _validate_baseline_constraints(skill, validator)

    assert validator.calls == [(skill["raw"], "skill")]


def test_constraint_gate_accepts_all_passing_results():
    _require_constraints_pass(
        [ConstraintResult(True, "size_limit", "Size OK")],
        artifact_label="baseline skill",
    )


def test_constraint_gate_rejects_any_failing_result_with_context():
    results = [
        ConstraintResult(True, "size_limit", "Size OK"),
        ConstraintResult(False, "skill_structure", "Skill missing frontmatter"),
    ]

    with pytest.raises(click.ClickException) as exc_info:
        _require_constraints_pass(results, artifact_label="baseline skill")

    message = str(exc_info.value)
    assert "baseline skill" in message
    assert "skill_structure" in message
    assert "Skill missing frontmatter" in message
