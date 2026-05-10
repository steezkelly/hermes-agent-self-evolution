"""Tests for GEPA trace bridge: optimizer templates → DSPy datasets."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from evolution.core.gepa_trace_bridge import (
    _build_dataset_for_class,
    _build_gepa_manifest,
    _CLASS_TO_EXAMPLES,
    main as gepa_trace_bridge_main,
    run_gepa_bridge,
)


# ── Unit: dataset builder ──────────────────────────────────────────────

class TestBuildDatasetForClass:
    """dataset builder produces valid JSONL splits."""

    def test_known_class_produces_files(self, tmp_path):
        ds_path, count = _build_dataset_for_class(
            "agent_describes_instead_of_calls_tools",
            "Always call tools first.",
            tmp_path,
        )
        assert count == 2
        assert (ds_path / "train.jsonl").is_file()
        assert (ds_path / "val.jsonl").is_file()
        assert (ds_path / "holdout.jsonl").is_file()

    def test_unknown_class_uses_fallback(self, tmp_path):
        ds_path, count = _build_dataset_for_class(
            "nonexistent_failure", "Be concise", tmp_path
        )
        assert count == 1
        assert (ds_path / "train.jsonl").is_file()

    def test_lines_are_valid_json(self, tmp_path):
        ds_path, _ = _build_dataset_for_class(
            "long_briefing_instead_of_concise_action_queue",
            "Constraint here.",
            tmp_path,
        )
        for fname in ["train.jsonl", "val.jsonl"]:
            lines = (ds_path / fname).read_text().strip().split("\n")
            for line in lines:
                if line.strip():
                    data = json.loads(line)
                    assert "task_input" in data
                    assert "expected_behavior" in data

    def test_all_known_classes_covered(self):
        """Every class in optimizer templates must have eval examples."""
        for fc in _CLASS_TO_EXAMPLES:
            examples = _CLASS_TO_EXAMPLES[fc]
            assert len(examples) >= 1, f"{fc} has no eval examples"
            for ex in examples:
                assert "task_input" in ex
                assert "expected_behavior" in ex


# ── Unit: manifest builder ─────────────────────────────────────────────

class TestBuildGepaManifest:
    """manifest produces valid ready-to-run commands."""

    def test_manifest_structure(self, tmp_path):
        datasets = [
            {
                "failure_class": "test_class",
                "improvement_type": "output_constraint",
                "dataset_path": str(tmp_path / "test_class"),
                "example_count": 3,
            }
        ]
        manifest = _build_gepa_manifest(
            datasets, "minimax/minimax-m2.7", "minimax/minimax-m2.7", tmp_path
        )
        assert manifest["schema_version"] == 1
        assert manifest["total_datasets"] == 1
        assert len(manifest["datasets"]) == 1
        assert manifest["datasets"][0]["example_count"] == 3

    def test_command_contains_required_args(self, tmp_path):
        datasets = [
            {
                "failure_class": "fc1",
                "improvement_type": "prompt_patch",
                "dataset_path": "/tmp/fc1",
                "example_count": 2,
            }
        ]
        manifest = _build_gepa_manifest(
            datasets, "model-a", "model-b", tmp_path
        )
        cmd = manifest["datasets"][0]["command"]
        assert "--skill-name 'fc1'" in cmd
        assert "--iterations 5" in cmd
        assert "--dataset-path '/tmp/fc1'" in cmd
        assert "--optimizer-model 'model-a'" in cmd
        assert "--eval-model 'model-b'" in cmd

    def test_writes_manifest_file(self, tmp_path):
        manifest = _build_gepa_manifest(
            [], "a", "b", tmp_path
        )
        assert (tmp_path / "gepa_manifest.json").is_file()
        assert manifest["total_datasets"] == 0


# ── Integration: run_gepa_bridge ───────────────────────────────────────

class TestRunGepaBridge:
    """end-to-end bridge from real optimizer output."""

    def test_no_candidate_artifacts(self, tmp_path):
        result = run_gepa_bridge(
            candidate_artifacts_path=tmp_path / "nonexistent.json",
            output_dir=tmp_path / "out",
        )
        assert result["verdict"] == "fail"
        assert result["datasets_built"] == 0

    def test_real_artifacts_from_drill(self, tmp_path):
        """Test against the real optimize-drill output from earlier."""
        artifacts_path = Path(
            "/tmp/optimize-drill/trace_optimizer/candidate_artifacts.json"
        )
        if not artifacts_path.is_file():
            pytest.skip("optimize-drill artifacts not available")

        out = tmp_path / "gepa_out"
        result = run_gepa_bridge(
            candidate_artifacts_path=artifacts_path,
            output_dir=out,
        )
        assert result["verdict"] == "pass"
        assert result["datasets_built"] == 3

    def test_empty_candidates(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({"candidates": []}))
        result = run_gepa_bridge(
            candidate_artifacts_path=empty,
            output_dir=tmp_path / "out",
        )
        assert result["verdict"] == "fail"

    def test_safety_flags_always_false(self, tmp_path):
        artifacts = tmp_path / "cand.json"
        artifacts.write_text(json.dumps({
            "candidates": [
                {
                    "failure_class": "long_briefing_instead_of_concise_action_queue",
                    "improvement_type": "output_constraint",
                    "candidate_constraint": "Be brief.",
                }
            ]
        }))
        result = run_gepa_bridge(
            candidate_artifacts_path=artifacts,
            output_dir=tmp_path / "out",
        )
        s = result["safety"]
        assert s["network_allowed"] is False
        assert s["external_writes_allowed"] is False
        assert s["github_writes_allowed"] is False

    def test_writes_run_report(self, tmp_path):
        artifacts = tmp_path / "cand.json"
        artifacts.write_text(json.dumps({
            "candidates": [
                {
                    "failure_class": "agent_describes_instead_of_calls_tools",
                    "improvement_type": "prompt_patch",
                    "candidate_constraint": "Use tools.",
                }
            ]
        }))
        out = tmp_path / "out"
        run_gepa_bridge(
            candidate_artifacts_path=artifacts,
            output_dir=out,
        )
        assert (out / "run_report.json").is_file()
        assert (out / "gepa_manifest.json").is_file()

    def test_dataset_files_created(self, tmp_path):
        artifacts = tmp_path / "cand.json"
        artifacts.write_text(json.dumps({
            "candidates": [
                {
                    "failure_class": "long_briefing_instead_of_concise_action_queue",
                    "improvement_type": "output_constraint",
                    "candidate_constraint": "Be brief.",
                }
            ]
        }))
        out = tmp_path / "out"
        run_gepa_bridge(
            candidate_artifacts_path=artifacts,
            output_dir=out,
        )
        ds_dir = out / "long_briefing_instead_of_concise_action_queue"
        assert ds_dir.is_dir()
        for fname in ["train.jsonl", "val.jsonl", "holdout.jsonl"]:
            assert (ds_dir / fname).is_file()

    def test_manifest_contains_gepa_commands(self, tmp_path):
        artifacts = tmp_path / "cand.json"
        artifacts.write_text(json.dumps({
            "candidates": [
                {
                    "failure_class": "agent_describes_instead_of_calls_tools",
                    "improvement_type": "prompt_patch",
                    "candidate_constraint": "Call tools.",
                }
            ]
        }))
        out = tmp_path / "out"
        run_gepa_bridge(
            candidate_artifacts_path=artifacts,
            output_dir=out,
        )
        manifest = json.loads((out / "gepa_manifest.json").read_text())
        assert len(manifest["datasets"]) == 1
        cmd = manifest["datasets"][0]["command"]
        assert "gepa_v2_dispatch" in cmd
        assert "agent_describes_instead_of_calls_tools" in cmd

class TestGepaTraceBridgeCliSafetyFlags:
    """CLI safety flags must be opt-in and fail closed when omitted."""

    def _candidate_artifacts(self, tmp_path):
        artifacts = tmp_path / "cand.json"
        artifacts.write_text(json.dumps({
            "candidates": [
                {
                    "failure_class": "agent_describes_instead_of_calls_tools",
                    "improvement_type": "prompt_patch",
                    "candidate_constraint": "Use tools before describing.",
                }
            ]
        }))
        return artifacts

    def test_no_network_and_no_external_writes_flags_allow_cli_run(self, tmp_path):
        artifacts = self._candidate_artifacts(tmp_path)
        out = tmp_path / "out"

        result = CliRunner().invoke(
            gepa_trace_bridge_main,
            [
                "--candidate-artifacts",
                str(artifacts),
                "--out",
                str(out),
                "--no-network",
                "--no-external-writes",
            ],
        )

        assert result.exit_code == 0, result.output
        report = json.loads((out / "run_report.json").read_text())
        assert report["safety"]["network_allowed"] is False
        assert report["safety"]["external_writes_allowed"] is False

    @pytest.mark.parametrize(
        ("omitted_flag", "expected_message"),
        [
            ("--no-network", "network safety disabled"),
            ("--no-external-writes", "external writes safety disabled"),
        ],
    )
    def test_missing_safety_flag_fails_closed(
        self, tmp_path, omitted_flag, expected_message
    ):
        artifacts = self._candidate_artifacts(tmp_path)
        out = tmp_path / "out"
        args = [
            "--candidate-artifacts",
            str(artifacts),
            "--out",
            str(out),
            "--no-network",
            "--no-external-writes",
        ]
        args.remove(omitted_flag)

        result = CliRunner().invoke(gepa_trace_bridge_main, args)

        assert result.exit_code != 0
        assert expected_message in str(result.exception)
