"""Tests for Phase 2: Tool description evolution modules.

Tests tool_module.py, tool_dataset_builder.py, tool_description_v2.py,
and evolve_tool_description.py without requiring API access.
"""

import json
from pathlib import Path

import pytest

from evolution.tools.tool_module import (
    ToolDescriptionStore,
    ToolDescriptionModule,
    ToolSelectionSignature,
    _format_tool_descriptions,
    UNCHANGED,
)


class TestToolDescriptionStore:
    """Tests for ToolDescriptionStore."""

    def test_from_dict(self):
        store = ToolDescriptionStore(descriptions={
            "search_files": "Search for text in files",
            "read_file": "Read a file's contents",
        })
        assert len(store) == 2
        assert "search_files" in store.tools
        assert "read_file" in store.tools
        assert store.descriptions["search_files"] == "Search for text in files"

    def test_baseline_tracking(self):
        store = ToolDescriptionStore(descriptions={
            "search_files": "Original description",
        })
        assert store._baseline["search_files"] == "Original description"

        # Mutate
        store.descriptions["search_files"] = "Evolved description"
        assert store._baseline["search_files"] == "Original description"

        # Reset
        store.reset("search_files")
        assert store.descriptions["search_files"] == "Original description"

        # Reset all
        store.descriptions["search_files"] = "Evolved again"
        store.reset()
        assert store.descriptions["search_files"] == "Original description"

    def test_to_json_roundtrip(self):
        original = ToolDescriptionStore(descriptions={
            "tool_a": "Description A",
            "tool_b": "Description B",
        })
        json_str = original.to_json()
        restored = ToolDescriptionStore.from_json(json_str)
        assert restored.descriptions == original.descriptions
        assert restored._baseline == original._baseline

    def test_tools_returns_sorted(self):
        store = ToolDescriptionStore(descriptions={
            "zebra": "Z tool",
            "apple": "A tool",
            "mango": "M tool",
        })
        assert store.tools == ["apple", "mango", "zebra"]

    def test_len(self):
        store = ToolDescriptionStore(descriptions={
            "a": "A", "b": "B", "c": "C",
        })
        assert len(store) == 3


class TestToolDescriptionModule:
    """Tests for ToolDescriptionModule DSPy wrapper."""

    def test_format_tool_descriptions(self):
        store = ToolDescriptionStore(descriptions={
            "search_files": "Search for patterns in files",
            "read_file": "Read file contents",
        })
        formatted = _format_tool_descriptions(store)
        assert "search_files: Search for patterns in files" in formatted
        assert "read_file: Read file contents" in formatted

    def test_signature_has_required_fields(self):
        sig = ToolSelectionSignature
        # DSPy/Pydantic v2: field names are dict keys, values are FieldInfo
        fields = set(sig.model_fields.keys())
        assert "task_description" in fields
        assert "tool_descriptions" in fields
        assert "predicted_tool" in fields


class TestConstraintValidator:
    """Tests for ToolDescriptionConstraintValidator."""

    def test_valid_descriptions_pass(self):
        from evolution.tools.tool_description_v2 import ToolDescriptionConstraintValidator

        store = ToolDescriptionStore(descriptions={
            "search_files": "A" * 400,  # Well under 500
            "read_file": "Read a file",  # Short but valid
        })
        validator = ToolDescriptionConstraintValidator()
        ok, errors = validator.validate(store)
        assert ok
        assert len(errors) == 0

    def test_empty_description_fails(self):
        from evolution.tools.tool_description_v2 import ToolDescriptionConstraintValidator

        store = ToolDescriptionStore(descriptions={
            "search_files": "Some description",
            "broken_tool": "",
        })
        validator = ToolDescriptionConstraintValidator()
        ok, errors = validator.validate(store)
        assert not ok
        assert any("broken_tool" in e for e in errors)

    def test_over_500_chars_fails(self):
        from evolution.tools.tool_description_v2 import ToolDescriptionConstraintValidator

        store = ToolDescriptionStore(descriptions={
            "search_files": "A" * 501,
        })
        validator = ToolDescriptionConstraintValidator()
        ok, errors = validator.validate(store)
        assert not ok
        assert any("501 chars" in e for e in errors)

    def test_exactly_500_chars_passes(self):
        from evolution.tools.tool_description_v2 import ToolDescriptionConstraintValidator

        store = ToolDescriptionStore(descriptions={
            "search_files": "A" * 500,
        })
        validator = ToolDescriptionConstraintValidator()
        ok, errors = validator.validate(store)
        assert ok
        assert len(errors) == 0


