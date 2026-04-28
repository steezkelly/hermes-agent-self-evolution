"""Shared dataclass types for the GEPA v2 evolution pipeline.

All v2 modules import from here to avoid circular dependencies and
data-type sprawl. Module-specific types stay in their own modules.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvolutionSnapshot:
    """State at one iteration of the evolution loop."""
    iteration: int
    skill_body: str
    score: float
    variation_explanation: str
    timestamp: str
    branch: str = "single"


@dataclass
class RouterDecision:
    """Output of the Router: what to do with the current iteration's result."""
    action: str                    # "fix" | "extend" | "abstain"
    confidence: float              # 0.0-1.0
    rationale: str                 # for logging + human review
    failure_pattern: str           # "edge_case" | "structural" | "coverage" | "noise"


@dataclass
class ScenarioResult:
    """Per-example score from evaluation."""
    scenario_id: str
    passed: bool
    score: float
    failure_reason: str
    output: str


@dataclass
class BacktrackDecision:
    """Output of BacktrackController."""
    action: str                    # "continue" | "backtrack" | "force_archive"
    rationale: str
    target_checkpoint: Optional[int] = None


@dataclass
class ComputeBudget:
    """Compute allocation for an evolution run."""
    max_iterations: int
    total_metric_calls: int


@dataclass
class StopDecision:
    """Output of OptimizationController.should_stop()."""
    action: str                    # "hard_stop" | "soft_stop" | "continue"
    rationale: str
    iteration_count: int
    predicted_next_gain: Optional[float] = None


@dataclass
class EvolutionReport:
    """Final output of a v2 evolution run."""
    skill_name: str
    n_iterations_executed: int
    improvement: float
    recommendation: str = "review"
    details: str = ""
    router_decision: Optional[RouterDecision] = None
    backtrack_decision: Optional[BacktrackDecision] = None
    elapsed_seconds: float = 0.0
