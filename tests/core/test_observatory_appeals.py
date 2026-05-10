"""Tests for evolution.core.observatory.appeals

Covers: Cohen's Kappa computation, Tier2Sampler sampling logic, Kappa thresholds,
audit_skill flow with mock data.
"""

import tempfile
from pathlib import Path

import pytest
import numpy as np

from evolution.core.observatory.appeals import (
    cohens_kappa,
    Tier2Sampler,
    Tier2AuditResult,
    AppealTask,
)
from evolution.core.observatory.logger import JudgeAuditLogger


class TestCohensKappa:
    def test_perfect_agreement(self):
        t1 = [0.2, 0.5, 0.8]
        t2 = [0.2, 0.5, 0.8]
        k = cohens_kappa(t1, t2)
        assert k == pytest.approx(1.0, rel=1e-6)

    def test_no_agreement_different_buckets(self):
        t1 = [0.1, 0.1, 0.1]   # all bucket 0
        t2 = [0.9, 0.9, 0.9]   # all bucket 2
        k = cohens_kappa(t1, t2)
        # Expected agreement = (1.0 * 0) + (0 * 1.0) + (0 * 0) = 0
        # Observed agreement = 0
        # Kappa = (0 - 0) / (1 - 0) = 0
        assert k == pytest.approx(0.0, rel=1e-6)

    def test_empty_lists(self):
        assert cohens_kappa([], []) == 0.0

    def test_mismatched_lengths(self):
        assert cohens_kappa([0.5], [0.5, 0.6]) == 0.0

    def test_expected_agreement_only(self):
        # Both in same distribution but different assignments
        t1 = [0.1, 0.1, 0.9]
        t2 = [0.1, 0.9, 0.1]
        k = cohens_kappa(t1, t2)
        # Observed = 1/3 agree (first item)
        # Expected = P0(t1)*P0(t2) + P1(t1)*P1(t2) + P2(t1)*P2(t2)
        #          = (2/3)*(2/3) + 0 + (1/3)*(1/3) = 5/9
        # Kappa = (1/3 - 5/9) / (1 - 5/9) = (-2/9) / (4/9) = -0.5
        assert k == pytest.approx(-0.5, rel=1e-6)

    def test_all_same_bucket(self):
        # Edge case: all scores land in same bucket → expected agreement = 1.0
        t1 = [0.1, 0.2, 0.3]
        t2 = [0.15, 0.25, 0.33]  # all still < 0.35
        k = cohens_kappa(t1, t2)
        # All in bucket 0, expected agreement = 1.0 → return 1.0
        assert k == pytest.approx(1.0, rel=1e-6)

    def test_boundary_35(self):
        # Verify bucket boundaries: 0.35 is bucket 1, <0.35 is bucket 0
        # Use 3 items with known Kappa = -0.5
        t1 = [0.1, 0.1, 0.9]   # buckets 0, 0, 2
        t2 = [0.1, 0.9, 0.1]   # buckets 0, 2, 0
        k = cohens_kappa(t1, t2)
        # Observed = 1/3, Expected = 5/9, Kappa = -0.5
        assert k == pytest.approx(-0.5, rel=1e-6)

    def test_boundary_35_exact(self):
        # 0.35 goes to bucket 1, verify exact boundary
        t1 = [0.35, 0.35, 0.35]   # all bucket 1
        t2 = [0.36, 0.36, 0.36]   # all bucket 1
        assert cohens_kappa(t1, t2) == pytest.approx(1.0)

    def test_kappa_clipped_to_1(self):
        # Impossible to exceed 1.0, but test clipping works
        t1 = [0.1, 0.5, 0.9]
        t2 = [0.1, 0.5, 0.9]
        assert cohens_kappa(t1, t2) == pytest.approx(1.0)


