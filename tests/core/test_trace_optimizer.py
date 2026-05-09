"""Tests for deterministic trace optimizer."""

import json
from pathlib import Path

import pytest

from evolution.core.trace_optimizer import (
    _baseline_output,
    _candidate_output,
    _CANDIDATE_TEMPLATES,
    run_optimizer,
)

# ── Helpers ────────────────────────────────────────────────────────────

def _make_eval_examples(dir_path: Path, failure_classes: list[str]) -> Path:
    data = {
        "examples": [
            {
                "detected_failure_classes": failure_classes,
                "failure_count": len(failure_classes),
                "assistant_messages": 20,
                "detection_summary": ["summary"] * len(failure_classes),
            }
        ]
    }
    path = dir_path / "eval_examples.json"
    path.write_text(json.dumps(data))
    return path


# ── Output shape tests ─────────────────────────────────────────────────

class TestBaselineOutput:
    """Baseline output should fail with zero improvements."""

    def test_verdict_is_fail(self):
        b = _baseline_output()
        assert b["verdict"] == "fail"

    def test_improvements_empty(self):
        b = _baseline_output()
        assert b["improvements"] == []

    def test_safety_all_false(self):
        b = _baseline_output()
        s = b["safety"]
        assert s["network_allowed"] is False
        assert s["external_writes_allowed"] is False
        assert s["github_writes_allowed"] is False

    def test_schema_version(self):
        b = _baseline_output()
        assert b["schema_version"] == 1

    def test_mode_is_optimizer(self):
        b = _baseline_output()
        assert b["mode"] == "optimizer"


class TestCandidateOutput:
    """Candidate output for known failure classes."""

    def test_single_failure_class(self):
        c = _candidate_output(["long_briefing_instead_of_concise_action_queue"])
        assert c["verdict"] == "pass"
        assert len(c["improvements"]) == 1

    def test_all_three_failure_classes(self):
        classes = [
            "long_briefing_instead_of_concise_action_queue",
            "raw_session_trace_without_structured_eval_example",
            "agent_describes_instead_of_calls_tools",
        ]
        c = _candidate_output(classes)
        assert c["verdict"] == "pass"
        assert len(c["improvements"]) == 3

    def test_unknown_failure_class_silently_ignored(self):
        c = _candidate_output(["nonexistent_failure"])
        assert c["verdict"] == "fail"
        assert c["improvements"] == []

    def test_mixed_known_and_unknown(self):
        c = _candidate_output([
            "long_briefing_instead_of_concise_action_queue",
            "unknown_class",
        ])
        assert c["verdict"] == "pass"
        assert len(c["improvements"]) == 1

    def test_each_improvement_has_all_fields(self):
        c = _candidate_output(_CANDIDATE_TEMPLATES.keys())
        for imp in c["improvements"]:
            assert "failure_class" in imp
            assert "improvement_type" in imp
            assert "baseline_description" in imp
            assert "candidate_description" in imp
            assert "candidate_constraint" in imp
            assert len(imp["candidate_constraint"]) > 0

    def test_improvement_types_are_valid(self):
        c = _candidate_output(_CANDIDATE_TEMPLATES.keys())
        valid_types = {"output_constraint", "extraction_rule", "prompt_patch"}
        for imp in c["improvements"]:
            assert imp["improvement_type"] in valid_types

    def test_safety_flags_false(self):
        c = _candidate_output(["long_briefing_instead_of_concise_action_queue"])
        s = c["safety"]
        assert s["network_allowed"] is False
        assert s["external_writes_allowed"] is False
        assert s["github_writes_allowed"] is False

    def test_metrics_reflect_actual_counts(self):
        classes = [
            "long_briefing_instead_of_concise_action_queue",
            "agent_describes_instead_of_calls_tools",
        ]
        c = _candidate_output(classes)
        assert c["metrics"]["failure_classes_seen"] == 2
        assert c["metrics"]["improvements_generated"] == 2


# ── run_optimizer integration tests ────────────────────────────────────

class TestRunOptimizerIntegration:
    """End-to-end run_optimizer with filesystem."""

    def test_no_eval_examples_file(self, tmp_path):
        result = run_optimizer(
            eval_examples_path=tmp_path / "nonexistent.json",
            output_dir=tmp_path / "out",
        )
        assert result["verdict"] == "fail"
        assert result["improvements"] == []

    def test_empty_eval_examples(self, tmp_path):
        ep = tmp_path / "eval.json"
        ep.write_text(json.dumps({"examples": []}))
        result = run_optimizer(
            eval_examples_path=ep,
            output_dir=tmp_path / "out",
        )
        assert result["verdict"] == "fail"

    def test_writes_run_report(self, tmp_path):
        ep = _make_eval_examples(
            tmp_path, ["long_briefing_instead_of_concise_action_queue"]
        )
        out = tmp_path / "out"
        run_optimizer(ep, out)
        assert (out / "run_report.json").is_file()

    def test_writes_candidate_artifacts(self, tmp_path):
        ep = _make_eval_examples(
            tmp_path, ["agent_describes_instead_of_calls_tools"]
        )
        out = tmp_path / "out"
        run_optimizer(ep, out)
        assert (out / "candidate_artifacts.json").is_file()

    def test_writes_baseline_vs_candidate(self, tmp_path):
        ep = _make_eval_examples(
            tmp_path, ["raw_session_trace_without_structured_eval_example"]
        )
        out = tmp_path / "out"
        run_optimizer(ep, out)
        assert (out / "baseline_vs_candidate.json").is_file()

    def test_gate_result_recommends_promote(self, tmp_path):
        ep = _make_eval_examples(
            tmp_path, ["long_briefing_instead_of_concise_action_queue"]
        )
        out = tmp_path / "out"
        run_optimizer(ep, out)
        bc = json.loads((out / "baseline_vs_candidate.json").read_text())
        gate = bc["gate_result"]
        assert gate["baseline_passed"] is False
        assert gate["candidate_passed"] is True
        assert gate["recommendation"] == "promote"

    def test_all_three_artifacts_present(self, tmp_path):
        ep = _make_eval_examples(tmp_path, list(_CANDIDATE_TEMPLATES.keys()))
        out = tmp_path / "out"
        run_optimizer(ep, out)
        assert (out / "run_report.json").is_file()
        assert (out / "candidate_artifacts.json").is_file()
        assert (out / "baseline_vs_candidate.json").is_file()

    def test_output_is_valid_json(self, tmp_path):
        ep = _make_eval_examples(
            tmp_path, ["agent_describes_instead_of_calls_tools"]
        )
        out = tmp_path / "out"
        run_optimizer(ep, out)
        for fname in ["run_report.json", "candidate_artifacts.json",
                       "baseline_vs_candidate.json"]:
            text = (out / fname).read_text()
            json.loads(text)  # should not raise

    def test_safety_never_leaked(self, tmp_path):
        """Safety flags must be False regardless of input."""
        ep = _make_eval_examples(tmp_path, list(_CANDIDATE_TEMPLATES.keys()))
        out = tmp_path / "out"
        run_optimizer(ep, out)
        rr = json.loads((out / "run_report.json").read_text())
        s = rr["safety"]
        assert s["network_allowed"] is False
        assert s["external_writes_allowed"] is False
        assert s["github_writes_allowed"] is False
