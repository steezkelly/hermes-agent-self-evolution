"""Deterministic action-router trace-to-eval demo for Foundry issue #10."""

import json
from pathlib import Path

from click.testing import CliRunner


def test_action_routing_fixture_baseline_fails_candidate_passes(tmp_path):
    from evolution.core.action_routing_demo import run_action_routing_fixture

    result = run_action_routing_fixture(tmp_path)

    assert result["schema_version"] == 1
    assert result["mode"] == "fixture"
    assert result["external_writes_allowed"] is False
    assert result["network_allowed"] is False
    assert result["verdict"] == "pass"
    assert result["metrics"]["baseline_pass_rate"] == 0.0
    assert result["metrics"]["candidate_pass_rate"] == 1.0
    assert result["baseline"]["passed"] is False
    assert result["baseline"]["failures"]
    assert any("owner" in failure for failure in result["baseline"]["failures"])
    assert any("evidence_paths" in failure for failure in result["baseline"]["failures"])
    assert result["candidate"]["passed"] is True
    assert result["candidate"]["failures"] == []


def test_action_routing_fixture_emits_required_artifacts(tmp_path):
    from evolution.core.action_routing_demo import run_action_routing_fixture

    run_action_routing_fixture(tmp_path)

    report = json.loads((tmp_path / "run_report.json").read_text())
    queue = json.loads((tmp_path / "action_queue.json").read_text())
    manifest = json.loads((tmp_path / "artifact_manifest.json").read_text())
    dossier = (tmp_path / "promotion_dossier.md").read_text()

    assert report["verdict"] == "pass"
    assert report["baseline"]["passed"] is False
    assert report["candidate"]["passed"] is True
    assert report["safety"] == {
        "mode": "fixture",
        "network_allowed": False,
        "external_writes_allowed": False,
        "github_writes_allowed": False,
        "production_mutation_allowed": False,
    }

    assert queue["schema_version"] == 1
    assert queue["external_writes_allowed"] is False
    assert len(queue["items"]) == 1
    item = queue["items"][0]
    assert item["bucket"] == "needsSteve"
    assert item["owner"] == "steve"
    assert item["evidence_paths"]
    assert all(Path(path).is_absolute() for path in item["evidence_paths"])
    assert all(Path(path).exists() for path in item["evidence_paths"])
    assert item["next_prompt"].startswith("Work in `/home/steve/repos/steezkelly-hermes-agent-self-evolution`")
    assert item["expires_at"]
    assert len(item["why"]) <= 380

    assert manifest["schema_version"] == 1
    assert manifest["artifacts"]["run_report"] == str(tmp_path / "run_report.json")
    assert manifest["artifacts"]["action_queue"] == str(tmp_path / "action_queue.json")
    assert manifest["artifacts"]["promotion_dossier"] == str(tmp_path / "promotion_dossier.md")
    assert manifest["artifacts"]["artifact_manifest"] == str(tmp_path / "artifact_manifest.json")

    assert "Baseline failed" in dossier
    assert "Candidate passed" in dossier
    assert "Rollback" in dossier
    assert str(tmp_path / "run_report.json") in dossier


def test_action_routing_fixture_cli_writes_artifacts_without_stdout_noise(tmp_path):
    from evolution.core.action_routing_demo import main

    result = CliRunner().invoke(
        main,
        [
            "--out",
            str(tmp_path),
            "--mode",
            "fixture",
            "--no-network",
            "--no-external-writes",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == ""
    assert (tmp_path / "run_report.json").exists()
    assert (tmp_path / "action_queue.json").exists()
    assert (tmp_path / "promotion_dossier.md").exists()
    assert (tmp_path / "artifact_manifest.json").exists()


def test_action_routing_fixture_cli_fails_closed_without_safety_flags(tmp_path):
    from evolution.core.action_routing_demo import main

    missing_network_flag = CliRunner().invoke(
        main,
        ["--out", str(tmp_path), "--mode", "fixture", "--no-external-writes"],
    )
    assert missing_network_flag.exit_code != 0
    assert "--no-network is required" in missing_network_flag.output

    missing_external_flag = CliRunner().invoke(
        main,
        ["--out", str(tmp_path), "--mode", "fixture", "--no-network"],
    )
    assert missing_external_flag.exit_code != 0
    assert "--no-external-writes is required" in missing_external_flag.output
