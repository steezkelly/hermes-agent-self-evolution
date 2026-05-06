"""Section Rewriter — generates candidate section rewrites using failure signal.

This is step 2 of ContentEvolver. For each weak section identified by
SectionScorer, generate K candidate rewrites. The rewrite prompt includes:

1. The original section text
2. The task context (what the skill is for)
3. The holdout failure messages (specific reasons this section performed poorly)
4. Constraints: preserve heading, don't change skill type

Only rewrites the section body — never touches frontmatter or other sections.
"""

import dspy
from typing import Optional
from dataclasses import dataclass

from rich.console import Console

from evolution.core.nous_auth import _get_lm_kwargs

console = Console()


@dataclass
class RewriteCandidate:
    """A candidate rewrite for a single section."""
    section_name: str
    original_text: str
    candidate_text: str
    generator_prompt: str  # The prompt used to generate this candidate
    candidate_index: int  # 0..K-1


class SectionRewriter:
    """Generate K candidate rewrites for weak skill sections.

    Uses the failure signal from SectionScorer (specific holdout failures
    and their reasons) to guide the LLM toward improvements that actually
    fix the observed failures.
    """

    def __init__(
        self,
        rewrite_model: str = "minimax/minimax-m2.7",
        k_candidates: int = 3,
    ):
        self.rewrite_model = rewrite_model
        self.k_candidates = k_candidates
        self._lm: Optional[dspy.LM] = None

    def _get_lm(self) -> dspy.LM:
        if self._lm is None:
            lm_kwargs, model_used = _get_lm_kwargs(self.rewrite_model)
            lm_kwargs["num_retries"] = 8
            self._lm = dspy.LM(model_used, **lm_kwargs)
        return self._lm

    def _build_rewrite_prompt(
        self,
        section: dict,
        skill_name: str,
        skill_description: str,
        failures: list[dict],
        full_skill_body: str,
    ) -> str:
        """Build a rewrite prompt with failure signal and constraints."""
        heading = section.get("heading", section["name"])
        original_text = section["text"]

        failure_lines = []
        if failures:
            failure_lines.append(f"## This section failed on {len(failures)} holdout examples:")
            for i, f in enumerate(failures[:5], 1):
                reason = f.get("reason", "Unknown failure")
                failure_lines.append(f"{i}. {reason}")
            if len(failures) > 5:
                failure_lines.append(f"...and {len(failures) - 5} more similar failures.")
        else:
            failure_lines.append("## This section had low scores but no specific failures were isolated.")
            failure_lines.append("Consider improving clarity, completeness, or actionable detail.")

        failure_text = "\n".join(failure_lines)

        prompt = f"""You are an expert technical writer improving a Hermes Agent skill file.

## Task
Rewrite the section below to improve its quality. This skill section is underperforming on real holdout examples.

## Skill Context
- Skill name: {skill_name}
- Skill description: {skill_description}
- Section heading: {heading}

{failure_text}

## Critical Constraints
1. KEEP the exact section heading: {heading}
2. PRESERVE the skill type and purpose — do not change it into a different kind of document
3. FIX the specific failures listed above
4. KEEP all other sections unchanged — only rewrite THIS section
5. MAINTAIN markdown format with ## headings and bullet points where appropriate

## Original Section Text
{heading}

{original_text}

## Instructions for Rewrite
Analyze the failures above and produce an improved version of ONLY this section.
Focus on:
- Fixing the specific failure modes observed
- Adding missing detail or precision
- Clarifying ambiguous instructions
- Ensuring the section is self-contained and actionable

Return ONLY the rewritten section text, starting with the heading line.
"""
        return prompt

    def generate_candidates(
        self,
        section: dict,
        skill_name: str,
        skill_description: str = "",
        failures: Optional[list[dict]] = None,
        full_skill_body: str = "",
        verbose: bool = False,
    ) -> list[RewriteCandidate]:
        """Generate K candidate rewrites for a single section."""
        if failures is None:
            failures = []

        prompt = self._build_rewrite_prompt(
            section=section,
            skill_name=skill_name,
            skill_description=skill_description,
            failures=failures,
            full_skill_body=full_skill_body,
        )

        candidates = []
        lm = self._get_lm()

        for k in range(self.k_candidates):
            if verbose:
                console.print(f"    Generating candidate {k+1}/{self.k_candidates} for section '{section['name']}'")

            try:
                with dspy.context(lm=lm):
                    sig = dspy.Signature(
                        "prompt: str -> rewritten_section: str",
                        instructions="You are a technical writer. Rewrite ONLY the given section to fix the listed failures. Return only the rewritten section text, starting with its heading."
                    )
                    result = dspy.Predict(sig)(prompt=prompt)
                    candidate_text = result.rewritten_section.strip()

                    heading = section.get("heading", section["name"])
                    if not candidate_text.startswith("#"):
                        candidate_text = f"{heading}\n\n{candidate_text}"

                    candidates.append(RewriteCandidate(
                        section_name=section["name"],
                        original_text=section["text"],
                        candidate_text=candidate_text,
                        generator_prompt=prompt,
                        candidate_index=k,
                    ))
            except Exception as e:
                if verbose:
                    console.print(f"    [yellow]Candidate {k+1} generation failed: {e}[/yellow]")
                continue

        if not candidates:
            candidates.append(RewriteCandidate(
                section_name=section["name"],
                original_text=section["text"],
                candidate_text=section["text"],
                generator_prompt=prompt,
                candidate_index=0,
            ))

        return candidates

    def generate_for_sections(
        self,
        weak_sections: list,
        skill_name: str,
        skill_description: str = "",
        section_scores: Optional[list] = None,
        full_skill_body: str = "",
        verbose: bool = False,
    ) -> dict[str, list[RewriteCandidate]]:
        """Generate candidates for multiple weak sections."""
        results = {}

        failure_map = {}
        if section_scores:
            for ss in section_scores:
                failure_map[ss.name] = ss.failures

        for section in weak_sections:
            failures = failure_map.get(section["name"], [])
            if verbose:
                score_str = "N/A"
                if section_scores:
                    for s in section_scores:
                        if s.name == section["name"]:
                            score_str = f"{s.score:.3f}"
                console.print(f"\n[bold]Rewriting section: {section.get('heading', section['name'])}[/bold]")
                console.print(f"  Original score: {score_str}")
                console.print(f"  Failures: {len(failures)}")

            candidates = self.generate_candidates(
                section=section,
                skill_name=skill_name,
                skill_description=skill_description,
                failures=failures,
                full_skill_body=full_skill_body,
                verbose=verbose,
            )
            results[section["name"]] = candidates

        return results
