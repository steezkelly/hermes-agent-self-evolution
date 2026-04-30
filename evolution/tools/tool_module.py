"""Tool description evolution — DSPy module and tool description store.

Each Hermes tool has a description (≤500 chars) that the model reads when
deciding which tool to call.  ToolDescriptionModule wraps the current
descriptions as a DSPy Predict module so GEPA can evolve them — the
module's input is a task description, and the label is the correct tool
name.  Evolving the descriptions improves tool-selection accuracy.

The pipeline:
    1. tool_dataset_builder  — build (task, correct_tool) eval pairs
    2. ToolDescriptionModule — DSPy module using tool descriptions as input
    3. evolve_tool_description — GEPA loop that evolves descriptions
    4. Constraint validation  — ≤500 chars per description, no regressions
    5. Git PR with metrics   — before/after accuracy comparison
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import dspy

from evolution.core.config import EvolutionConfig
from evolution.core.nous_auth import _get_lm_kwargs

# ------------------------------------------------------------------
# Tool Description Store
# ------------------------------------------------------------------

# Sentinel value used when a description hasn't been evolved yet
UNCHANGED = "__UNCHANGED__"


@dataclass
class ToolDescriptionStore:
    """Holds current (baseline) and evolved tool descriptions.

    Descriptions are stored as a dict: tool_name -> description string.
    The GEPA optimizer mutates these strings in-place during evolution.
    """

    descriptions: Dict[str, str] = field(default_factory=dict)
    # Maps tool_name -> original baseline description (never mutated)
    _baseline: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # Initialize _baseline from descriptions if not already set
        if not self._baseline and self.descriptions:
            object.__setattr__(self, '_baseline', dict(self.descriptions))

    @classmethod
    def from_hermes_registry(cls, hermes_path: Optional[Path] = None) -> "ToolDescriptionStore":
        """Load current tool descriptions from the Hermes Agent registry."""
        import sys
        if hermes_path:
            sys.path.insert(0, str(hermes_path))

        from tools.registry import discover_builtin_tools, registry

        discover_builtin_tools(Path(hermes_path) / "tools" if hermes_path else None)
        descriptions = {}
        for entry in registry._tools.values():
            desc = entry.description or entry.schema.get("description", "") if entry.schema else ""
            descriptions[entry.name] = desc

        store = cls(descriptions=descriptions)
        store._baseline = dict(descriptions)
        return store

    def reset(self, tool_name: Optional[str] = None) -> None:
        """Reset to baseline descriptions. Pass None to reset all."""
        if tool_name:
            self.descriptions[tool_name] = self._baseline.get(tool_name, "")
        else:
            self.descriptions = dict(self._baseline)

    @property
    def tools(self) -> List[str]:
        return sorted(self.descriptions.keys())

    def __len__(self) -> int:
        return len(self.descriptions)

    def to_json(self) -> str:
        return json.dumps({"descriptions": self.descriptions, "_baseline": self._baseline}, indent=2)

    @classmethod
    def from_json(cls, data: str) -> "ToolDescriptionStore":
        obj = json.loads(data)
        descriptions = obj.get("descriptions", {})
        baseline = obj.get("_baseline", dict(descriptions))
        store = cls(descriptions=descriptions)
        store._baseline = dict(baseline)
        return store


# ------------------------------------------------------------------
# DSPy Module
# ------------------------------------------------------------------

class ToolSelectionSignature(dspy.Signature):
    """Predict the correct Hermes tool for a given task.

    Given a natural-language description of a task, predict which
    Hermes Agent tool should be called.  The tool descriptions are
    provided as context so the model can discriminate between similar
    tools.

    Inputs:
        task_description: Natural-language description of the task to accomplish.
        tool_descriptions: Formatted list of available tools and their descriptions.

    Output:
        predicted_tool: The name of the tool that best accomplishes the task.
    """

    task_description: str = dspy.InputField(
        desc="The task the user wants to accomplish"
    )
    tool_descriptions: str = dspy.InputField(
        desc="Available tools and their descriptions"
    )
    predicted_tool: str = dspy.OutputField(
        desc="The tool name that best accomplishes the task"
    )


def _format_tool_descriptions(tool_store: ToolDescriptionStore) -> str:
    """Format tool descriptions for the DSPy module's context."""
    lines = []
    for name in tool_store.tools:
        desc = tool_store.descriptions.get(name, "")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


class ToolDescriptionModule(dspy.Module):
    """DSPy module that predicts tool selection given task + tool descriptions.

    The module reads all tool descriptions as context and produces a
    predicted_tool name.  During GEPA evolution, only the descriptions
    in tool_store are mutated — this module's forward() method stays fixed.
    """

    def __init__(self, tool_store: ToolDescriptionStore):
        super().__init__()
        self.tool_store = tool_store
        self.predict = dspy.Predict(ToolSelectionSignature)

    def forward(self, task_description: str) -> dspy.Prediction:
        tool_context = _format_tool_descriptions(self.tool_store)
        return self.predict(
            task_description=task_description,
            tool_descriptions=tool_context,
        )

    @property
    def tool_names(self) -> List[str]:
        return self.tool_store.tools
