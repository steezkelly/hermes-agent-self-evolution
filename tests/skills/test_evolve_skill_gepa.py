"""Regression tests for DSPy 3.x GEPA construction."""

from evolution.skills import evolve_skill


class FakeLM:
    def __init__(self, model):
        self.model = model


def test_create_gepa_optimizer_uses_dspy3_api(monkeypatch):
    """GEPA should use max_metric_calls + reflection_lm, never removed max_steps."""
    captured = {}

    def fake_gepa(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(evolve_skill.dspy, "LM", FakeLM)
    monkeypatch.setattr(evolve_skill.dspy, "GEPA", fake_gepa)

    optimizer = evolve_skill._create_gepa_optimizer(iterations=7, optimizer_model="openai/gpt-4.1")

    assert optimizer is not None
    assert "max_steps" not in captured
    assert captured["max_metric_calls"] == 140
    assert isinstance(captured["reflection_lm"], FakeLM)
    assert captured["reflection_lm"].model == "openai/gpt-4.1"
    assert captured["metric"] is evolve_skill.skill_fitness_metric


def test_create_gepa_optimizer_clamps_zero_iterations_to_one_metric_call(monkeypatch):
    captured = {}

    def fake_gepa(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(evolve_skill.dspy, "LM", FakeLM)
    monkeypatch.setattr(evolve_skill.dspy, "GEPA", fake_gepa)

    evolve_skill._create_gepa_optimizer(iterations=0, optimizer_model="openai/gpt-4.1")

    assert captured["max_metric_calls"] == 1
