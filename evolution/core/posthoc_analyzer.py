"""PostHoc Analyzer — power-law curve fitting and phase classification for evolution runs.

Fits observed iteration scores to a power law of the form:
    score = a * iteration^c + b

Where:
    c > 0.2   → Early Discovery (steep improvement, keep going)
    0.05 < c < 0.2 → Diminishing Returns (slowing, start wrapping up)
    c < 0.05  → Plateau (flatlined, stop now)

Also computes:
- Crossover point: iteration where marginal gain drops below min_improvement_delta
- Predicted score at N more iterations
- Recommended stop iteration

This is a PURELY ANALYTICAL module — no API calls, no LLM calls.
"""

import math
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PowerLawFit:
    """Result of power-law curve fitting."""
    exponent_c: float                # Power-law exponent
    scale_a: float                   # Scale factor
    offset_b: float                  # Baseline offset (starting score)
    r_squared: float                 # Goodness of fit (0-1)
    n_points: int                    # Number of data points used
    convergence: str                 # Whether optimization converged


@dataclass
class PhaseResult:
    """Phase classification output."""
    phase: str                       # "early_discovery" | "diminishing_returns" | "plateau"
    phase_confidence: float          # 0.0-1.0
    crossover_iteration: Optional[int]  # Estimated optimal stop point
    predicted_score_at_double: float    # Score if we run 2x more iterations
    recommended_stop: int            # Suggested max iterations
    marginal_gain_at_stop: float     # Score improvement at recommended stop


@dataclass
class PostHocReport:
    """Complete output of the post-hoc analysis."""
    power_law: Optional[PowerLawFit]
    phase: Optional[PhaseResult]
    raw_scores: list[float]
    filtered_scores: list[float]
    recommended_action: str          # "continue" | "wind_down" | "stop"
    summary: str


