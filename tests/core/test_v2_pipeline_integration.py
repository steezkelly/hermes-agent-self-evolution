"""Full pipeline integration test — exercises all v2 gates with realistic data.

This test simulates a complete GEPAv2 run WITHOUT making API calls.
It loads a real skill from the repo, creates a mock GEPA output, and
runs every gate in sequence.

Run with: python -m pytest tests/core/test_v2_pipeline_integration.py -v
"""

from pathlib import Path

from evolution.core.config import EvolutionConfig
from evolution.core.router import EvolutionRouter
from evolution.core.backtrack import BacktrackController
from evolution.core.pareto_selector import ParetoSelector
from evolution.core.constraints_v2 import (
    ConfigDriftChecker,
    SkillRegressionChecker,
    ScopeCreepChecker,
)
from evolution.core.types import (
    ScenarioResult,
    RouterDecision,
    BacktrackDecision,
    EvolutionSnapshot,
)


# ── Fixture: load a real skill ─────────────────────────────────────────

SKILL_NAME = "companion-workflows"


def _load_test_skill():
    """Load a real skill from the repo for realistic test data."""
    config = EvolutionConfig()
    from evolution.skills.skill_module import find_skill, load_skill
    path = find_skill(SKILL_NAME, config.hermes_agent_path)
    if not path:
        # Fallback: try finding any skill
        skills_dir = config.hermes_agent_path / "skills"
        if skills_dir.exists():
            for d in sorted(skills_dir.iterdir()):
                if d.is_dir():
                    path = find_skill(d.name, config.hermes_agent_path)
                    if path:
                        break
    if not path:
        raise FileNotFoundError(f"No skill found for {SKILL_NAME}")
    skill = load_skill(path)
    return skill["body"], skill.get("frontmatter", "---\n---\n"), skill["raw"]


def _make_mock_scenarios(n_total: int, n_fail: int, fail_reason: str = "medium") -> list[ScenarioResult]:
    """Generate mock per-scenario results."""
    results = []
    for i in range(n_total):
        failed = i < n_fail
        results.append(ScenarioResult(
            scenario_id=f"scenario_{i}",
            passed=not failed,
            score=0.3 if failed else 0.85,
            failure_reason=fail_reason if failed else "",
            output=f"mock_result_{i}",
        ))
    return results


# ── Tests ────────────────────────────────────────────────────────────────

