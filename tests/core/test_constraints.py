"""Tests for constraint validators."""

import sys
import subprocess

import pytest
from evolution.core.constraints import ConstraintValidator
from evolution.core.config import EvolutionConfig


@pytest.fixture
def validator():
    config = EvolutionConfig()
    return ConstraintValidator(config)


class TestSizeConstraints:
    def test_skill_under_limit(self, validator):
        result = validator._check_size("x" * 1000, "skill")
        assert result.passed

    def test_skill_over_limit(self, validator):
        result = validator._check_size("x" * 60_000, "skill")
        assert not result.passed
        assert "exceeded" in result.message

    def test_tool_description_under_limit(self, validator):
        result = validator._check_size("Search files by content", "tool_description")
        assert result.passed

    def test_tool_description_over_limit(self, validator):
        result = validator._check_size("x" * 600, "tool_description")
        assert not result.passed


class TestGrowthConstraints:
    def test_acceptable_growth(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 1100  # 10% growth
        result = validator._check_growth(evolved, baseline, "skill")
        assert result.passed

    def test_excessive_growth(self, validator):
        baseline = "x" * 25_000
        evolved = "x" * 32_500  # 30% growth on 25KB skill (max 20% for >20KB skills)
        result = validator._check_growth(evolved, baseline, "skill")
        assert not result.passed

    def test_shrinkage_is_ok(self, validator):
        baseline = "x" * 1000
        evolved = "x" * 800  # 20% smaller
        result = validator._check_growth(evolved, baseline, "skill")
        assert result.passed


class TestNonEmpty:
    def test_non_empty_passes(self, validator):
        result = validator._check_non_empty("some content")
        assert result.passed

    def test_empty_fails(self, validator):
        result = validator._check_non_empty("")
        assert not result.passed

    def test_whitespace_only_fails(self, validator):
        result = validator._check_non_empty("   \n  ")
        assert not result.passed


class TestSkillStructure:
    def test_valid_skill(self, validator):
        skill = "---\nname: test-skill\ndescription: A test skill\n---\n\n# Test\n\nThis is a substantive test skill body with enough content to pass\nstructural validation. It describes a step-by-step procedure for\nprocessing requests and handling edge cases in the system.\n\n## Steps\n\n1. Validate the input parameters\n2. Process the request through the pipeline\n3. Return the result to the caller"
        result = validator._check_skill_structure(skill)
        assert result.passed

    def test_missing_frontmatter(self, validator):
        skill = "# Test\nContent without frontmatter"
        result = validator._check_skill_structure(skill)
        assert not result.passed

    def test_missing_name(self, validator):
        skill = "---\ndescription: A test skill\n---\n\n# Test"
        result = validator._check_skill_structure(skill)
        assert not result.passed
        assert "name" in result.message

    def test_missing_description(self, validator):
        skill = "---\nname: test\n---\n\n# Test"
        result = validator._check_skill_structure(skill)
        assert not result.passed
        assert "description" in result.message


class TestRunTestSuite:
    def test_uses_current_python_interpreter(self, validator, monkeypatch, tmp_path):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout="1 passed\n", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = validator.run_test_suite(tmp_path)

        assert result.passed
        assert calls[0][0][0] == sys.executable
        assert calls[0][0][1:] == ["-m", "pytest", "tests/", "-q", "--tb=no"]
        assert calls[0][1]["cwd"] == str(tmp_path)
