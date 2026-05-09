"""Tests for the session-import fixture demo."""

import json
import os
import sys
import tempfile
from pathlib import Path


def _run_fixture(out_dir: Path) -> dict:
    """Run the session-import fixture and return the summary dict."""
    # Import is inside the function so pytest can collect even if deps missing.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from evolution.core.session_import_demo import run_session_import_fixture

    return run_session_import_fixture(out_dir)


def test_fixture_verdict_is_pass():
    """The deterministic fixture must pass: baseline fails, candidate passes."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = _run_fixture(out)
        assert result["verdict"] == "pass", f"verdict={result['verdict']}"


def test_fixture_baseline_fails():
    """Baseline (raw extractor) must fail."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = _run_fixture(out)
        assert result["baseline"]["passed"] is False


def test_fixture_candidate_passes():
    """Candidate (structured extractor) must pass."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        result = _run_fixture(out)
        assert result["candidate"]["passed"] is True


def test_fixture_emits_four_artifacts():
    """Fixture must emit run_report.json, eval_examples.json, promotion_dossier.md, artifact_manifest.json."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        assert (out / "run_report.json").is_file()
        assert (out / "eval_examples.json").is_file()
        assert (out / "promotion_dossier.md").is_file()
        assert (out / "artifact_manifest.json").is_file()


def test_eval_examples_has_structured_fields():
    """Extracted example must have task_input, expected_behavior, difficulty, category."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        _run_fixture(out)
        examples = json.loads((out / "eval_examples.json").read_text())
        ex = examples["examples"][0]
        assert "task_input" in ex
        assert "expected_behavior" in ex
        assert "difficulty" in ex
        assert "category" in ex
        assert ex["difficulty"] in {"easy", "medium", "hard"}


def test_fixture_no_network_no_external_writes():
    """Safety block must deny all external writes."""
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

        examples = json.loads((out / "eval_examples.json").read_text())
        assert examples["external_writes_allowed"] is False