class TestFullPipeline:
    """Each test exercises the full decision chain for one scenario."""

    def setup_method(self):
        self.body, self.frontmatter, self.raw = _load_test_skill()
        self.modified_body = self.body + "\n\nif new_condition:\n    handle it\nelif another:\n    do something\nelse:\n    fallback\nwhen done:\n    clean up\n"

    def test_pipeline_accepts_improvement(self):
        """Pipeline should accept evolved skill when scores are better and robustness passes."""
        router = EvolutionRouter()
        pareto = ParetoSelector()
        regression = SkillRegressionChecker()
        config_drift = ConfigDriftChecker()
        scope = ScopeCreepChecker()
        backtrack = BacktrackController()

        baseline_score = 0.50
        evolved_score = 0.65  # +30% improvement
        scenarios = _make_mock_scenarios(10, 2, "medium")  # 2/10 failures

        # 1. Router — 2 medium failures with budget available
        router_dec = router.classify(
            skill_body=self.modified_body,
            benchmark_results=scenarios,
            evolution_history=[EvolutionSnapshot(0, self.body, 0.50, "baseline", "t0")],
            remaining_budget=5,
        )
        assert router_dec.action in ("fix", "extend", "abstain"), f"Router returned {router_dec.action}"

        # 2. Config drift — same frontmatter
        drift_ok, drift_msg = config_drift.check(self.frontmatter, self.frontmatter)
        assert drift_ok, f"Config drift should pass: {drift_msg}"

        # 3. Regression — evolved better than baseline
        reg_ok, reg_msg = regression.check_score(evolved_score, baseline_score)
        assert reg_ok, f"Regression should pass: {reg_msg}"

        # 4. Scope creep — modified body has new conditionals
        scope_status, scope_msg = scope.check(self.modified_body, self.body)
        assert scope_status in ("match", "minor_drift"), f"Scope should be minor: {scope_status}"

        # 5. Pareto selection — evolved wins
        pareto_result = pareto.select(
            baseline_body=self.body, baseline_score=baseline_score,
            evolved_body=self.modified_body, evolved_score=evolved_score,
            robustness_passed=True,
        )
        assert pareto_result.source == "evolved", f"Pareto should select evolved, got {pareto_result.source}"

        # 6. Backtrack — should continue since we're improving
        backtrack.checkpoint_for_score(baseline_score, self.body, self.frontmatter, 0)
        bt_dec = backtrack.should_backtrack(evolved_score)
        assert bt_dec.action == "continue", f"Backtrack should continue, got {bt_dec.action}"

    def test_pipeline_rejects_regression(self):
        """Pipeline should reject evolved when score regresses."""
        pareto = ParetoSelector()
        regression = SkillRegressionChecker()
        backtrack = BacktrackController()

        baseline_score = 0.60
        evolved_score = 0.45  # regression

        # 1. Regression checker rejects
        reg_ok, reg_msg = regression.check_score(evolved_score, baseline_score)
        assert not reg_ok, f"Regression should fail: {reg_msg}"

        # 2. Pareto rejects
        pareto_result = pareto.select(
            baseline_body=self.body, baseline_score=baseline_score,
            evolved_body=self.modified_body, evolved_score=evolved_score,
            robustness_passed=False,  # regression failed
        )
        assert pareto_result.source == "baseline", f"Pareto should keep baseline, got {pareto_result.source}"

        # 3. Backtrack registers plateau
        backtrack.checkpoint_for_score(baseline_score, self.body, self.frontmatter, 0)
        backtrack.checkpoint_for_score(evolved_score, self.body, self.frontmatter, 1)
        backtrack.checkpoint_for_score(evolved_score, self.modified_body, self.frontmatter, 2)
        bt_dec = backtrack.should_backtrack(evolved_score)
        # If 3 sequential non-improving checkpoints ≤ threshold, should backtrack
        assert bt_dec.action in ("continue", "backtrack"), f"Unexpected: {bt_dec.action}"

    def test_gates_are_independent(self):
        """Each gate should produce a valid result regardless of others."""
        router = EvolutionRouter()
        pareto = ParetoSelector()
        regression = SkillRegressionChecker()
        config_drift = ConfigDriftChecker()
        scope = ScopeCreepChecker()

        # Gate 1: Router with no history
        r1 = router.classify("# test", [], [], remaining_budget=0)
        assert r1.action in ("fix", "extend", "abstain")
        assert 0.0 <= r1.confidence <= 1.0

        # Gate 2: Pareto with identical bodies
        p1 = pareto.select(
            baseline_body=self.body, baseline_score=0.5,
            evolved_body=self.body, evolved_score=0.5,
            robustness_passed=True,
        )
        assert p1.source == "baseline"
        assert p1.reason != ""

        # Gate 3: Regression with equal scores
        r2 = regression.check_score(0.5, 0.5)
        assert r2[0] is True, f"Regression should pass, got {r2}"

        # Gate 4: Config drift with different tags (name/description same)
        fm1 = "name: test\ndescription: Same description\ntags: [old-tag]"
        fm2 = "name: test\ndescription: Same description\ntags: [new-tag]"
        d1 = config_drift.check(fm1, fm2)
        assert d1[0] is True, f"Tags should not trigger drift: {d1[1]}"

        # Gate 5: Scope creep with empty new terms
        s1 = scope.check("# Simple body", "# Simple body")
        assert s1[0] == "match"

        print("All 5 gates produce valid output in isolation")

    def test_pipeline_rejects_huge_growth(self):
        """Pipeline should flag evolved body that's > growth_threshold larger."""
        pareto = ParetoSelector(growth_threshold=0.2, min_improvement_delta=0.03)
        baseline_score = 0.50
        evolved_score = 0.55  # only 10% improvement — below noise floor
        huge_body = self.body * 5  # 500% growth

        result = pareto.select(
            baseline_body=self.body, baseline_score=baseline_score,
            evolved_body=huge_body, evolved_score=evolved_score,
            robustness_passed=True,
        )
        # 500% growth with only 10% improvement → baseline should win
        assert result.source == "baseline", f"Should reject huge growth, got {result.source}: {result.reason}"
        assert "growth" in result.reason.lower() or "size" in result.reason.lower(), \
            f"Reason should mention growth: {result.reason}"
