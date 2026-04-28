"""Backtrack Controller — plateau detection with checkpoint rollback.

Checkpoints after every iteration where score improved. Uses a 3-iteration
sliding window for noise-robust plateau detection. Reverts to the last
checkpoint with non-trivial gain. Force-archives after 3 consecutive backtracks.

Force-archive workflow: skill is logged to output/<skill>/archived/<timestamp>/
Human review required before retry. No auto-retry permitted.
"""

from typing import Optional
from datetime import datetime

from evolution.core.types import EvolutionSnapshot, BacktrackDecision


class BacktrackController:
    """Monitors for plateau conditions and rolls back to last good state.

    Plateau detection uses a 3-iteration sliding window:
        window = last min(3, len(checkpoints)) snapshots
        if max(window.scores) - min(window.scores) < threshold (default 0.01)
            → plateau detected

    The 3-iteration window and 1% threshold are pragmatic heuristics.
    The window size balances responsiveness (smaller = faster detection)
    against noise immunity (larger = fewer false positives). The 1% threshold
    is near the LLM evaluation noise floor (~±2-5%) — this means the window
    may detect score noise rather than true capability ceilings. Validation
    against actual holdout score distributions is recommended.

    On backtrack, walks backward through all checkpoints to find the LAST
    checkpoint where improvement > 1% of cumulative gain. Reverts to that
    checkpoint. If none found, reverts to checkpoint N-2.
    """

    def __init__(self, window_size: int = 3, plateau_threshold: float = 0.01,
                 max_consecutive_backtracks: int = 3):
        self.window_size = window_size
        self.plateau_threshold = plateau_threshold
        self.max_consecutive_backtracks = max_consecutive_backtracks

        self.checkpoints: list[EvolutionSnapshot] = []
        self.backtrack_count: int = 0

    def checkpoint(self, snapshot: EvolutionSnapshot) -> None:
        """Record a checkpoint. Call after every iteration where score stabilized."""
        self.checkpoints.append(snapshot)

    def checkpoint_for_score(self, score: float, body: str, frontmatter: str, iteration: int) -> None:
        """Convenience: record a checkpoint from raw score/body values."""
        snapshot = EvolutionSnapshot(
            iteration=iteration,
            skill_body=body,
            score=score,
            variation_explanation="",
            timestamp=datetime.now().isoformat(),
        )
        self.checkpoints.append(snapshot)

    def should_backtrack(self, current_score: float) -> BacktrackDecision:
        """Check plateau conditions against sliding window.

        Uses epsilon comparison to avoid floating-point precision issues
        with the threshold check.
        """
        if self.backtrack_count >= self.max_consecutive_backtracks:
            return BacktrackDecision(
                action="force_archive",
                rationale=(f"Max consecutive backtracks ({self.max_consecutive_backtracks}) "
                           f"reached. Skill appears untrainable with current config. "
                           f"Archived for human review."),
            )

        if len(self.checkpoints) < self.window_size:
            return BacktrackDecision(action="continue", rationale="Not enough history for plateau detection")

        # Sliding window: last N checkpoints
        window = self.checkpoints[-self.window_size:]
        scores = [s.score for s in window]
        score_range = max(scores) - min(scores)

        # Epsilon comparison for floating-point precision
        if score_range <= self.plateau_threshold + 1e-10:
            self.backtrack_count += 1
            return BacktrackDecision(
                action="backtrack",
                rationale=(f"Plateau detected: score range {score_range:.4f} "
                           f"over last {self.window_size} iterations "
                           f"(threshold: {self.plateau_threshold}). "
                           f"Backtrack count: {self.backtrack_count}/{self.max_consecutive_backtracks}."),
            )

        return BacktrackDecision(action="continue", rationale=f"Score range {score_range:.4f} above threshold")

    def execute_backtrack(self) -> Optional[EvolutionSnapshot]:
        """Walk back to the last checkpoint before the plateau started.

        Walks backward from the end, finds the first PAIR of adjacent
        checkpoints where the USABLE gain (>1% improvement over previous)
        occurs. Returns the earlier checkpoint in that pair — the last
        state before the skill stopped meaningfully improving.

        If none found, returns checkpoint at index -3 (N-2).
        """
        if not self.checkpoints:
            return None

        first_score = self.checkpoints[0].score
        if first_score == 0:
            first_score = 1e-9

        # Walk backward, find first adjacent improvement > 1%
        for i in range(len(self.checkpoints) - 1, 0, -1):
            prev_score = self.checkpoints[i - 1].score
            curr_score = self.checkpoints[i].score
            gain = (curr_score - prev_score) / first_score
            if gain > 0.01:
                # Found the last meaningful improvement — return the state
                # JUST BEFORE this improvement (the "last good" state)
                return self.checkpoints[i - 1]

        # No significant adjacent improvement anywhere — revert to N-2
        if len(self.checkpoints) >= 3:
            return self.checkpoints[-3]
        elif len(self.checkpoints) >= 1:
            return self.checkpoints[0]
        return None

    def reset(self):
        """Reset backtrack count after a non-backtrack iteration."""
        self.backtrack_count = 0

    def reset_full(self):
        """Full reset — clear all checkpoints and backtrack count."""
        self.checkpoints.clear()
        self.backtrack_count = 0
