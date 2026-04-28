"""Integration tests for GEPA v2 dispatch (dry-run mode, no API calls)."""

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport


def test_v2_dispatch_dry_run():
    """v2 dispatch in dry-run should validate without API calls."""
    report = v2_dispatch(
        skill_name="test-dispatch",
        iterations=10,
        eval_source="synthetic",
        dry_run=True,
    )
    assert isinstance(report, EvolutionReport)
    assert report.skill_name == "test-dispatch"
    assert report.n_iterations_executed == 0
    assert report.recommendation == "review"


def test_v2_dispatch_no_skill():
    """v2 dispatch without a real skill should return reject."""
    report = v2_dispatch(
        skill_name="nonexistent-skill-xyz-999",
        iterations=5,
        dry_run=False,
        eval_source="synthetic",
    )
    assert isinstance(report, EvolutionReport)
    assert report.recommendation == "reject"
    assert "not found" in report.details.lower()


def test_v2_dispatch_returns_report_type():
    """v2 dispatch always returns an EvolutionReport, not None."""
    report = v2_dispatch(
        skill_name="test-dispatch",
        iterations=3,
        dry_run=True,
    )
    assert hasattr(report, "router_decision")
    assert hasattr(report, "backtrack_decision")
    assert hasattr(report, "improvement")
    assert hasattr(report, "recommendation")
