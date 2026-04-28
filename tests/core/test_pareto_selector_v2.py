"""Tests for ParetoSelector."""

from evolution.core.pareto_selector import ParetoSelector


def test_select_evolved_when_better():
    """Should select evolved when it has higher holdout score with minimal growth."""
    selector = ParetoSelector()
    result = selector.select(
        baseline_body="# Baseline\nsmall skill",
        baseline_score=0.50,
        evolved_body="# Evolved\n# Extended\nmuch larger skill with more detail and instructions",
        evolved_score=0.75,
        robustness_passed=True,
    )
    assert result.source == "evolved"
    assert result.holdout_score == 0.75


def test_select_baseline_when_no_improvement():
    """Should select baseline when evolved score is not better."""
    selector = ParetoSelector(min_improvement_delta=0.03)
    result = selector.select(
        baseline_body="# Baseline\nsmall skill",
        baseline_score=0.50,
        evolved_body="# Evolved\n# Extended\nmuch larger skill body",
        evolved_score=0.51,  # only 0.01 improvement — below noise floor
        robustness_passed=True,
    )
    assert result.source == "baseline"


def test_select_baseline_when_robustness_fails():
    """Should select baseline when robustness checks fail regardless of score."""
    selector = ParetoSelector()
    result = selector.select(
        baseline_body="# Baseline\nsmall skill",
        baseline_score=0.50,
        evolved_body="# Evolved\nmuch larger skill",
        evolved_score=0.80,
        robustness_passed=False,
    )
    assert result.source == "baseline"


def test_growth_penalty_overrides_improvement():
    """Evolved with huge growth but small improvement should be rejected."""
    selector = ParetoSelector(growth_threshold=0.2, min_improvement_delta=0.03)
    result = selector.select(
        baseline_body="x" * 100,
        baseline_score=0.50,
        evolved_body="x" * 500,  # 400% growth
        evolved_score=0.55,  # 10% improvement
        robustness_passed=True,
    )
    # 400% growth should trigger size penalty that overrides small improvement
    assert result.source == "baseline"


def test_zero_growth_improvement_wins():
    """When evolved is same size and better score, it should win."""
    selector = ParetoSelector()
    result = selector.select(
        baseline_body="# Same size",
        baseline_score=0.50,
        evolved_body="# Same size",
        evolved_score=0.80,
        robustness_passed=True,
    )
    assert result.source == "evolved"
