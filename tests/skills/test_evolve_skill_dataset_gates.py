"""Tests for evolution dataset gates."""

import click
import pytest

from evolution.core.dataset_builder import EvalDataset, EvalExample
from evolution.skills.evolve_skill import _require_non_empty_holdout


def _example(i=1):
    return EvalExample(
        task_input=f"task {i}",
        expected_behavior=f"expected {i}",
        source="test",
    )


def test_holdout_gate_accepts_dataset_with_holdout_examples():
    dataset = EvalDataset(
        train=[_example(1)],
        val=[_example(2)],
        holdout=[_example(3)],
    )

    _require_non_empty_holdout(dataset)


def test_holdout_gate_rejects_empty_holdout_with_actionable_error():
    dataset = EvalDataset(train=[_example(1)], val=[_example(2)], holdout=[])

    with pytest.raises(click.ClickException) as exc_info:
        _require_non_empty_holdout(dataset)

    message = str(exc_info.value)
    assert "holdout" in message.lower()
    assert "0 holdout" in message
    assert "cannot compute" in message.lower()
