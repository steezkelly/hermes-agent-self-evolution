"""Tests for the tool-underuse fixture demo."""

import json
import sys
import tempfile
from pathlib import Path


def _run_fixture(out_dir: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evolution.core.tool_underuse_demo import run_tool_underuse_fixture

    return run_tool_underuse_fixture(out_dir)


def test_fixture_verdict_is_pass():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["verdict"] == "pass", f"verdict={result['verdict']}"


def test_fixture_baseline_fails():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["baseline"]["passed"] is False


def test_fixture_candidate_passes():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["candidate"]["passed"] is True


def test_fixture_tool_call_delta_positive():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["metrics"]["tool_call_delta"] > 0


def test_fixture_emits_four_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        assert (out / "run_report.json").is_file()
        assert (out / "tool_usage_snapshot.json").is_file()
        assert (out / "promotion_dossier.md").is_file()
        assert (out / "artifact_manifest.json").is_file()


def test_baseline_has_zero_tool_calls():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        report = json.loads((out / "run_report.json").read_text())
        assert report["baseline"]["tool_call_count"] == 0


def test_candidate_has_tool_calls():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        report = json.loads((out / "run_report.json").read_text())
        assert report["candidate"]["tool_call_count"] > 0


def test_fixture_no_network_no_external_writes():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        report = json.loads((out / "run_report.json").read_text())
        safety = report["safety"]
        assert safety["network_allowed"] is False
        assert safety["external_writes_allowed"] is False
        assert safety["github_writes_allowed"] is False
        assert safety["production_mutation_allowed"] is False

        manifest = json.loads((out / "artifact_manifest.json").read_text())
        assert manifest["external_writes_allowed"] is False
