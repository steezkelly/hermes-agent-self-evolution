"""Tests for the skill-drift fixture demo."""

import json
import sys
import tempfile
from pathlib import Path


def _run_fixture(out_dir: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evolution.core.skill_drift_demo import run_skill_drift_fixture

    return run_skill_drift_fixture(out_dir)


def test_fixture_verdict_is_pass():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["verdict"] == "pass"


def test_fixture_baseline_fails():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["baseline"]["passed"] is False


def test_fixture_candidate_passes():
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_fixture(Path(tmp))
        assert result["candidate"]["passed"] is True


def test_fixture_emits_four_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        assert (out / "run_report.json").is_file()
        assert (out / "skill_diff.txt").is_file()
        assert (out / "promotion_dossier.md").is_file()
        assert (out / "artifact_manifest.json").is_file()


def test_skill_diff_has_content():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        diff_text = (out / "skill_diff.txt").read_text()
        assert len(diff_text) > 0
        assert "+" in diff_text or "-" in diff_text


def test_fixture_safety_block():
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
