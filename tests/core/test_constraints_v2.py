"""Tests for ConfigDriftChecker and ScopeCreepChecker."""

from evolution.core.constraints_v2 import ConfigDriftChecker, ScopeCreepChecker


class TestConfigDriftChecker:
    def test_pass_when_identical(self):
        checker = ConfigDriftChecker()
        fm = "name: test-skill\ndescription: A test skill"
        passed, msg = checker.check(fm, fm)
        assert passed

    def test_fail_when_name_changes(self):
        checker = ConfigDriftChecker()
        passed, msg = checker.check(
            "name: new-name\ndescription: A test skill",
            "name: test-skill\ndescription: A test skill",
        )
        assert not passed
        assert "name" in msg

    def test_fail_when_description_changes(self):
        checker = ConfigDriftChecker()
        passed, msg = checker.check(
            "name: test-skill\ndescription: Different description",
            "name: test-skill\ndescription: Original description",
        )
        assert not passed
        assert "description" in msg

    def test_pass_with_version_change(self):
        checker = ConfigDriftChecker()
        passed, msg = checker.check(
            "name: test-skill\ndescription: A test skill\nversion: '2.0'",
            "name: test-skill\ndescription: A test skill\nversion: '1.0'",
        )
        assert passed

    def test_parse_frontmatter_with_markers(self):
        checker = ConfigDriftChecker()
        fm = "---\nname: test-skill\ndescription: A test skill\n---"
        passed, msg = checker.check(fm, fm)
        assert passed


class TestScopeCreepChecker:
    def test_match_when_identical(self):
        checker = ScopeCreepChecker()
        body = "# Test Skill\n\nThis is a test skill about code review.\n"
        status, msg = checker.check(body, body)
        assert status == "match"

    def test_minor_drift_with_some_new_terms(self):
        checker = ScopeCreepChecker(min_occurrences=2, match_threshold=0.10, drift_threshold=0.30)
        baseline = "# Test Skill\nThis skill handles code review for python projects\n"
        # Add new domain terms (deployment, kubernetes) that appear frequently
        evolved = (
            "# Test Skill\n"
            "This skill handles code review for python projects.\n"
            "deployment kubernetes deployment kubernetes deployment kubernetes\n"
        )
        status, msg = checker.check(evolved, baseline)
        # The evolved body has significantly different term frequency
        assert status in ("minor_drift", "major_drift")

    def test_match_with_stopwords(self):
        """Common English words should be filtered."""
        checker = ScopeCreepChecker()
        baseline = "# Test\nThis is a test with the and for words"
        evolved = "# Test\nThis is a test with the and for words and nothing new"
        status, msg = checker.check(evolved, baseline)
        assert status == "match"

    def test_match_empty_baseline(self):
        """If baseline is too small to extract terms, pass."""
        checker = ScopeCreepChecker()
        status, msg = checker.check("# Big evolved body\n" * 10, "# Small")
        assert status == "match"
