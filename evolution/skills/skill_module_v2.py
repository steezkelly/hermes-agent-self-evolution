"""Multi-component SkillModule — splits skill into sections for GEPA to mutate independently.

This version is designed to make GEPA's *reflective mutation* work.

Why: GEPA's reflective mutation builds a reflective dataset by filtering
DSPy execution traces down to trace instances whose predictor signature
matches the predictor it wants to update.

Therefore, each section predictor must (a) exist as a named predictor
(Predict instance) and (b) emit trace entries during forward().

We achieve (b) by appending trace tuples manually for each section
predictor, using the active dspy.settings.trace list (which GEPA
initializes via `dspy.context(trace=[])`).

After optimization, GEPA mutates each predictor via
`pred.signature = pred.signature.with_instructions(candidate[name])`.
We read the mutated instructions back via evolved_sections().
"""

import re
from typing import Optional

import dspy

_MIN_SECTION_CHARS = 200


def split_into_sections(body: str) -> list[dict]:
    """Split a skill body by ## headings into named sections."""
    lines = body.split("\n")
    sections = []
    current_heading = None
    current_lines = []

    for line in lines:
        heading_match = re.match(r"^(##\s+.+)$", line)
        if heading_match:
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    sections.append({
                        "heading": current_heading or "",
                        "text": text,
                    })
            current_heading = heading_match.group(1).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append({
                "heading": current_heading or "",
                "text": text,
            })

    merged = []
    for sec in sections:
        if merged and len(sec["text"]) < _MIN_SECTION_CHARS:
            merged[-1]["text"] += "\n\n" + sec["text"]
        else:
            merged.append(dict(sec))

    # Assign stable section names
    for i, sec in enumerate(merged):
        ht = sec["heading"].lstrip("#").strip() if sec["heading"] else f"preamble"
        name = re.sub(r"[^a-z0-9]+", "-", ht.lower()).strip("-")
        if not name:
            name = f"section_{i}"
        sec["name"] = name

    return merged


def reconstruct_body(sections: list[dict], evolved_texts: dict[str, str]) -> str:
    """Reconstruct full skill body from evolved section texts."""
    parts = []
    for sec in sections:
        text = evolved_texts.get(sec["name"], sec["text"])
        if text and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def _safe_attr(section_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", section_name)


def _safe_output_field(section_name: str) -> str:
    return f"section_{_safe_attr(section_name)}"


def _pred_name(section_name: str) -> str:
    # Name used as the GEPA candidate key
    return f"pred_{section_name}"


class SectionModule(dspy.Module):
    """A single section where the predictor's instructions ARE the section text."""

    def __init__(self, section_name: str, section_text: str):
        super().__init__()
        self.section_name = section_name

        output_field = _safe_output_field(section_name)

        # The Predict's signature.instructions hold the optimizable text.
        sig = dspy.Signature(
            f"task_input: str -> {output_field}: str",
            instructions=section_text,
        )
        self.predict = dspy.Predict(sig)

    @property
    def signature(self):
        return self.predict.signature

    @signature.setter
    def signature(self, new_sig):
        self.predict.signature = new_sig

    def forward(self, task_input: str) -> dspy.Prediction:
        # No LM call: we just return the current instruction text.
        current_text = self.predict.signature.instructions
        pred = dspy.Prediction(**{_safe_output_field(self.section_name): current_text})

        # Emit a trace entry so GEPA reflective mutation can build
        # reflective datasets.
        try:
            if hasattr(dspy, "settings") and getattr(dspy.settings, "trace", None) is not None:
                # GEPA's dspy adapter expects trace tuples like:
                # (predictor_instance, predictor_inputs_dict, prediction_outputs)
                dspy.settings.trace.append((self.predict, {"task_input": task_input}, pred))
        except Exception:
            pass

        return pred


class MultiComponentSkillModule(dspy.Module):
    """SkillModule decomposed into independently mutatable section predictors."""

    def __init__(self, skill_body: str):
        super().__init__()
        self.sections = split_into_sections(skill_body)

        # Create one SectionModule per section.
        for sec in self.sections:
            attr = _safe_attr(sec["name"])
            setattr(self, f"secmod_{attr}", SectionModule(sec["name"], sec["text"]))

    def _get_section_mod(self, section_name: str) -> SectionModule:
        return getattr(self, f"secmod_{_safe_attr(section_name)}")

    def named_predictors(self):
        """Return Predict instances directly (GEPA will mutate .signature.instructions)."""
        result = []
        for sec in self.sections:
            section_mod = self._get_section_mod(sec["name"])
            result.append((_pred_name(sec["name"]), section_mod.predict))
        return result

    def evolved_sections(self) -> dict[str, str]:
        """Read back mutated instructions from each predictor."""
        evolved: dict[str, str] = {}
        for sec in self.sections:
            section_mod = self._get_section_mod(sec["name"])
            try:
                evolved[sec["name"]] = (section_mod.predict.signature.instructions or sec["text"]).strip()
            except Exception:
                evolved[sec["name"]] = sec["text"]
        return evolved

    def forward(self, task_input: str) -> dspy.Prediction:
        # Call each SectionModule forward so trace entries exist.
        for sec in self.sections:
            section_mod = self._get_section_mod(sec["name"])
            try:
                section_mod(task_input=task_input)
            except Exception:
                # Trace still matters; failure should not crash evolution.
                pass

        evolved_direct = self.evolved_sections()
        body = reconstruct_body(self.sections, evolved_direct)
        return dspy.Prediction(output=body)