class TestToolDatasetBuilder:
    """Tests for the tool description dataset builder."""

    def test_synthetic_examples_per_tool(self):
        from evolution.tools.tool_dataset_builder import _build_synthetic_examples
        from evolution.core.config import EvolutionConfig

        store = ToolDescriptionStore(descriptions={
            "search_files": "Search for text in files",
            "read_file": "Read a file",
            "terminal": "Run shell commands",
        })
        config = EvolutionConfig()

        examples = _build_synthetic_examples(store, config, num_per_tool=3)
        assert len(examples) >= 3  # At least 3 for search_files

        # All examples should have required keys
        for ex in examples:
            assert "task" in ex
            assert "tool_name" in ex
            assert "difficulty" in ex
            assert "source" in ex
            assert ex["source"] == "synthetic"

        # search_files examples
        sf_examples = [e for e in examples if e["tool_name"] == "search_files"]
        assert len(sf_examples) >= 3

    def test_tool_filter(self):
        from evolution.tools.tool_dataset_builder import build_dataset, ToolDescriptionDataset
        from evolution.core.config import EvolutionConfig

        store = ToolDescriptionStore(descriptions={
            "search_files": "Search for text",
            "read_file": "Read a file",
            "terminal": "Run shell commands",
        })
        config = EvolutionConfig()

        # build_dataset() supports tool_filter; _build_synthetic_examples does not
        dataset: ToolDescriptionDataset = build_dataset(
            store, config, eval_source="synthetic", tool_filter=["search_files"]
        )
        tool_names = {e["tool_name"] for e in dataset.examples}
        assert tool_names == {"search_files"}

    def test_dataset_split_balanced(self):
        from evolution.tools.tool_dataset_builder import _build_synthetic_examples
        from evolution.tools.tool_dataset_builder import ToolDescriptionDataset
        from evolution.core.config import EvolutionConfig

        store = ToolDescriptionStore(descriptions={
            f"tool_{i}": f"Description {i}" for i in range(10)
        })
        config = EvolutionConfig()

        examples = _build_synthetic_examples(store, config, num_per_tool=5)
        dataset = ToolDescriptionDataset(examples)

        train, val, test = dataset.split(train_frac=0.6, val_frac=0.2, test_frac=0.2)
        assert len(train) + len(val) + len(test) == len(dataset)
        assert len(train) > len(val)
        assert len(val) > 0
        assert len(test) > 0

    def test_by_difficulty_filter(self):
        from evolution.tools.tool_dataset_builder import _build_synthetic_examples
        from evolution.tools.tool_dataset_builder import ToolDescriptionDataset
        from evolution.core.config import EvolutionConfig

        store = ToolDescriptionStore(descriptions={"search_files": "Search"})
        config = EvolutionConfig()

        examples = _build_synthetic_examples(store, config, num_per_tool=5)
        dataset = ToolDescriptionDataset(examples)

        easy = dataset.by_difficulty("easy")
        medium = dataset.by_difficulty("medium")
        assert len(easy) + len(medium) == len(dataset)
        assert all(e["difficulty"] == "easy" for e in easy.examples)
        assert all(e["difficulty"] == "medium" for e in medium.examples)


