"""Tests for the EvolutionRouter."""

from evolution.core.router import EvolutionRouter
from evolution.core.types import RouterDecision, ScenarioResult, EvolutionSnapshot


def test_router_defaults_to_extend_on_empty_failures():
    """When all scenarios pass, Router defaults to extend."""
    router = EvolutionRouter()
    decision = router.classify(
        skill_body="# Test Skill\nStep 1: do thing",
        benchmark_results=[
            ScenarioResult(scenario_id="s1", passed=True, score=1.0, failure_reason="", output="ok"),
            ScenarioResult(scenario_id="s2", passed=True, score=1.0, failure_reason="", output="ok"),
        ],
        evolution_history=[],
        remaining_budget=10,
    )
    assert decision.action == "extend"
    assert decision.confidence >= 0.5


def test_router_edge_case_high_confidence():
    """When 80%+ failures are hard/adversarial, classify as edge_case fix."""
    router = EvolutionRouter()
    failures = [
        ScenarioResult(scenario_id="s1", passed=False, score=0.2, failure_reason="hard", output="x"),
        ScenarioResult(scenario_id="s2", passed=False, score=0.3, failure_reason="adversarial", output="x"),
        ScenarioResult(scenario_id="s3", passed=False, score=0.4, failure_reason="hard", output="x"),
        ScenarioResult(scenario_id="s4", passed=True, score=0.9, failure_reason="easy", output="ok"),
    ]
    decision = router.classify(
        skill_body="# Test Skill",
        benchmark_results=failures,
        evolution_history=[],
        remaining_budget=10,
    )
    assert decision.action == "fix"
    assert decision.failure_pattern == "edge_case"
    assert decision.confidence >= 0.7


def test_router_extend_on_low_budget_noise():
    """When budget is nearly exhausted and no pattern, Router should still extend (not abstain)."""
    router = EvolutionRouter()
    failures = [
        ScenarioResult(scenario_id="s1", passed=False, score=0.4, failure_reason="medium", output="x"),
    ]
    decision = router.classify(
        skill_body="# Test Skill",
        benchmark_results=failures,
        evolution_history=[],
        remaining_budget=1,
    )
    # Router never abstains alone — defaults to extend
    assert decision.action == "extend"
    assert decision.failure_pattern == "noise"


def test_router_structural_detection():
    """When new conditionals are added without holdout improvement, flag as structural fix."""
    router = EvolutionRouter()
    prev_body = "# Simple Skill\nStep 1: do the thing\nStep 2: finish"
    curr_body = "# Complex Skill\nif condition:\n    Step 1: do the thing\nelse:\n    Step 2: alternative\nwhen ready:\n    Step 3: finish"

    failures = [
        ScenarioResult(scenario_id="s1", passed=False, score=0.3, failure_reason="medium", output="x"),
    ]
    decision = router.classify(
        skill_body=curr_body,
        benchmark_results=failures,
        evolution_history=[
            EvolutionSnapshot(iteration=1, skill_body=prev_body, score=0.5,
                              variation_explanation="", timestamp=""),
            EvolutionSnapshot(iteration=2, skill_body=prev_body, score=0.6,
                              variation_explanation="", timestamp=""),
        ],
        remaining_budget=5,
    )
    # Should detect new conditionals (if, else, when = 3)
    # With 2+ history items, structural analysis kicks in
    assert decision.failure_pattern == "structural" or decision.action == "fix", f"Got {decision.failure_pattern}/{decision.action}"


def test_router_confidence_scaling():
    """Confidence should increase with evidence strength."""
    router = EvolutionRouter()

    # Weak evidence: only 1 of 3 failures is hard
    weak_failures = [
        ScenarioResult(scenario_id="s1", passed=False, score=0.3, failure_reason="hard", output="x"),
        ScenarioResult(scenario_id="s2", passed=False, score=0.4, failure_reason="easy", output="x"),
    ]
    weak_decision = router.classify(
        skill_body="# Test",
        benchmark_results=weak_failures,
        evolution_history=[],
        remaining_budget=10,
    )

    # Strong evidence: 4 of 4 failures are hard
    strong_failures = [
        ScenarioResult(scenario_id="s1", passed=False, score=0.2, failure_reason="hard", output="x"),
        ScenarioResult(scenario_id="s2", passed=False, score=0.3, failure_reason="adversarial", output="x"),
        ScenarioResult(scenario_id="s3", passed=False, score=0.1, failure_reason="hard", output="x"),
        ScenarioResult(scenario_id="s4", passed=False, score=0.2, failure_reason="hard", output="x"),
    ]
    strong_decision = router.classify(
        skill_body="# Test",
        benchmark_results=strong_failures,
        evolution_history=[],
        remaining_budget=10,
    )

    # Stronger evidence should produce higher confidence
    assert strong_decision.confidence >= weak_decision.confidence


def test_router_all_pass_high_confidence():
    """All scenarios passing should produce high confidence extend."""
    router = EvolutionRouter()
    all_pass = [
        ScenarioResult(scenario_id="s1", passed=True, score=1.0, failure_reason="", output="ok"),
        ScenarioResult(scenario_id="s2", passed=True, score=0.95, failure_reason="", output="ok"),
        ScenarioResult(scenario_id="s3", passed=True, score=0.98, failure_reason="", output="ok"),
    ]
    decision = router.classify(
        skill_body="# Test",
        benchmark_results=all_pass,
        evolution_history=[],
        remaining_budget=10,
    )
    assert decision.action == "extend"
    assert decision.confidence == 1.0
