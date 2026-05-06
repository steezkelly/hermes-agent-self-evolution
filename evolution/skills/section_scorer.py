"""Section Scorer — per-section LLMJudge evaluation using holdout examples.

This is step 1 of ContentEvolver. It scores each section independently
against holdout examples to identify the bottom third for rewriting.

Pure read+eval — no side effects, no mutations.
"""

import re
from typing import Optional
from dataclasses import dataclass

import dspy
from rich.console import Console

from evolution.core.fitness import skill_fitness_metric, LLMJudge
from evolution.skills.skill_module_v2 import split_into_sections as mcs_split, reconstruct_body as mcs_reconstruct

console = Console()


@dataclass
class SectionScore:
    """Score result for a single section."""
    name: str
    heading: str
    score: float
    example_count: int
    failures: list[dict]  # List of {example_id, reason, section_text} for failures


class SectionScorer:
    """Score each section of a skill body against a holdout set.

    For each holdout example, we evaluate the full skill body but parse
    the LLMJudge reasoning to determine which section(s) contributed to
    the failure. The section with the lowest aggregate score is the weakest.

    When per-section attribution isn't available from the judge, we fall back
    to scoring the section in isolation (replace all other sections with stubs).
    """

    def __init__(self, evaluator_model: str = "minimax/minimax-m2.7"):
        self.evaluator_model = evaluator_model
        self._lm: Optional[dspy.LM] = None

    def _get_lm(self) -> dspy.LM:
        if self._lm is None:
            from evolution.core.nous_auth import _get_lm_kwargs
            lm_kwargs, model_used = _get_lm_kwargs(self.evaluator_model)
            lm_kwargs["num_retries"] = 8
            self._lm = dspy.LM(model_used, **lm_kwargs)
        return self._lm

    def _create_stubs_for_other_sections(self, sections: list[dict], target_name: str) -> str:
        """Create a skill body where non-target sections are replaced with minimal stubs."""
        parts = []
        for sec in sections:
            if sec["name"] == target_name:
                parts.append(sec["text"].strip())
            else:
                parts.append(f"{sec['heading']}\n\n[Section content omitted for section-scoring]")
        return "\n\n".join(parts)

    def score_sections(
        self,
        skill_body: str,
        holdout_examples: list,
        verbose: bool = False,
        use_isolation_scoring: bool = True,
    ) -> list[SectionScore]:
        """Score each section of the skill body against holdout examples.

        Args:
            skill_body: Full skill body text (without frontmatter)
            holdout_examples: DSPy examples (from dataset.to_dspy_examples("holdout"))
            verbose: Print progress
            use_isolation_scoring: If True, score each section in isolation (stub other sections)
                                 for more accurate per-section signal.

        Returns:
            List of SectionScore, one per section, sorted by score ascending.
        """
        sections = mcs_split(skill_body)
        section_scores: dict[str, SectionScore] = {}

        for sec in sections:
            section_scores[sec["name"]] = SectionScore(
                name=sec["name"],
                heading=sec.get("heading", sec["name"]),
                score=0.0,
                example_count=0,
                failures=[],
            )

        total_examples = len(holdout_examples)
        if total_examples == 0:
            return list(section_scores.values())

        # Use the LLMJudge for per-example scoring
        # We score either full body or isolated sections
        for idx, ex in enumerate(holdout_examples):
            if verbose:
                console.print(f"  Evaluating example {idx+1}/{total_examples}")

            try:
                if use_isolation_scoring:
                    # Score each section independently by stubbing others
                    for sec in sections:
                        isolated_body = self._create_stubs_for_other_sections(sections, sec["name"])
                        # Create a pseudo-prediction with the isolated body
                        pred = dspy.Prediction(output=isolated_body)
                        score = skill_fitness_metric(ex, pred)

                        section_scores[sec["name"]].score += score
                        section_scores[sec["name"]].example_count += 1

                        if score < 0.5:  # Threshold for "failure"
                            section_scores[sec["name"]].failures.append({
                                "example_id": idx,
                                "reason": f"Score: {score:.3f}",
                                "section_text": sec["text"] if verbose else None,
                            })
                else:
                    # Full-body scoring: single score distributed across sections
                    pred = dspy.Prediction(output=skill_body)
                    score = skill_fitness_metric(ex, pred)
                    # Distribute score equally across sections
                    per_section_score = score / len(sections)
                    for sec in sections:
                        section_scores[sec["name"]].score += per_section_score
                        section_scores[sec["name"]].example_count += 1
            except Exception as e:
                if verbose:
                    console.print(f"    [yellow]Example {idx+1} failed: {e}[/yellow]")
                continue

        # Normalize scores to [0, 1] per section
        results = []
        for sec in sections:
            s = section_scores[sec["name"]]
            if s.example_count > 0:
                s.score = s.score / s.example_count
            results.append(s)

        # Sort by score ascending (weakest first)
        results.sort(key=lambda x: x.score)
        return results

    def identify_weak_sections(
        self,
        skill_body: str,
        holdout_examples: list,
        fraction: float = 1/3,
        verbose: bool = False,
    ) -> list[SectionScore]:
        """Identify the bottom fraction of sections by score.

        Returns:
            Sorted list of weak SectionScore objects.
        """
        all_scores = self.score_sections(skill_body, holdout_examples, verbose=verbose)
        n = max(1, int(len(all_scores) * fraction))
        weak = all_scores[:n]

        if verbose:
            console.print(f"\n[bold]Section Scores ({len(all_scores)} sections):[/bold]")
            for s in all_scores:
                color = "red" if s in weak else "green"
                console.print(f"  [{color}]{s.score:.3f} {s.heading}[/{color}]")
            console.print(f"\nWeakest {len(weak)} sections selected for rewrite.")

        return weak
