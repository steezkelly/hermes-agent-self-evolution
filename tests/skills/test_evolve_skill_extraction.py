"""Regression tests for extracting actually evolved skill text."""

from types import SimpleNamespace

from evolution.skills.evolve_skill import _extract_evolved_skill_body
from evolution.skills.skill_module import (
    _SKILL_BODY_SENTINEL_,
    _SKILL_INSTRUCTION_HEADER,
    SkillModule,
)


def _wrapped(body: str) -> str:
    return f"{_SKILL_INSTRUCTION_HEADER}{body}{_SKILL_BODY_SENTINEL_}fixed wrapper"


def test_extracts_from_nested_predict_signature_instructions():
    module = SkillModule("# Original\nold procedure")
    module.predictor.predict.signature.instructions = _wrapped("# Evolved\nnew procedure")

    evolved = _extract_evolved_skill_body(module, "# Original\nold procedure")

    assert evolved == "# Evolved\nnew procedure"
    assert evolved != module.skill_body


def test_extracts_from_nested_predict_docstring_when_signature_is_stale():
    module = SkillModule("# Original\nold procedure")
    module.predictor.predict.signature.instructions = _wrapped("# Original\nold procedure")
    module.predictor.predict.__doc__ = _wrapped("# Evolved Via Doc\nnew docstring procedure")

    evolved = _extract_evolved_skill_body(module, "# Original\nold procedure")

    assert evolved == "# Evolved Via Doc\nnew docstring procedure"
    assert evolved != module.skill_body


def test_falls_back_to_original_when_optimizer_did_not_mutate_text():
    original = "# Original\nold procedure"
    module = SimpleNamespace(predictor=SimpleNamespace())

    assert _extract_evolved_skill_body(module, original) == original
