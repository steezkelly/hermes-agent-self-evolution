"""Tests for ConfigDriftChecker and ScopeCreepChecker."""

from evolution.core.constraints_v2 import ConfigDriftChecker, ScopeCreepChecker, PurposePreservationChecker


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


class TestPurposePreservationChecker:
    """Tests for PurposePreservationChecker — blocks type-changing evolutions."""

    def test_identical_bodies_pass(self):
        checker = PurposePreservationChecker()
        body = "# Test Skill\n\nThis is a test about code review for python projects.\n\n## Steps\n1. Do thing\n"
        status, _ = checker.check(body, body)
        assert status is True  # identical content preserves purpose

    def test_consultant_prompt_adoption_fails(self):
        """Evolved adopted ## Role / ## Task format when baseline was documentation."""
        checker = PurposePreservationChecker()
        baseline = (
            "# Test Skill\n\n## Overview\nThis skill handles code review.\n\n## Steps\n1. Review\n"
        )
        evolved = (
            "# Test Skill\n\n## Role\nYou are a code reviewer.\n\n## Task\nReview the provided code.\n"
        )
        status, msg = checker.check(evolved, baseline)
        assert status is False  # consultant-prompt adoption must fail

    def test_keyword_survival_threshold(self):
        """If <40% of skill-type keywords survive, check fails."""
        checker = PurposePreservationChecker(keyword_threshold=0.4)
        baseline = (
            "# Debugging Skill\n\n"
            "Use debug, trace, inspect, hypothesis, verify, root cause, "
            "reproduce, isolate, systematic for debugging.\n"
        )
        # Evolved keeps only 1/8 keywords (< 40%)
        evolved = "# Debugging Skill\n\n## Role\nYou are an expert debugger.\n"
        status, msg = checker.check(evolved, baseline)
        assert status is False  # should FAIL — only 1/8 = 12.5% survival

    def test_doc_sections_collapse_fails(self):
        """Baseline had ## Steps/Overview, evolved lost them -> fail."""
        checker = PurposePreservationChecker()
        baseline = "# Test\n\n## Overview\n## Steps\n1. Do it\n## Examples\n"
        evolved = "# Test\n\n## Role\nDo the task.\n"
        status, _ = checker.check(evolved, baseline)
        assert status is False

    def test_no_matching_baseline_doc_sections_consultant_adoption(self):
        """Baseline has non-standard sections, evolved adopts consultant format -> fail."""
        checker = PurposePreservationChecker()
        # Baseline with non-standard section names (no match in DOCUMENTATION_SECTIONS)
        baseline = (
            "# Test\n\n## Choosing a Pattern\n## Pattern 1\nContent.\n## Pattern 2\nContent.\n"
        )
        # Evolved with consultant-prompt sections
        evolved = (
            "# Test\n\n## Role\nYou are a task executor.\n\n## Task\nExecute the pattern.\n"
        )
        status, msg = checker.check(evolved, baseline)
        assert status is False

    def test_consultant_subset_survives(self):
        """Baseline already had some consultant sections — subset adoption is OK."""
        checker = PurposePreservationChecker()
        baseline = "# Test\n\n## Role\nYou are a reviewer.\n## Task\nReview the code.\n"
        evolved = "# Test\n\n## Role\nYou are a senior reviewer.\n## Task\nReview thoroughly.\n## Output Format\nJSON.\n"
        status, _ = checker.check(evolved, baseline)
        assert status is True  # OK — baseline had consultant sections too

    def test_single_doc_section_baseline_reorganized_passes(self):
        """Baseline with 1 doc section that gets reorganized → pass."""
        checker = PurposePreservationChecker()
        baseline = "# Test\n\n## Overview\nThis skill handles code review.\n## Steps\n1. Review\n"
        evolved = "# Test\n\n## Overview\nThis skill handles code review.\n## How to Use\n1. Review\n"
        status, _ = checker.check(evolved, baseline)
        assert status is True

    def test_content_semantic_similarity_catches_format_drift(self):
        """When keywords survive but text distribution diverges → fail."""
        from evolution.core.constraints_v2 import ContentSemanticScorer

        baseline = """
## Pattern Selection
Choose the workflow pattern based on task characteristics:
- Collaborative: Multiple agents provide parallel feedback
- Hierarchical: Sequential chain of specialist agents
- Delegation: Spawn a single focused subagent

## Execution Rules
When using delegation, ensure the subagent has full context.
"""
        evolved = """
## Task Input Format
Describe the task clearly before invoking a workflow.

## Execution Rules
1. If task is ambiguous → route to collaborative pattern
2. If task has clear subtasks → chain of specialists
3. If task is well-defined → spawn focused subagent

## Response Quality
Evaluate outputs on accuracy, completeness, and consistency.
"""
        checker = PurposePreservationChecker()
        scorer = ContentSemanticScorer().fit(baseline)
        checker.set_content_scorer(scorer)

        status, msg = checker.check(evolved, baseline)
        assert status is False, f"Expected FAIL but got: {msg}"
        assert "content-semantic divergence" in msg

    def test_mnemosyne_self_evolution_tools_purpose_drift_is_caught(self):
        """Regression test: canonical mnemosyne tools baseline vs drifted evolved.

        The evolved content drifted to 'Background Process Completion Analyzer' —
        a completely different skill type. ContentSemanticScorer must catch this
        even though keyword survival passes (both bodies contain 'debug', 'test',
        'verify', etc.).

        This test EXISTS because the original dispatch missed this failure.
        v2_20260502_170705 recommended 'deploy' on the drifted content.
        """
        from pathlib import Path
        from evolution.core.constraints_v2 import ContentSemanticScorer, extract_body

        # Canonical baseline from first run: genuine Mnemosyne tools
        canonical_path = Path(
            "output/mnemosyne-self-evolution-tools/20260428_014049/baseline_skill.md"
        )
        if not canonical_path.exists():
            # Fallback for CI / test environments without the file
            canonical_body = (
                "# Mnemosyne Self-Evolution Tools\n\n"
                "Build standalone Python diagnostic tools for Mnemosyne. "
                "Zero dependencies (stdlib only).\n\n"
                "## When to Use\n"
                "- Creating tools that analyze Mnemosyne DB health\n"
                "- Building snapshot-based trend tracking\n"
                "## Architecture Pattern: Snapshot + Trends\n"
                "### Snapshot Structure\n"
                "Use json with timestamp, version, metrics dict.\n"
                "### Trend Calculation\n"
                "Load snapshots, calculate deltas and percent changes.\n"
                "## Testing Pattern\n"
                "Test tools with real mnemosyne.db, verify outputs.\n"
            )
        else:
            raw = canonical_path.read_text()
            canonical_body = extract_body(raw)

        # Drifted evolved: Background Process Completion Analyzer (wrong topic)
        drifted_body = (
            "# Background Process Completion Analyzer\n\n"
            "## Task Overview\n"
            "You will receive notifications about background processes that have completed. "
            "Your job is to analyze these completions.\n\n"
            "## Input Format\n"
            "Background process proc_<ID> completed (exit code <N>).\n\n"
            "## Key Components to Extract\n"
            "1. Process ID\n"
            "2. Exit Code (0=success, 1=failure, -15=SIGTERM)\n"
            "3. Command\n"
            "4. Output\n\n"
            "## Output Structure Template\n"
            "## Process Completion Summary\n"
            "**Process**: proc_<ID>\n"
            "**Exit Code**: N\n"
            "## Domain Knowledge: Evolution Scripts\n"
            "Evolution Parameters: --skill, --iterations, --eval-source\n"
            "DSPy GEPA Optimization shows iteration scores.\n"
        )

        checker = PurposePreservationChecker()
        scorer = ContentSemanticScorer().fit(canonical_body)
        checker.set_content_scorer(scorer)

        status, msg = checker.check(drifted_body, canonical_body)
        assert status is False, (
            "PURPOSE DRIFT NOT CAUGHT! ContentSemanticScorer should have "
            "detected that 'Background Process Completion Analyzer' is not "
            f"'Mnemosyne Self-Evolution Tools'. Got: {msg}"
        )

    def test_content_semantic_similarity_allows_legitimate_improvement(self):
        """When keywords survive AND text distribution is similar → pass."""
        from evolution.core.constraints_v2 import ContentSemanticScorer

        baseline = """
## Overview
This skill helps you debug issues systematically.

## Steps
1. Identify the root cause
2. Reproduce the issue
3. Test the fix
"""
        # Evolved: same format, same structure, improved wording
        evolved = """
## Overview
This skill helps you systematically debug issues.

## Steps
1. Find the root cause
2. Reproduce the problem
3. Verify the fix
"""
        checker = PurposePreservationChecker()
        scorer = ContentSemanticScorer().fit(baseline)
        checker.set_content_scorer(scorer)

        status, msg = checker.check(evolved, baseline)
        assert status is True, f"Expected PASS but got: {msg}"


