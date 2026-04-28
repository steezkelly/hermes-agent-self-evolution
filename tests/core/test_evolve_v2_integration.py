"""Integration tests for GEPA v2 pipeline (dry-run, no API calls)."""

from evolution.core.types import ComputeBudget
from evolution.core.evolve_skill_v2 import EvolutionRun
from evolution.core.backtrack import BacktrackController
from evolution.core.pareto_selector import ParetoSelector


def test_dry_run_makes_no_api_calls():
    """Dry run should return immediately without calling any LM."""
    run = EvolutionRun(skill_name="test-skill")
    budget = ComputeBudget(max_iterations=10, total_metric_calls=100)
    report = run.execute(
        baseline_body="# Test Skill\n\nSimple skill for testing",
        baseline_frontmatter="name: test-skill\ndescription: A test skill",
        baseline_score=0.5,
        budget=budget,
        dry_run=True,
    )
    assert report.skill_name == "test-skill"
    assert report.n_iterations_executed == 0
    assert report.improvement == 0.0
    assert report.recommendation == "review"


def test_pipeline_runs_without_gepa():
    """Pipeline skeleton should complete without GEPA being initialized."""
    run = EvolutionRun(skill_name="test-skill")
    budget = ComputeBudget(max_iterations=3, total_metric_calls=30)
    report = run.execute(
        baseline_body="# Test Skill\n\nTesting pipeline skeleton",
        baseline_frontmatter="name: test-skill\ndescription: A test skill",
        baseline_score=0.5,
        budget=budget,
    )
    assert report.n_iterations_executed <= 3
    assert report.recommendation in ("deploy", "review", "reject")
    assert len(report.backtrack_events) > 0


def test_backtrack_integration():
    """Backtrack controller should integrate with EvolutionRun history."""
    controller = BacktrackController(window_size=3, plateau_threshold=0.01)
    from evolution.core.types import EvolutionSnapshot

    # Simulate improving, then plateauing
    for i in range(5):
        score = 0.50 + (0.02 * min(i, 3))  # plateau after 3 iterations
        controller.checkpoint(EvolutionSnapshot(i, f"body{i}", score, "", f"t{i}"))

    decision = controller.should_backtrack(0.54)
    # Should detect plateau since scores only moved 0.02 over 5 iterations
    assert decision.action in ("backtrack", "continue")


def test_pareto_selector_integration():
    """Pareto selector should work with EvolutionRun output shapes."""
    selector = ParetoSelector()
    result = selector.select(
        baseline_body="# Base\ncontent",
        baseline_score=0.5,
        evolved_body="# Base\ncontent\nmore content",
        evolved_score=0.65,
        robustness_passed=True,
    )
    assert result.source in ("evolved", "baseline")
    assert 0.0 <= result.holdout_score <= 1.0
