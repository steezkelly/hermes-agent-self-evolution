"""Tier-2 Appeals Court + Cohen's Kappa — Phase 2 of the GEPA Observatory.

Tier-2 sampling strategy (from GEPA v3 brief):
    Trigger: Random 5% sample of all evaluations per generation.
    Trigger: Any score in the "uncertain zone" (0.35-0.70) from Tier-1.
    Tier-2 Models: qwen/qwen3-8b or deepseek/deepseek-chat
    Metric: Cohen's Kappa. If Kappa < 0.6 for 2 consecutive generations → pause evolution.

Usage (post-Phase 2):
    from evolution.core.observatory.appeals import Tier2Sampler

    sampler = Tier2Sampler(logger)
    result = sampler.audit_skill(skill_name="github-code-review")
    print(result.message)
"""

from dataclasses import dataclass
from typing import Optional, Any, Tuple
import numpy as np

from evolution.core.observatory.logger import JudgeAuditLogger, get_logger


# ─────────────────────────────────────────────────────────────────────────────
# Kappa computation
# ─────────────────────────────────────────────────────────────────────────────

def cohens_kappa(tier1_scores: list[float], tier2_scores: list[float]) -> float:
    """Compute Cohen's Kappa between two sets of ordinal scores.

    Bins scores into buckets: [0.0-0.35), [0.35-0.70), [0.70-1.0]
    to match the uncertain-zone sampling logic.
    """
    if len(tier1_scores) != len(tier2_scores) or not tier1_scores:
        return 0.0

    def bucket(s: float) -> int:
        if s < 0.35:
            return 0
        elif s < 0.70:
            return 1
        return 2

    t1_cats = [bucket(s) for s in tier1_scores]
    t2_cats = [bucket(s) for s in tier2_scores]

    n = len(t1_cats)
    cats = [0, 1, 2]

    # Observed agreement
    observed = sum(1 for a, b in zip(t1_cats, t2_cats) if a == b) / n

    # Expected agreement (by chance)
    expected = 0.0
    for c in cats:
        p1 = t1_cats.count(c) / n
        p2 = t2_cats.count(c) / n
        expected += p1 * p2

    if expected == 1.0:
        return 1.0  # Perfect agreement

    kappa = (observed - expected) / (1.0 - expected)
    return float(np.clip(kappa, -1.0, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AppealTask:
    """A task selected for Tier-2 re-evaluation."""
    generation: int
    skill_name: str
    task_id: str
    tier1_score: float
    reason: str  # "random_sample" | "uncertain_zone"


@dataclass
class Tier2AuditResult:
    """Result of a Tier-2 audit for a skill."""
    skill_name: str
    n_sampled: int
    n_uncertain: int
    n_random: int
    n_total_in_generation: int
    kappa: float
    agreement_rate: float
    sufficient: bool
    message: str
    tier1_mean: float
    tier2_mean: float
    tier1_scores: list[float]
    tier2_scores: list[float]


# ─────────────────────────────────────────────────────────────────────────────
# Tier-2 Sampler
# ─────────────────────────────────────────────────────────────────────────────

class Tier2Sampler:
    """Select judge calls for Tier-2 re-evaluation and track Cohen's Kappa."""

    UNCERTAIN_ZONE = (0.35, 0.70)
    RANDOM_SAMPLE_RATE = 0.05  # 5% random sample
    KAPPA_THRESHOLD = 0.6
    KAPPA_CONSECUTIVE_BREACHES_FOR_HALT = 2
    TIER2_MODELS = ["qwen/qwen3-8b", "deepseek/deepseek-chat-v3"]

    def __init__(self, logger: Optional[JudgeAuditLogger] = None):
        self._logger = logger or get_logger()
        self._kappa_history: list[float] = []
        self._tier2_judge: Optional[Any] = None  # Cached tuple (judge, model_name)

    def _get_tier2_judge(self) -> Optional[Tuple[Any, str]]:
        """Lazy-load the first working Tier-2 judge and cache it."""
        if self._tier2_judge is not None:
            return self._tier2_judge
        from evolution.core.fitness import LLMJudge
        from evolution.core.config import EvolutionConfig
        for model in self.TIER2_MODELS:
            try:
                config = EvolutionConfig(judge_model=model)
                judge = LLMJudge(config)
                self._tier2_judge = (judge, model)
                return self._tier2_judge
            except Exception:
                continue
        return None

    def sample_for_appeals(
        self,
        generation: int,
        tier1_results: list[dict],
    ) -> list[AppealTask]:
        """Select tasks for Tier-2 re-evaluation.

        Parameters
        ----------
        generation : int
            Current GEPA generation number.
        tier1_results : list of dict
            Each dict must have: task_id, skill_name, raw_score.
            All must already be logged to the audit table.

        Returns
        -------
        list[AppealTask]
            Tasks selected for Tier-2 re-evaluation.
        """
        import random

        selected: list[AppealTask] = []

        for item in tier1_results:
            task_id = item["task_id"]
            skill_name = item["skill_name"]
            score = item["raw_score"]

            reason: Optional[str] = None

            # 5% random sample
            if random.random() < self.RANDOM_SAMPLE_RATE:
                reason = "random_sample"
            # Uncertain zone
            elif self.UNCERTAIN_ZONE[0] <= score <= self.UNCERTAIN_ZONE[1]:
                reason = "uncertain_zone"

            if reason:
                selected.append(AppealTask(
                    generation=generation,
                    skill_name=skill_name,
                    task_id=task_id,
                    tier1_score=score,
                    reason=reason,
                ))

        return selected

    def record_tier2_scores(
        self,
        appeals: list[AppealTask],
        tier2_scores: list[float],
    ) -> None:
        """Record Tier-2 scores for previously sampled appeals.

        Logs them to the audit table with model_used indicating Tier-2.
        """
        for appeal, score in zip(appeals, tier2_scores):
            self._logger.log(
                generation=appeal.generation,
                skill_name=appeal.skill_name,
                model_used=f"TIER2::{appeal.tier1_score}",  # marker
                task_id=appeal.task_id,
                expected_behavior="[TIER2_APPEAL]",
                actual_behavior="[TIER2]",
                rubric=f"[TIER2] reason={appeal.reason}",
                raw_score=score,
                latency_ms=None,
                token_cost_estimate=None,
                error_flag=None,
            )

    def check_kappa(
        self,
        generation: int,
        tier1_scores: list[float],
        tier2_scores: list[float],
    ) -> dict:
        """Compute Cohen's Kappa for a set of Tier-1/Tier-2 paired scores.

        Returns a dict with:
            kappa, sufficient, message, consecutive_breaches
        """
        if len(tier1_scores) != len(tier2_scores) or len(tier1_scores) < 3:
            return {
                "kappa": 0.0,
                "sufficient": False,
                "message": "Not enough paired scores to compute Kappa",
                "consecutive_breaches": 0,
            }

        kappa = cohens_kappa(tier1_scores, tier2_scores)
        self._kappa_history.append(kappa)

        sufficient = kappa >= self.KAPPA_THRESHOLD
        consecutive_breaches = self._count_consecutive_breaches()

        if sufficient:
            message = f"Kappa={kappa:.3f} >= {self.KAPPA_THRESHOLD} — Tier-1 calibrated"
        else:
            message = (
                f"Kappa={kappa:.3f} < {self.KAPPA_THRESHOLD} — "
                f"Tier-1 miscalibrated ({consecutive_breaches} consecutive breaches)"
            )

        return {
            "kappa": kappa,
            "sufficient": sufficient,
            "message": message,
            "consecutive_breaches": consecutive_breaches,
            "halt_recommended": consecutive_breaches >= self.KAPPA_CONSECUTIVE_BREACHES_FOR_HALT,
        }

    def _count_consecutive_breaches(self) -> int:
        """Count consecutive generations where kappa < threshold, from newest backward."""
        count = 0
        for k in reversed(self._kappa_history):
            if k < self.KAPPA_THRESHOLD:
                count += 1
            else:
                break
        return count

    def audit_skill(self, skill_name: str) -> Tier2AuditResult:
        """Run a Tier-2 audit for the most recent generation of a skill.

        Fetches all Tier-1 evaluations from the audit log for the latest
        generation, re-evaluates the uncertain-zone and random-sample tasks
        with a Tier-2 model, computes Cohen's Kappa.

        Returns Tier2AuditResult.
        """
        import random

        gens = self._logger.generations_with_data()
        if not gens:
            return Tier2AuditResult(
                skill_name=skill_name, n_sampled=0, n_uncertain=0, n_random=0,
                n_total_in_generation=0, kappa=0.0, agreement_rate=0.0,
                sufficient=False, message="No audit data found", tier1_mean=0.0,
                tier2_mean=0.0, tier1_scores=[], tier2_scores=[],
            )

        latest_gen = max(gens)
        conn = self._logger.connection()

        # Fetch all Tier-1 entries for this skill+generation
        rows = conn.execute(
            """SELECT id, task_id, expected_behavior, actual_behavior,
                      raw_score
               FROM   judge_audit_log
               WHERE  skill_name = ? AND generation = ?
                 AND  error_flag IS NULL
               ORDER BY id""",
            (skill_name, latest_gen),
        ).fetchall()

        if not rows:
            return Tier2AuditResult(
                skill_name=skill_name, n_sampled=0, n_uncertain=0, n_random=0,
                n_total_in_generation=0, kappa=0.0, agreement_rate=0.0,
                sufficient=False, message=f"No entries for gen {latest_gen}", tier1_mean=0.0,
                tier2_mean=0.0, tier1_scores=[], tier2_scores=[],
            )

        # Select appeals
        tier1_scores: list[float] = []
        tier2_scores: list[float] = []
        n_uncertain = 0
        n_random = 0

        for row in rows:
            row_id, task_id, expected, actual, raw_score = row
            tier1_scores.append(float(raw_score))

            # Check selection criteria
            is_random = random.random() < self.RANDOM_SAMPLE_RATE
            in_uncertain = self.UNCERTAIN_ZONE[0] <= float(raw_score) <= self.UNCERTAIN_ZONE[1]

            if not (is_random or in_uncertain):
                continue

            if is_random:
                n_random += 1
            if in_uncertain:
                n_uncertain += 1

            # Call Tier-2 judge
            tier2_score = self._call_tier2_judge(
                task_input=task_id,
                expected_behavior=expected,
                actual_behavior=actual,
            )
            tier2_scores.append(tier2_score)

        n_sampled = len(tier2_scores)
        n_total = len(rows)

        # Compute Kappa
        if n_sampled < 3:
            kappa = 0.0
            agreement = 0.0
            sufficient = False
            message = f"Only {n_sampled} sampled — need ≥3 for Kappa"
        else:
            kappa = cohens_kappa(tier1_scores, tier2_scores)
            cats1 = [self._bucket(s) for s in tier1_scores]
            cats2 = [self._bucket(s) for s in tier2_scores]
            agreement = sum(a == b for a, b in zip(cats1, cats2)) / n_sampled
            sufficient = kappa >= self.KAPPA_THRESHOLD
            message = (
                f"kappa={kappa:.3f} ({'calibrated' if sufficient else 'MISCALIBRATED'}), "
                f"{n_sampled}/{n_total} sampled, "
                f"uncertain={n_uncertain}, random={n_random}"
            )

        self._kappa_history.append(kappa)
        t1_mean = float(np.mean(tier1_scores)) if tier1_scores else 0.0
        t2_mean = float(np.mean(tier2_scores)) if tier2_scores else 0.0

        return Tier2AuditResult(
            skill_name=skill_name,
            n_sampled=n_sampled,
            n_uncertain=n_uncertain,
            n_random=n_random,
            n_total_in_generation=n_total,
            kappa=kappa,
            agreement_rate=agreement,
            sufficient=sufficient,
            message=message,
            tier1_mean=t1_mean,
            tier2_mean=t2_mean,
            tier1_scores=tier1_scores,
            tier2_scores=tier2_scores,
        )

    def _bucket(self, s: float) -> int:
        """Map score to bucket index."""
        if s < 0.35:
            return 0
        elif s < 0.70:
            return 1
        return 2

    def _call_tier2_judge(
        self,
        task_input: str,
        expected_behavior: str,
        actual_behavior: str,
    ) -> float:
        """Call Tier-2 judge using a cached secondary model."""
        judge_tuple = self._get_tier2_judge()
        if judge_tuple is None:
            return 0.5  # fallback if all Tier-2 models fail
        judge, _ = judge_tuple
        try:
            fs = judge.score(
                task_input=task_input,
                expected_behavior=expected_behavior,
                agent_output=actual_behavior,
                skill_text="",  # Tier-2 doesn't use skill body
            )
            return fs.correctness
        except Exception:
            # If the cached judge fails, invalidate cache and try once more
            self._tier2_judge = None
            judge_tuple = self._get_tier2_judge()
            if judge_tuple is None:
                return 0.5
            judge, _ = judge_tuple
            try:
                fs = judge.score(
                    task_input=task_input,
                    expected_behavior=expected_behavior,
                    agent_output=actual_behavior,
                    skill_text="",
                )
                return fs.correctness
            except Exception:
                return 0.5