class PostHocAnalyzer:
    """Fit power-law curves to evolution iteration scores and classify phases.

    Usage:
        analyzer = PostHocAnalyzer(min_improvement_delta=0.03)
        report = analyzer.analyze(scores=[0.40, 0.45, 0.48, 0.50, 0.51])
    """

    def __init__(
        self,
        min_improvement_delta: float = 0.03,
        diminishing_threshold: float = 0.05,
        discovery_threshold: float = 0.20,
        min_points_for_fit: int = 4,
    ):
        self.min_improvement_delta = min_improvement_delta
        self.diminishing_threshold = diminishing_threshold  # c below this = plateau
        self.discovery_threshold = discovery_threshold      # c above this = early discovery
        self.min_points_for_fit = min_points_for_fit

    def analyze(self, scores: list[float]) -> PostHocReport:
        """Run full post-hoc analysis on a sequence of iteration scores.

        Args:
            scores: List of scores, one per iteration (chronological).
                    iteration 0 = baseline, iteration 1+ = evolved.

        Returns:
            PostHocReport with all analysis results.
        """
        if len(scores) < self.min_points_for_fit:
            return PostHocReport(
                power_law=None,
                phase=None,
                raw_scores=scores,
                filtered_scores=scores,
                recommended_action="continue",
                summary=f"Need at least {self.min_points_for_fit} data points; got {len(scores)}",
            )

        # Fit power law
        power_law = self._fit_power_law(scores)

        # Classify phase
        phase = self._classify_phase(power_law, scores)

        # Determine action
        if phase and phase.phase == "plateau" and phase.phase_confidence > 0.4:
            recommended_action = "stop"
        elif phase and phase.phase == "diminishing_returns":
            recommended_action = "wind_down"
        else:
            recommended_action = "continue"

        # Build summary
        summary = self._build_summary(power_law, phase, scores)

        return PostHocReport(
            power_law=power_law,
            phase=phase,
            raw_scores=scores,
            filtered_scores=scores,
            recommended_action=recommended_action,
            summary=summary,
        )

    def _fit_power_law(self, scores: list[float]) -> Optional[PowerLawFit]:
        """Fit score = a * iteration^c + b via nonlinear least squares.

        Uses scipy for the initial fit, falls back to log-log regression
        if scipy isn't available.
        """
        iterations = np.arange(1, len(scores) + 1, dtype=float)
        scores_arr = np.array(scores, dtype=float)

        # Initial guess: assume a=improvement_span, c=0.3 (moderate power), b=first_score
        improvement_span = scores_arr[-1] - scores_arr[0]
        a_init = max(improvement_span, 0.01)
        c_init = 0.3
        b_init = scores_arr[0]

        try:
            from scipy.optimize import curve_fit

            def power_law_func(x, a, c, b):
                return a * np.power(x, c) + b

            params, pcov = curve_fit(
                power_law_func, iterations, scores_arr,
                p0=[a_init, c_init, b_init],
                bounds=([0.001, -0.5, 0], [2.0, 1.0, 1.0]),
                maxfev=5000,
            )
            a_fit, c_fit, b_fit = params

            # Compute R²
            residuals = scores_arr - power_law_func(iterations, a_fit, c_fit, b_fit)
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((scores_arr - np.mean(scores_arr)) ** 2)
            r_squared = 1 - (ss_res / max(ss_tot, 1e-10))

            convergence = "converged"

        except (ImportError, Exception) as e:
            # Fallback to log-log linear regression
            # score_offset = score - b_init  →  log(score_offset) = log(a) + c * log(iteration)
            logger.debug(f"curve_fit unavailable ({e}), using log-log fallback")

            y_adj = np.maximum(scores_arr - b_init + 1e-10, 1e-10)
            log_x = np.log(iterations)
            log_y = np.log(y_adj)

            # Linear regression on log-log
            n = len(log_x)
            sum_x = np.sum(log_x)
            sum_y = np.sum(log_y)
            sum_xy = np.sum(log_x * log_y)
            sum_x2 = np.sum(log_x ** 2)

            c_fit = (n * sum_xy - sum_x * sum_y) / max(n * sum_x2 - sum_x ** 2, 1e-10)
            log_a_fit = (sum_y - c_fit * sum_x) / n
            a_fit = np.exp(log_a_fit)
            b_fit = b_init

            # Estimate R² from log-log fit
            y_pred = a_fit * np.power(iterations, c_fit) + b_fit
            residuals = scores_arr - y_pred
            ss_res = np.sum(residuals ** 2)
            ss_tot = np.sum((scores_arr - np.mean(scores_arr)) ** 2)
            r_squared = 1 - (ss_res / max(ss_tot, 1e-10))

            convergence = "fallback_loglog"

        return PowerLawFit(
            exponent_c=round(c_fit, 4),
            scale_a=round(a_fit, 4),
            offset_b=round(b_fit, 4),
            r_squared=round(r_squared, 4),
            n_points=len(scores),
            convergence=convergence,
        )

    def _classify_phase(self, power_law: Optional[PowerLawFit],
                        scores: list[float]) -> Optional[PhaseResult]:
        """Classify the current evolution phase from power-law fit."""
        if power_law is None:
            return None

        c = power_law.exponent_c
        r2 = power_law.r_squared

        # Compute recommended stop: where marginal gain < min_improvement_delta
        # For power law: marginal_gain = a * (iteration^c - (iteration-1)^c)
        predicted_stop = len(scores)
        for i in range(len(scores) + 1, len(scores) * 2 + 10):
            gain = power_law.scale_a * (i ** c - (i - 1) ** c)
            if gain < self.min_improvement_delta:
                predicted_stop = i
                break

        # Predicted score at 2x iterations
        double_iter = len(scores) * 2
        predicted_at_double = (
            power_law.scale_a * (double_iter ** c) + power_law.offset_b
        )
        predicted_at_double = min(max(predicted_at_double, 0.0), 1.0)

        # Marginal gain at recommended stop
        if predicted_stop > 1:
            gain_at_stop = power_law.scale_a * (
                predicted_stop ** c - (predicted_stop - 1) ** c
            )
        else:
            gain_at_stop = 0.0

        # Classify phase
        if c < self.diminishing_threshold and r2 > 0.5:
            phase = "plateau"
            conf = min(1.0, max(0.5, (self.diminishing_threshold - c) / self.diminishing_threshold))
        elif c < self.discovery_threshold:
            phase = "diminishing_returns"
            conf = min(1.0, max(0.4, (self.discovery_threshold - c) / self.discovery_threshold))
        else:
            phase = "early_discovery"
            conf = min(1.0, max(0.3, (c - self.discovery_threshold) / self.discovery_threshold + 0.3))

        return PhaseResult(
            phase=phase,
            phase_confidence=round(conf, 4),
            crossover_iteration=predicted_stop if predicted_stop > len(scores) else None,
            predicted_score_at_double=round(predicted_at_double, 4),
            recommended_stop=min(predicted_stop, len(scores) * 2),
            marginal_gain_at_stop=round(gain_at_stop, 4),
        )

    @staticmethod
    def _build_summary(power_law: Optional[PowerLawFit],
                       phase: Optional[PhaseResult],
                       scores: list[float]) -> str:
        """Build a human-readable summary of the analysis."""
        parts = [f"Analyzed {len(scores)} iterations: scores from {scores[0]:.3f} to {scores[-1]:.3f}"]

        if power_law:
            parts.append(
                f"Power-law fit: score = {power_law.scale_a} * iter^{power_law.exponent_c} "
                f"+ {power_law.offset_b} (R²={power_law.r_squared}, {power_law.convergence})"
            )

        if phase:
            parts.append(
                f"Phase: {phase.phase} (confidence: {phase.phase_confidence:.2f})"
            )
            if phase.recommended_stop > len(scores):
                parts.append(
                    f"Recommended stop: iteration {phase.recommended_stop} "
                    f"(crossover when marginal gain < {0.03:.0%})"
                )
            else:
                parts.append("At crossover point already — further iterations unlikely to help")

        return " | ".join(parts)

    def to_dict(self, report: PostHocReport) -> dict:
        """Serialize report to a JSON-compatible dict."""
        return {
            "power_law": asdict(report.power_law) if report.power_law else None,
            "phase": asdict(report.phase) if report.phase else None,
            "raw_scores": report.raw_scores,
            "filtered_scores": report.filtered_scores,
            "recommended_action": report.recommended_action,
            "summary": report.summary,
        }
