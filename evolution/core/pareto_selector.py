"""Pareto Selector — multi-objective candidate selection.

Selects the best candidate between baseline and evolved skill using
two quality dimensions: holdout score (primary) and skill size delta
(secondary). No automatic text merging is attempted (GEPA produces
whole-text replacements, not clean diffs).

The robustness gate runs BEFORE this selector. If robustness checks
failed, the selector skips the evolved candidate entirely.
"""

from dataclasses import dataclass


@dataclass
class SelectionResult:
    body: str
    source: str          # "evolved" | "baseline"
    holdout_score: float
    improvement_vs_baseline: float
    size_growth_ratio: float


class ParetoSelector:
    """Select the best candidate between baseline and evolved.

    Quality dimensions:
    1. Holdout score (primary, weight=0.85)
    2. Skill size delta (secondary, weight=0.15)
       Penalizes growth beyond a configurable threshold (default 20%).

    The size penalty formula:
        size_penalty = max(0, 1.0 - max(0, growth_ratio - growth_threshold))
        growth_ratio = (evolved_size - baseline_size) / baseline_size

    Weighted score:
        weighted = holdout * 0.85 + size_penalty * 0.15

    If robustness checks failed on the evolved candidate, returns baseline.
    If both are roughly equal (delta < 0.005), baseline is preferred (conservative).
    """

    def __init__(self, holdout_weight: float = 0.85,
                 size_weight: float = 0.15,
                 growth_threshold: float = 0.2,
                 min_improvement_delta: float = 0.03):
        self.holdout_weight = holdout_weight
        self.size_weight = size_weight
        self.growth_threshold = growth_threshold
        self.min_improvement_delta = min_improvement_delta

    def select(
        self,
        baseline_body: str,
        baseline_score: float,
        evolved_body: str,
        evolved_score: float,
        robustness_passed: bool = True,
    ) -> SelectionResult:
        """Select the best candidate.

        Args:
            baseline_body: Original skill body.
            baseline_score: Holdout score of baseline.
            evolved_body: Evolved skill body.
            evolved_score: Holdout score of evolved.
            robustness_passed: True if all robustness checks passed.

        Returns:
            SelectionResult with the selected body and source label.
        """
        if not robustness_passed:
            return SelectionResult(
                body=baseline_body,
                source="baseline",
                holdout_score=baseline_score,
                improvement_vs_baseline=evolved_score - baseline_score,
                size_growth_ratio=self._growth_ratio(baseline_body, evolved_body),
            )

        improvement = evolved_score - baseline_score

        # If improvement is below noise floor, prefer baseline
        if improvement < self.min_improvement_delta:
            return SelectionResult(
                body=baseline_body,
                source="baseline",
                holdout_score=baseline_score,
                improvement_vs_baseline=improvement,
                size_growth_ratio=self._growth_ratio(baseline_body, evolved_body),
            )

        growth_ratio = self._growth_ratio(baseline_body, evolved_body)

        # Compute size penalty: 0 = no penalty, 1 = full penalty
        excess_growth = max(0.0, growth_ratio - self.growth_threshold)
        size_penalty = min(1.0, excess_growth)

        # Weighted score
        evolved_weighted = evolved_score * self.holdout_weight + (1.0 - size_penalty) * self.size_weight
        baseline_weighted = baseline_score * self.holdout_weight + 1.0 * self.size_weight

        if evolved_weighted > baseline_weighted:
            return SelectionResult(
                body=evolved_body,
                source="evolved",
                holdout_score=evolved_score,
                improvement_vs_baseline=improvement,
                size_growth_ratio=growth_ratio,
            )
        else:
            return SelectionResult(
                body=baseline_body,
                source="baseline",
                holdout_score=baseline_score,
                improvement_vs_baseline=improvement,
                size_growth_ratio=growth_ratio,
            )

    @staticmethod
    def _growth_ratio(baseline_body: str, evolved_body: str) -> float:
        """Compute size growth ratio of evolved vs baseline."""
        baseline_size = max(len(baseline_body), 1)
        evolved_size = len(evolved_body)
        return (evolved_size - baseline_size) / baseline_size
