"""Tests for BacktrackController."""

from evolution.core.backtrack import BacktrackController
from evolution.core.types import EvolutionSnapshot


def test_backtrack_continue_insufficient_data():
    """Should continue when fewer than 3 checkpoints exist."""
    controller = BacktrackController(window_size=3, plateau_threshold=0.01)
    controller.checkpoint(EvolutionSnapshot(1, "body1", 0.5, "", "t1"))
    controller.checkpoint(EvolutionSnapshot(2, "body2", 0.6, "", "t2"))

    decision = controller.should_backtrack(0.65)
    assert decision.action == "continue"


def test_backtrack_plateau_detected():
    """Should backtrack when 3 consecutive scores are within 1% range."""
    controller = BacktrackController(window_size=3, plateau_threshold=0.01)
    controller.checkpoint(EvolutionSnapshot(4, "body4", 0.50, "", "t4"))
    controller.checkpoint(EvolutionSnapshot(5, "body5", 0.51, "", "t5"))
    controller.checkpoint(EvolutionSnapshot(6, "body6", 0.50, "", "t6"))

    decision = controller.should_backtrack(0.50)
    assert decision.action == "backtrack"


def test_backtrack_continue_improving():
    """Should continue when scores are still improving beyond threshold."""
    controller = BacktrackController(window_size=3, plateau_threshold=0.01)
    controller.checkpoint(EvolutionSnapshot(4, "body4", 0.50, "", "t4"))
    controller.checkpoint(EvolutionSnapshot(5, "body5", 0.60, "", "t5"))
    controller.checkpoint(EvolutionSnapshot(6, "body6", 0.70, "", "t6"))

    decision = controller.should_backtrack(0.75)
    assert decision.action == "continue"


def test_force_archive_after_three_backtracks():
    """Should force archive after 3 consecutive backtracks."""
    controller = BacktrackController(max_consecutive_backtracks=3)
    # Simulate 3 backtracks
    for _ in range(3):
        decision = controller.should_backtrack(0.50)
        controller.backtrack_count += 1

    decision = controller.should_backtrack(0.50)
    assert decision.action == "force_archive"


def test_reset_after_improvement():
    """Backtrack count should reset after a non-backtrack iteration."""
    controller = BacktrackController()
    controller.backtrack_count = 2
    controller.reset()
    assert controller.backtrack_count == 0


def test_execute_backtrack_returns_last_good_checkpoint():
    """execute_backtrack should walk back to the last checkpoint with >1% gain."""
    controller = BacktrackController()
    controller.checkpoint(EvolutionSnapshot(1, "body1", 0.40, "", "t1"))
    controller.checkpoint(EvolutionSnapshot(2, "body2", 0.42, "", "t2"))
    controller.checkpoint(EvolutionSnapshot(3, "body3", 0.45, "", "t3"))
    controller.checkpoint(EvolutionSnapshot(4, "body4", 0.45, "", "t4"))
    controller.checkpoint(EvolutionSnapshot(5, "body5", 0.44, "", "t5"))

    restored = controller.execute_backtrack()
    assert restored is not None
    # Iteration 5 plateaued — should revert to iteration 3 (last >1% gain from iter 1)
    assert restored.iteration <= 3
