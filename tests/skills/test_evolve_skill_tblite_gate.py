"""Tests for TBLite benchmark gate configuration."""

import click
import pytest
from click.testing import CliRunner

from evolution.core.config import EvolutionConfig
from evolution.skills.evolve_skill import _run_tblite_gate_if_requested, main


def test_tblite_gate_is_skipped_when_disabled():
    config = EvolutionConfig(run_tblite=False)

    _run_tblite_gate_if_requested(config)


def test_tblite_gate_fails_loudly_when_enabled_until_implemented():
    config = EvolutionConfig(run_tblite=True)

    with pytest.raises(click.ClickException) as exc_info:
        _run_tblite_gate_if_requested(config)

    message = str(exc_info.value)
    assert "TBLite" in message
    assert "not implemented" in message
    assert "run_tblite=False" in message


def test_run_tblite_cli_option_is_exposed_in_help():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--run-tblite" in result.output
