"""Thread-safe context for GEPA Observatory metadata injection.

Allows skill_fitness_metric (a DSPy metric function) to receive
generation/skill_name/task_id without changing its signature.

Usage:
    from evolution.core.observatory.context import set_evaluation_context, get_evaluation_context

    # In evolve_skill.py or evolve_content.py, BEFORE calling dspy.GEPA.compile():
    set_evaluation_context(generation=1, skill_name="python-debugpy", session_id="abc123")

    # Inside skill_fitness_metric (called by DSPy), the context is available:
    ctx = get_evaluation_context()
    generation = ctx.generation  # 1
    skill_name = ctx.skill_name  # "python-debugpy"
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class EvaluationContext:
    """Immutable snapshot of the current evaluation context."""
    generation: int = 0
    skill_name: str = "unknown"
    task_id: Optional[str] = None
    session_id: Optional[str] = None
    # Timing — set by the timing decorator
    latency_ms: Optional[int] = None
    # Token cost estimate — set by LM wrapper
    token_cost_estimate: Optional[float] = None


# ─── ContextVar ────────────────────────────────────────────────────────────────

_evaluation_context: ContextVar[EvaluationContext] = ContextVar(
    "evaluation_context",
    default=EvaluationContext(),
)


def set_evaluation_context(
    generation: int = 0,
    skill_name: str = "unknown",
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Set the current evaluation context (thread-safe, non-invasive)."""
    _evaluation_context.set(EvaluationContext(
        generation=generation,
        skill_name=skill_name,
        task_id=task_id,
        session_id=session_id,
    ))


def get_evaluation_context() -> EvaluationContext:
    """Get the current evaluation context (thread-safe)."""
    return _evaluation_context.get()


def update_context_latency(ms: int) -> None:
    """Update latency_ms in the current context."""
    ctx = _evaluation_context.get()
    _evaluation_context.set(EvaluationContext(
        generation=ctx.generation,
        skill_name=ctx.skill_name,
        task_id=ctx.task_id,
        session_id=ctx.session_id,
        latency_ms=ms,
        token_cost_estimate=ctx.token_cost_estimate,
    ))


def update_context_cost(cost: float) -> None:
    """Update token_cost_estimate in the current context."""
    ctx = _evaluation_context.get()
    _evaluation_context.set(EvaluationContext(
        generation=ctx.generation,
        skill_name=ctx.skill_name,
        task_id=ctx.task_id,
        session_id=ctx.session_id,
        latency_ms=ctx.latency_ms,
        token_cost_estimate=cost,
    ))
