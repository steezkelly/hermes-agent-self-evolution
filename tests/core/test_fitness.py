"""Tests for skill fitness scoring."""

import dspy
import pytest

from evolution.core import fitness
from evolution.core.fitness import FitnessScore, skill_fitness_metric


def _example(expected="Use the repo workflow and run tests", task="Fix a bug"):
    return dspy.Example(
        task_input=task,
        expected_behavior=expected,
        skill_text="Follow the GitHub workflow skill.",
    )


def _prediction(output="I used the repo workflow and ran tests"):
    return dspy.Prediction(output=output)


class TestSkillFitnessMetric:
    def test_returns_prediction_with_llm_judge_feedback(self, monkeypatch):
        def fake_judge(**kwargs):
            assert kwargs["task_input"] == "Fix a bug"
            assert kwargs["expected_behavior"] == "Use the repo workflow and run tests"
            assert kwargs["agent_output"] == "I used the repo workflow and ran tests"
            assert kwargs["skill_text"] == "Follow the GitHub workflow skill."
            return FitnessScore(
                correctness=0.8,
                procedure_following=0.7,
                conciseness=0.5,
                feedback="Mention the exact test command next time.",
            )

        monkeypatch.setattr(fitness, "_score_with_llm_judge", fake_judge)

        result = skill_fitness_metric(_example(), _prediction())

        assert isinstance(result, dspy.Prediction)
        assert result.score == pytest.approx(0.71)
        assert float(result) == pytest.approx(0.71)
        assert result.feedback == "Mention the exact test command next time."

    def test_falls_back_to_keyword_overlap_with_feedback_when_judge_fails(self, monkeypatch):
        def failing_judge(**kwargs):
            raise RuntimeError("rate limited")

        monkeypatch.setattr(fitness, "_score_with_llm_judge", failing_judge)

        result = skill_fitness_metric(
            _example(expected="alpha beta gamma"),
            _prediction(output="alpha beta"),
        )

        assert isinstance(result, dspy.Prediction)
        assert result.score == pytest.approx(0.3 + 0.7 * (2 / 3))
        assert float(result) == pytest.approx(result.score)
        assert "LLM judge unavailable" in result.feedback
        assert "keyword-overlap fallback" in result.feedback

    def test_empty_output_returns_zero_score_prediction_with_feedback(self, monkeypatch):
        def should_not_call_judge(**kwargs):
            raise AssertionError("judge should not be called for empty output")

        monkeypatch.setattr(fitness, "_score_with_llm_judge", should_not_call_judge)

        result = skill_fitness_metric(_example(), _prediction(output="  \n"))

        assert isinstance(result, dspy.Prediction)
        assert result.score == 0.0
        assert float(result) == 0.0
        assert "empty" in result.feedback.lower()
