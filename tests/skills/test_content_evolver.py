"""Tests for ContentEvolver section-level mutation pipeline.

These tests validate:
1. SectionScorer -- pure read+eval, no side effects
2. SectionRewriter -- prompt construction and candidate generation
3. ContentEvolver -- full pipeline orchestration with constraint gate

Uses dry-run style mocking to avoid actual LLM calls.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import dspy
import pytest

from evolution.skills.section_scorer import SectionScorer, SectionScore
from evolution.skills.section_rewriter import SectionRewriter, RewriteCandidate
from evolution.skills.content_evolver import ContentEvolver
from evolution.skills.skill_module_v2 import split_into_sections, reconstruct_body


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def sample_skill_body():
    """A simple skill body with 4 sections for testing."""
    return """## Overview

This skill helps with testing.

## Steps

1. Load the module
2. Run the test

## Examples

Example usage here.

## Troubleshooting

Fix common issues.
"""


@pytest.fixture
def sample_sections(sample_skill_body):
    return split_into_sections(sample_skill_body)


@pytest.fixture
def mock_holdout_examples():
    """Mock DSPy examples for holdout scoring."""
    examples = []
    for i in range(6):
        ex = dspy.Example(
            task_input=f"Task {i+1}",
            expected_behavior=f"Expected output for task {i+1}",
        ).with_inputs("task_input")
        examples.append(ex)
    return examples


# ─────────────────────────────────────────────
# SectionScorer Tests
# ─────────────────────────────────────────────

class TestSectionScorer:
    def test_split_sections(self, sample_sections):
        """Test that split_into_sections produces named sections."""
        assert len(sample_sections) >= 3
        names = [s["name"] for s in sample_sections]
        assert "overview" in names
        assert "steps" in names
        assert "examples" in names

    def test_identify_weak_sections_fraction(self, sample_skill_body, mock_holdout_examples):
        """Test that bottom third is identified."""
        scorer = SectionScorer()
        # Mock the scoring to return deterministic values
        with patch.object(scorer, 'score_sections') as mock_score:
            mock_score.return_value = [
                SectionScore(name="examples", heading="## Examples", score=0.2, example_count=6, failures=[]),
                SectionScore(name="troubleshooting", heading="## Troubleshooting", score=0.3, example_count=6, failures=[]),
                SectionScore(name="steps", heading="## Steps", score=0.7, example_count=6, failures=[]),
                SectionScore(name="overview", heading="## Overview", score=0.8, example_count=6, failures=[]),
            ]
            weak = scorer.identify_weak_sections(
                skill_body=sample_skill_body,
                holdout_examples=mock_holdout_examples,
                fraction=1/3,
                verbose=False,
            )
        assert len(weak) == 1  # 4 sections * 1/3 = 1.33 -> max(1, 1) = 1
        assert weak[0].name == "examples"
        assert weak[0].score == 0.2

    def test_scorer_is_pure_read_eval(self, sample_skill_body, mock_holdout_examples):
        """SectionScorer must not modify the skill body."""
        original = sample_skill_body
        scorer = SectionScorer()
        with patch.object(scorer, 'score_sections') as mock_score:
            mock_score.return_value = [
                SectionScore(name="steps", heading="## Steps", score=0.5, example_count=6, failures=[]),
            ]
            scorer.identify_weak_sections(sample_skill_body, mock_holdout_examples, verbose=False)
        assert sample_skill_body == original

    def test_empty_holdout(self, sample_skill_body):
        """Empty holdout should return all sections with zero scores."""
        scorer = SectionScorer()
        result = scorer.score_sections(sample_skill_body, [], verbose=False)
        assert len(result) == len(split_into_sections(sample_skill_body))
        for r in result:
            assert r.score == 0.0
            assert r.example_count == 0


# ─────────────────────────────────────────────
# SectionRewriter Tests
# ─────────────────────────────────────────────

class TestSectionRewriter:
    def test_build_rewrite_prompt_contains_failure_signal(self):
        """Rewrite prompt must include failure reasons."""
        rewriter = SectionRewriter()
        section = {"name": "steps", "heading": "## Steps", "text": "1. Do thing"}
        failures = [{"reason": "Missing detail about edge case X"}]
        prompt = rewriter._build_rewrite_prompt(
            section=section,
            skill_name="test-skill",
            skill_description="A test skill",
            failures=failures,
            full_skill_body="## Steps\n\n1. Do thing",
        )
        assert "Missing detail about edge case X" in prompt
        assert "test-skill" in prompt
        assert "## Steps" in prompt
        assert "1. Do thing" in prompt

    def test_generate_candidates_returns_k_candidates(self):
        """Should return K candidates (or fallback to original)."""
        rewriter = SectionRewriter(k_candidates=3)
        section = {"name": "steps", "heading": "## Steps", "text": "1. Do thing"}

        # Mock the LM to avoid real API calls
        mock_lm = MagicMock()
        mock_result = MagicMock()
        mock_result.rewritten_section = "## Steps\n\n1. Do thing better"

        with patch.object(rewriter, '_get_lm', return_value=mock_lm):
            with patch('dspy.context'):
                with patch('dspy.Predict') as mock_predict:
                    mock_predict.return_value.return_value = mock_result
                    candidates = rewriter.generate_candidates(
                        section=section,
                        skill_name="test",
                        verbose=False,
                    )

        assert len(candidates) > 0
        assert all(isinstance(c, RewriteCandidate) for c in candidates)
        assert all(c.section_name == "steps" for c in candidates)

    def test_candidate_includes_original_text(self):
        """Each candidate should preserve original_text reference."""
        rewriter = SectionRewriter(k_candidates=1)
        section = {"name": "steps", "heading": "## Steps", "text": "Original text"}

        with patch.object(rewriter, '_get_lm') as mock_lm:
            mock_result = MagicMock()
            mock_result.rewritten_section = "## Steps\n\nRewritten"
            mock_predict = MagicMock()
            mock_predict.return_value = mock_result
            with patch('dspy.context'):
                with patch('dspy.Predict', return_value=mock_predict):
                    candidates = rewriter.generate_candidates(
                        section=section,
                        skill_name="test",
                        verbose=False,
                    )

        assert candidates[0].original_text == "Original text"
        assert "Rewritten" in candidates[0].candidate_text


# ─────────────────────────────────────────────
# ContentEvolver Integration Tests
# ─────────────────────────────────────────────

class TestContentEvolver:
    def test_reconstruction_preserves_unchanged_sections(self, sample_sections):
        """When no sections are rewritten, output should match input."""
        original_body = reconstruct_body(sample_sections, {s["name"]: s["text"] for s in sample_sections})
        assert "## Overview" in original_body
        assert "## Steps" in original_body

    def test_content_evolver_init(self):
        """ContentEvolver should initialize with correct defaults."""
        from evolution.core.config import EvolutionConfig
        config = EvolutionConfig()
        evolver = ContentEvolver(config=config)
        assert evolver.k_candidates == 3
        assert evolver.weak_fraction == 1/3

    def test_build_metrics(self):
        """Metrics dict should contain all expected keys."""
        from evolution.core.config import EvolutionConfig
        config = EvolutionConfig()
        evolver = ContentEvolver(config=config)
        metrics = evolver._build_metrics(
            skill_name="test",
            baseline_score=0.5,
            evolved_score=0.6,
            improvements=[{"section": "steps", "improvement": 0.1}],
            constraints_passed=True,
            elapsed=10.5,
            original_body="body",
            evolved_body="better body",
        )
        assert metrics["skill_name"] == "test"
        assert metrics["baseline_score"] == 0.5
        assert metrics["evolved_score"] == 0.6
        assert metrics["improvement"] == pytest.approx(0.1)
        assert metrics["constraints_passed"] is True
        assert "timestamp" in metrics
        assert "improvements" in metrics
        assert metrics["sections_rewritten"] == 1

    def test_constraint_gate_allows_valid_evolution(self):
        """Constraint gate should pass when skills are identical."""
        from evolution.core.config import EvolutionConfig
        config = EvolutionConfig()
        evolver = ContentEvolver(config=config)
        # Patch legacy validator to always pass (toy skills lack full structure)
        with patch.object(evolver, "_run_constraint_gate", wraps=evolver._run_constraint_gate) as mock_gate:
            # Actually call but then override just the legacy piece
            pass
        skill_text = "---\nname: test\n---\n\n## Steps\n\nDo thing"

        with patch("evolution.skills.content_evolver.ConstraintValidator") as MockValidator:
            instance = MockValidator.return_value
            class FakeResult:
                def __init__(self, n, p):
                    self.constraint_name = n
                    self.passed = p
            instance.validate_all.return_value = [
                FakeResult("size_limit", True),
                FakeResult("growth_limit", True),
                FakeResult("non_empty", True),
                FakeResult("skill_structure", True),
                FakeResult("cli_syntax", True),
            ]
            passed, results = evolver._run_constraint_gate(
                evolved_full=skill_text,
                baseline_full=skill_text,
                baseline_score=0.5,
                evolved_score=0.5,
            )
        assert passed is True
        names = [r["name"] for r in results]
        assert "ConfigDrift" in names
        assert "PurposePreservation" in names
        assert "Regression" in names
        assert "ScopeCreep" in names
        assert "ConstraintValidator" in names

    def test_no_weak_sections_returns_original(self, sample_skill_body, mock_holdout_examples):
        """When all sections score well, original should be returned unchanged."""
        from evolution.core.config import EvolutionConfig
        from evolution.skills.content_evolver import find_skill, load_skill
        config = EvolutionConfig()
        evolver = ContentEvolver(config=config)

        # Mock find_skill + load_skill so disk isn't needed
        with patch("evolution.skills.content_evolver.find_skill") as mock_find:
            mock_find.return_value = Path("/fake/path.md")
            with patch("evolution.skills.content_evolver.load_skill") as mock_load:
                mock_load.return_value = {
                    "name": "test-skill",
                    "description": "A test skill",
                    "frontmatter": {"name": "test-skill"},
                    "body": sample_skill_body,
                    "raw": "---\nname: test-skill\n---\n\n" + sample_skill_body,
                }
                # Mock scorer to return no weak sections
                with patch.object(evolver.scorer, "identify_weak_sections") as mock_weak:
                    mock_weak.return_value = []
                    evolved, metrics = evolver.evolve(
                        skill_name="test-skill",
                        holdout_examples=mock_holdout_examples,
                        verbose=False,
                    )

        assert metrics["sections_rewritten"] == 0
        assert metrics["baseline_score"] == 0.0

    def test_full_pipeline_with_mocked_components(self, sample_skill_body, mock_holdout_examples):
        """Test full pipeline with all LLM calls mocked."""
        from evolution.core.config import EvolutionConfig
        config = EvolutionConfig()
        evolver = ContentEvolver(config=config, k_candidates=2)

        # Create a temp skill file
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"
            skills_dir.mkdir()
            skill_file = skills_dir / "test-skill" / "SKILL.md"
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            skill_file.write_text("---\nname: test-skill\ndescription: A test\n---\n\n" + sample_skill_body)
            config.hermes_agent_path = Path(tmpdir)

            # Mock all external dependencies
            with patch.object(evolver.scorer, 'identify_weak_sections') as mock_weak:
                mock_weak.return_value = [
                    SectionScore(name="examples", heading="## Examples", score=0.2, example_count=6, failures=[]),
                ]

                with patch.object(evolver.rewriter, 'generate_for_sections') as mock_rewrite:
                    candidate = RewriteCandidate(
                        section_name="examples",
                        original_text="Example usage here.",
                        candidate_text="## Examples\n\nBetter examples here.",
                        generator_prompt="prompt",
                        candidate_index=0,
                    )
                    mock_rewrite.return_value = {"examples": [candidate]}

                    with patch.object(evolver, '_score_candidate', return_value=0.7):
                        with patch.object(evolver, '_run_constraint_gate', return_value=(True, [])):
                            evolved, metrics = evolver.evolve(
                                skill_name="test-skill",
                                holdout_examples=mock_holdout_examples,
                                verbose=False,
                            )

            assert metrics["sections_rewritten"] == 1
            assert "examples" in [i["section"] for i in metrics["improvements"]]
            assert metrics["constraints_passed"] is True
