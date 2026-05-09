"""Fitness functions for evaluating evolved artifacts.

Uses LLM-as-judge with rubrics to score agent outputs.
Supports length penalties and multi-dimensional scoring.
"""

import dspy
from dataclasses import dataclass
from typing import Optional

from evolution.core.config import EvolutionConfig


@dataclass
class FitnessScore:
    """Multi-dimensional fitness score."""
    correctness: float = 0.0  # Did the agent produce correct output? (0-1)
    procedure_following: float = 0.0  # Did it follow the skill's procedure? (0-1)
    conciseness: float = 0.0  # Was it appropriately concise? (0-1)
    length_penalty: float = 0.0  # Penalty for being too verbose (0-1, 0 = no penalty)
    feedback: str = ""  # Textual feedback for GEPA's reflective analysis

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        raw = (
            0.5 * self.correctness
            + 0.3 * self.procedure_following
            + 0.2 * self.conciseness
        )
        return max(0.0, raw - self.length_penalty)


class LLMJudge:
    """LLM-as-judge scorer with rubric-based evaluation.

    Scores agent outputs on multiple dimensions and provides
    textual feedback that GEPA can use for reflective mutation.
    """

    class JudgeSignature(dspy.Signature):
        """Evaluate an agent's response against an expected behavior rubric.

        Score the response on three dimensions (0.0 to 1.0 each):
        1. correctness: Did the response correctly address the task?
        2. procedure_following: Did it follow the expected approach/procedure?
        3. conciseness: Was it appropriately concise without omitting important info?

        Also provide specific, actionable feedback on what could be improved.
        """
        task_input: str = dspy.InputField(desc="The task the agent was given")
        expected_behavior: str = dspy.InputField(desc="Rubric describing what a good response looks like")
        agent_output: str = dspy.InputField(desc="The agent's actual response")
        skill_text: str = dspy.InputField(desc="The skill/instructions the agent was following")
        correctness: float = dspy.OutputField(desc="Score 0.0-1.0: Did the response correctly address the task?")
        procedure_following: float = dspy.OutputField(desc="Score 0.0-1.0: Did it follow the expected procedure?")
        conciseness: float = dspy.OutputField(desc="Score 0.0-1.0: Appropriately concise?")
        feedback: str = dspy.OutputField(desc="Specific, actionable feedback on what could be improved")

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.judge = dspy.ChainOfThought(self.JudgeSignature)

    def score(
        self,
        task_input: str,
        expected_behavior: str,
        agent_output: str,
        skill_text: str,
        artifact_size: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> FitnessScore:
        """Score an agent output using LLM-as-judge."""

        lm = dspy.LM(self.config.eval_model)

        with dspy.context(lm=lm):
            result = self.judge(
                task_input=task_input,
                expected_behavior=expected_behavior,
                agent_output=agent_output,
                skill_text=skill_text,
            )

        # Parse scores (clamp to 0-1)
        correctness = _parse_score(result.correctness)
        procedure_following = _parse_score(result.procedure_following)
        conciseness = _parse_score(result.conciseness)

        # Length penalty
        length_penalty = 0.0
        if artifact_size is not None and max_size is not None:
            ratio = artifact_size / max_size
            if ratio > 0.9:
                # Penalty ramps from 0 at 90% to 0.3 at 100%+
                length_penalty = min(0.3, (ratio - 0.9) * 3.0)

        return FitnessScore(
            correctness=correctness,
            procedure_following=procedure_following,
            conciseness=conciseness,
            length_penalty=length_penalty,
            feedback=str(result.feedback),
        )


def skill_fitness_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> dspy.Prediction:
    """DSPy-compatible metric function for skill optimization.

    Uses the configured DSPy LM as a rubric judge and returns a
    ``dspy.Prediction(score=..., feedback=...)`` so GEPA can use the
    feedback for reflective mutation. If judge scoring fails (for example
    offline use, rate limits, or missing LM configuration), falls back to the
    old keyword-overlap heuristic with explicit feedback.
    """
    # The prediction should have an 'output' field with the agent's response.
    agent_output = getattr(prediction, "output", "") or ""
    expected = getattr(example, "expected_behavior", "") or ""
    task = getattr(example, "task_input", "") or ""
    skill_text = (
        getattr(example, "skill_text", "")
        or getattr(example, "skill_instructions", "")
        or ""
    )

    if not agent_output.strip():
        return _metric_prediction(0.0, "Agent output was empty, so no task requirements were satisfied.")

    try:
        fitness = _score_with_llm_judge(
            task_input=task,
            expected_behavior=expected,
            agent_output=agent_output,
            skill_text=skill_text,
        )
        feedback = fitness.feedback or _default_feedback(fitness)
        return _metric_prediction(fitness.composite, feedback)
    except Exception as e:
        score, feedback = _keyword_overlap_fallback(expected, agent_output)
        return _metric_prediction(
            score,
            f"LLM judge unavailable ({type(e).__name__}: {e}); "
            f"used keyword-overlap fallback. {feedback}",
        )


def _score_with_llm_judge(
    *,
    task_input: str,
    expected_behavior: str,
    agent_output: str,
    skill_text: str,
) -> FitnessScore:
    """Score a metric example with the currently configured DSPy LM."""
    judge = dspy.ChainOfThought(LLMJudge.JudgeSignature)
    result = judge(
        task_input=task_input,
        expected_behavior=expected_behavior,
        agent_output=agent_output,
        skill_text=skill_text,
    )

    return FitnessScore(
        correctness=_parse_score(result.correctness),
        procedure_following=_parse_score(result.procedure_following),
        conciseness=_parse_score(result.conciseness),
        feedback=str(result.feedback),
    )


def _keyword_overlap_fallback(expected: str, agent_output: str) -> tuple[float, str]:
    """Fallback score matching the previous heuristic, plus GEPA feedback."""
    expected_words = set(expected.lower().split())
    output_words = set(agent_output.lower().split())

    if not expected_words:
        return 0.5, "No expected-behavior rubric was provided; assigned neutral score."

    overlap_count = len(expected_words & output_words)
    overlap = overlap_count / len(expected_words)
    score = 0.3 + (0.7 * overlap)
    return min(1.0, max(0.0, score)), (
        f"Matched {overlap_count}/{len(expected_words)} expected-behavior keywords. "
        "Improve semantic correctness and procedure following, not just word overlap."
    )


def _metric_prediction(score: float, feedback: str) -> dspy.Prediction:
    """Create a GEPA feedback metric result while preserving float coercion."""
    return dspy.Prediction(score=min(1.0, max(0.0, float(score))), feedback=feedback)


def _default_feedback(fitness: FitnessScore) -> str:
    return (
        f"correctness={fitness.correctness:.2f}, "
        f"procedure_following={fitness.procedure_following:.2f}, "
        f"conciseness={fitness.conciseness:.2f}."
    )


def _parse_score(value) -> float:
    """Parse a score value, handling various LLM output formats."""
    if isinstance(value, (int, float)):
        return min(1.0, max(0.0, float(value)))
    try:
        return min(1.0, max(0.0, float(str(value).strip())))
    except (ValueError, TypeError):
        return 0.5  # Default to neutral on parse failure