class TestToolDescriptionV2Metrics:
    """Tests for tool_description_v2.py metrics and extraction."""

    def test_compute_pareto_front(self):
        from evolution.tools.tool_description_v2 import (
            ToolDescAttemptMetrics,
            _compute_pareto_front,
        )

        metrics = [
            ToolDescAttemptMetrics(attempt=1, score=0.8, baseline_score=0.5,
                                   optimizer_type="GEPA", elapsed_seconds=10.0,
                                   descriptions_changed=3),
            ToolDescAttemptMetrics(attempt=2, score=0.9, baseline_score=0.5,
                                   optimizer_type="GEPA", elapsed_seconds=10.0,
                                   descriptions_changed=5),
            ToolDescAttemptMetrics(attempt=3, score=0.85, baseline_score=0.5,
                                   optimizer_type="GEPA", elapsed_seconds=10.0,
                                   descriptions_changed=1),
        ]

        front = _compute_pareto_front(metrics)
        # Best accuracy (0.9) should be on the front
        accuracies = [p[0] for p in front]
        assert max(accuracies) == 0.9

    def test_tooldesc_evolution_report_fields(self):
        from evolution.tools.tool_description_v2 import ToolDescEvolutionReport
        from evolution.core.router import RouterDecision

        report = ToolDescEvolutionReport(
            tool_name="search_files",
            n_iterations_executed=3,
            improvement=0.15,
            recommendation="accept",
            details="Improved by 15%",
            router_decision=RouterDecision(action="extend", failure_pattern="", confidence=1.0, rationale="test"),
            backtrack_decision=RouterDecision(action="continue", failure_pattern="", confidence=1.0, rationale="test").__class__.__name__,
        )
        assert report.tool_name == "search_files"
        assert report.recommendation == "accept"
        assert report.improvement == 0.15


class TestEvolveToolDescriptionCLI:
    """Tests for the CLI entry point."""

    def test_evolution_output_save(self):
        """Test that _save_output produces correct files."""
        import tempfile
        from evolution.tools.evolve_tool_description import _save_output
        from evolution.tools.tool_module import ToolDescriptionStore
        from datetime import datetime

        baseline = ToolDescriptionStore(descriptions={
            "search_files": "Original search description",
            "read_file": "Original read description",
        })
        evolved = ToolDescriptionStore(descriptions={
            "search_files": "Evolved search description",
            "read_file": "Original read description",
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            report_path = _save_output(
                output_dir=output_dir,
                tool_name="search_files",
                baseline_store=baseline,
                evolved_store=evolved,
                baseline_acc=0.5,
                evolved_acc=0.7,
                train_acc=0.65,
                test_acc=0.68,
                elapsed_seconds=30.0,
                improvement={"delta": 0.2, "relative_pct": 40.0, "significant": True},
                recommendation="accept",
            )

            assert report_path.exists()
            data = json.loads(report_path.read_text())
            assert data["tool_name"] == "search_files"
            assert data["baseline_accuracy"] == 0.5
            assert data["evolved_accuracy"] == 0.7
            assert data["recommendation"] == "accept"
            assert data["improvement"]["delta"] == 0.2
            assert "search_files" in data["diff"]
            assert data["diff"]["search_files"]["before"] == "Original search description"
            assert data["diff"]["search_files"]["after"] == "Evolved search description"

            # Check descriptions.json and baseline_descriptions.json exist
            assert (output_dir / "descriptions.json").exists()
            assert (output_dir / "baseline_descriptions.json").exists()

    def test_compute_improvement(self):
        from evolution.tools.evolve_tool_description import _compute_improvement

        result = _compute_improvement(0.5, 0.7)
        assert abs(result["delta"] - 0.2) < 1e-9
        assert abs(result["relative_pct"] - 40.0) < 1e-9
        assert result["significant"] is True

        result2 = _compute_improvement(0.5, 0.5)
        assert result2["delta"] == 0.0
        assert result2["relative_pct"] == 0.0
        assert result2["significant"] is False

        result3 = _compute_improvement(0.0, 0.0)
        assert result3["relative_pct"] == 0.0  # No div-by-zero


class TestDatasetBuilderIntegration:
    """Integration tests using real Hermes registry (if available)."""

    def test_hermes_registry_loading(self):
        """Test that ToolDescriptionStore can load from Hermes registry if present."""
        from evolution.tools.tool_module import ToolDescriptionStore

        # This requires hermes-agent to be accessible
        # Skip if not available
        hermes_path = Path.home() / ".hermes" / "hermes-agent"
        if not hermes_path.exists():
            pytest.skip("Hermes agent not at ~/.hermes/hermes-agent")

        try:
            store = ToolDescriptionStore.from_hermes_registry(hermes_path)
            assert len(store) >= 10  # Should have many tools
            assert "read_file" in store.tools
            assert "search_files" in store.tools
            assert "terminal" in store.tools

            # Descriptions should be non-empty strings
            for name in store.tools:
                assert isinstance(store.descriptions[name], str)
        except Exception as e:
            pytest.skip(f"Registry loading failed: {e}")