class TestContentSemanticScorer:
    """Tests for ContentSemanticScorer."""

    def test_identical_bodies_high_similarity(self):
        """Identical bodies score near 1.0."""
        from evolution.core.constraints_v2 import ContentSemanticScorer
        body = "## Overview\nThis skill handles code review.\n\n## Steps\n1. Review the code\n2. Provide feedback.\n"
        scorer = ContentSemanticScorer().fit(body)
        score, threshold = scorer.score(body)
        assert score > 0.9, f"Identical bodies should score > 0.9, got {score}"

    def test_different_format_low_similarity(self):
        """Pattern-description doc vs execution-sheet → low similarity."""
        from evolution.core.constraints_v2 import ContentSemanticScorer

        baseline = """
## Pattern Selection
Choose the workflow pattern based on task:
- Collaborative: Multiple agents, parallel feedback
- Hierarchical: Sequential chain of specialists
- Delegation: Spawn focused subagent

## Execution Rules
Provide full context when delegating.
"""
        evolved = """
## Task Input Format
Clearly describe the task before starting.

## Execution Rules
1. If ambiguous → collaborative
2. If sequential → hierarchical
3. If well-defined → delegation

## Response Quality
Check accuracy and completeness.
"""
        scorer = ContentSemanticScorer().fit(baseline)
        score, threshold = scorer.score(evolved)
        assert score < threshold, f"Different formats should score below {threshold}, got {score}"

    def test_empty_evolved_defaults_to_passing(self):
        """Empty evolved body should not crash."""
        from evolution.core.constraints_v2 import ContentSemanticScorer
        baseline = "## Overview\nTest skill.\n"
        scorer = ContentSemanticScorer().fit(baseline)
        score, threshold = scorer.score("")
        assert score == 1.0  # Should default to 1.0 (no penalize empty)