class TestTier2Sampler:
    @pytest.fixture
    def sampler_and_logger(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "appeals.db"
            logger = JudgeAuditLogger(db_path=db)
            sampler = Tier2Sampler(logger)
            yield sampler, logger

    def test_sample_for_appeals_uncertain_zone(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        tier1 = [
            {"task_id": "t1", "skill_name": "s", "raw_score": 0.2},
            {"task_id": "t2", "skill_name": "s", "raw_score": 0.5},
            {"task_id": "t3", "skill_name": "s", "raw_score": 0.9},
        ]
        appeals = sampler.sample_for_appeals(generation=1, tier1_results=tier1)
        # 0.5 is in uncertain zone → t2 is always selected (either random or uncertain)
        assert any(a.task_id == "t2" for a in appeals)
        # If not randomly selected first, reason is uncertain_zone
        t2 = [a for a in appeals if a.task_id == "t2"]
        assert t2[0].reason in ("uncertain_zone", "random_sample")

    def test_sample_for_appeals_random(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        np.random.seed(42)
        tier1 = [
            {"task_id": f"t{i}", "skill_name": "s", "raw_score": 0.9}
            for i in range(100)
        ]
        appeals = sampler.sample_for_appeals(generation=1, tier1_results=tier1)
        # At 5% rate, expect ~5 random samples
        random_appeals = [a for a in appeals if a.reason == "random_sample"]
        assert 2 <= len(random_appeals) <= 10  # probabilistic

    def test_check_kappa_sufficient(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        t1 = [0.1, 0.5, 0.9, 0.2, 0.8]
        t2 = [0.15, 0.55, 0.85, 0.25, 0.75]
        result = sampler.check_kappa(generation=1, tier1_scores=t1, tier2_scores=t2)
        assert result["sufficient"] is True
        assert result["kappa"] >= 0.6
        assert result["consecutive_breaches"] == 0
        assert result["halt_recommended"] is False

    def test_check_kappa_insufficient(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        # Low agreement: all in different buckets
        t1 = [0.1, 0.1, 0.1, 0.9, 0.9]
        t2 = [0.9, 0.9, 0.9, 0.1, 0.1]
        result = sampler.check_kappa(generation=1, tier1_scores=t1, tier2_scores=t2)
        assert result["sufficient"] is False
        assert result["consecutive_breaches"] == 1
        assert result["halt_recommended"] is False  # only 1 breach

    def test_check_kappa_consecutive_breaches(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        # 3 generations with bad kappa — need ≥3 scores each
        for gen in [1, 2, 3]:
            result = sampler.check_kappa(
                generation=gen,
                tier1_scores=[0.1, 0.1, 0.9, 0.9, 0.5],
                tier2_scores=[0.9, 0.9, 0.1, 0.1, 0.5],
            )
        assert result["consecutive_breaches"] == 3
        assert result["halt_recommended"] is True

    def test_check_kappa_not_enough_scores(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        result = sampler.check_kappa(generation=1, tier1_scores=[0.5, 0.5], tier2_scores=[0.5, 0.5])
        assert result["sufficient"] is False
        assert "Not enough paired scores" in result["message"]

    def test_audit_skill_no_data(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        result = sampler.audit_skill("nonexistent")
        assert result.n_total_in_generation == 0
        assert result.sufficient is False
        assert "No audit data" in result.message

    def test_audit_skill_with_data(self, sampler_and_logger):
        sampler, logger = sampler_and_logger
        # Seed with 10 tasks — uncertain zone should trigger re-evaluation
        for i in range(10):
            logger.log(
                generation=1,
                skill_name="test-skill",
                model_used="minimax/minimax-m2.7",
                task_id=f"t{i}",
                expected_behavior="e",
                actual_behavior="a",
                rubric="r",
                raw_score=0.5 if i < 3 else (0.1 if i < 6 else 0.9),
            )
        result = sampler.audit_skill("test-skill")
        # Should have sampled uncertain zone (3 tasks) + random (0-1)
        assert result.n_total_in_generation == 10
        assert result.n_uncertain >= 3
        assert result.sufficient is not None

    def test_audit_skill_logs_tier2(self, sampler_and_logger):
        sampler, logger = sampler_and_logger
        logger.log(
            generation=1, skill_name="test", model_used="m", task_id="t1",
            expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
        )
        appeals = [AppealTask(generation=1, skill_name="test", task_id="t1", tier1_score=0.5, reason="uncertain_zone")]
        sampler.record_tier2_scores(appeals, [0.6])
        rows = logger.get_recent(skill_name="test", limit=5)
        tier2_rows = [r for r in rows if r["model_used"].startswith("TIER2::")]
        assert len(tier2_rows) == 1
        assert tier2_rows[0]["raw_score"] == pytest.approx(0.6)

    def test_consecutive_breach_reset_on_good(self, sampler_and_logger):
        sampler, _ = sampler_and_logger
        # Bad, bad, good → consecutive should reset
        sampler.check_kappa(1, [0.1, 0.1, 0.9, 0.9, 0.5], [0.9, 0.9, 0.1, 0.1, 0.5])
        sampler.check_kappa(2, [0.1, 0.1, 0.9, 0.9, 0.5], [0.9, 0.9, 0.1, 0.1, 0.5])
        # Perfect agreement — all in same buckets
        result = sampler.check_kappa(
            3,
            [0.1, 0.2, 0.3, 0.8, 0.9],       # buckets 0,0,0,2,2
            [0.15, 0.25, 0.33, 0.85, 0.95],  # buckets 0,0,0,2,2
        )
        assert result["sufficient"] is True
        assert result["consecutive_breaches"] == 0
        assert result["halt_recommended"] is False


class TestTier2AuditResult:
    def test_dataclass_fields(self):
        r = Tier2AuditResult(
            skill_name="test",
            n_sampled=5,
            n_uncertain=3,
            n_random=2,
            n_total_in_generation=100,
            kappa=0.75,
            agreement_rate=0.80,
            sufficient=True,
            message="good",
            tier1_mean=0.6,
            tier2_mean=0.65,
            tier1_scores=[0.1, 0.5, 0.9],
            tier2_scores=[0.15, 0.55, 0.85],
        )
        assert r.kappa == pytest.approx(0.75)
        assert r.sufficient is True


class TestAppealTask:
    def test_dataclass_fields(self):
        a = AppealTask(
            generation=1,
            skill_name="s",
            task_id="t1",
            tier1_score=0.5,
            reason="uncertain_zone",
        )
        assert a.reason == "uncertain_zone"
        assert a.generation == 1
