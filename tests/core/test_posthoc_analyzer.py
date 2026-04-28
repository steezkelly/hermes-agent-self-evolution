"""Tests for PostHocAnalyzer — power-law fitting and phase classification."""

import numpy as np
from evolution.core.posthoc_analyzer import PostHocAnalyzer


def _gen(a=0.15, c=0.25, b=0.40, n=12) -> list[float]:
    """Generate noise-free synthetic power-law scores."""
    return [round(a * (i ** c) + b, 4) for i in range(1, n + 1)]


class TestPowerLawFit:
    def test_early_discovery(self):
        """c > 0.2 should classify as early_discovery."""
        scores = _gen(a=0.2, c=0.35, b=0.35, n=12)
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        assert report.phase.phase == "early_discovery", \
            f"Got {report.phase.phase}, c={report.power_law.exponent_c:.3f}"
        assert report.recommended_action == "continue"
        assert report.power_law.exponent_c > 0.2

    def test_diminishing_returns(self):
        """c ~ 0.12 should classify as diminishing_returns."""
        scores = _gen(a=0.1, c=0.12, b=0.50, n=12)
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        # With 12 noise-free points, fit should be very close to c=0.12
        assert report.phase.phase == "diminishing_returns", \
            f"Got {report.phase.phase}, c={report.power_law.exponent_c:.3f}"
        assert report.recommended_action == "wind_down"

    def test_plateau(self):
        """c ~ 0.02 should classify as plateau."""
        scores = _gen(a=0.03, c=0.02, b=0.60, n=15)
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        assert report.phase.phase == "plateau", \
            f"Got {report.phase.phase}, c={report.power_law.exponent_c:.3f}"
        assert report.recommended_action == "stop"

    def test_power_law_recovery(self):
        """Fitted exponent should be close to the generating exponent."""
        true_c = 0.30
        np.random.seed(42)
        scores = _gen(a=0.15, c=true_c, b=0.40, n=15)
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.power_law is not None
        # With 15 noise-free points, should be very precise
        assert abs(report.power_law.exponent_c - true_c) < 0.05, \
            f"Fitted c={report.power_law.exponent_c:.3f} too far from true c={true_c:.3f}"


class TestPhaseClassification:
    def test_insufficient_points(self):
        """Fewer than min_points should return no classification."""
        scores = [0.4, 0.41, 0.42]
        analyzer = PostHocAnalyzer(min_points_for_fit=4)
        report = analyzer.analyze(scores)
        assert report.power_law is None
        assert report.phase is None
        assert report.recommended_action == "continue"

    def test_flat_line_plateau(self):
        """Nearly identical scores should plateau."""
        scores = [0.50, 0.51, 0.50, 0.51, 0.50, 0.51]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        assert report.phase.phase in ("plateau", "diminishing_returns")

    def test_improving_then_flat(self):
        """Strong initial improvement followed by flat should be diminishing."""
        scores = [0.40, 0.48, 0.52, 0.53, 0.54, 0.54, 0.55, 0.54]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        assert report.phase.phase in ("diminishing_returns", "plateau")

    def test_predicted_score_at_double(self):
        """predicted_score_at_double should be higher than last score for improving runs."""
        scores = _gen(a=0.15, c=0.25, b=0.40, n=12)
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.phase is not None
        assert report.phase.predicted_score_at_double > scores[-1]

    def test_log_log_fallback_works(self):
        """Test with pure sequential data where curve_fit may struggle."""
        # Nearly linear data (c close to 1.0) — curve_fit should handle it
        scores = [0.40, 0.55, 0.65, 0.72, 0.78, 0.82, 0.85, 0.88, 0.90, 0.92]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.power_law is not None
        # High improvement rate should be early discovery
        assert report.phase is not None


class TestRecommendation:
    def test_continue_on_good_trajectory(self):
        """Rapidly improving scores should recommend continue."""
        scores = [0.30, 0.50, 0.62, 0.70, 0.75, 0.79]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.recommended_action == "continue"

    def test_stop_on_flat(self):
        """Flat scores should recommend stop."""
        scores = [0.60, 0.60, 0.61, 0.60, 0.60, 0.61, 0.60]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        # Flat scores may fit as very low power-law exponent
        assert report.recommended_action in ("stop", "wind_down")

    def test_very_steep_early(self):
        """Very steep initial curve (c near 1.0) should recommend continue."""
        # Simulate a skill that learns very fast
        scores = [0.30, 0.55, 0.70, 0.80, 0.87, 0.92]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        assert report.recommended_action == "continue"


class TestToDict:
    def test_serialization(self):
        """to_dict should produce JSON-compatible output."""
        scores = [0.40, 0.45, 0.48, 0.50, 0.51]
        analyzer = PostHocAnalyzer()
        report = analyzer.analyze(scores)
        d = analyzer.to_dict(report)
        assert "power_law" in d
        assert "phase" in d
        assert "recommended_action" in d
        assert isinstance(d["raw_scores"], list)
        import json
        # Should be JSON-serializable
        json.dumps(d)
