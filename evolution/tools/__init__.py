# evolution.tools — Phase 2: Tool description evolution
#
# Entry points:
#   python -m evolution.tools.evolve_tool_description --tool search_files --iterations 10
#
# Modules:
#   tool_module.py          — ToolDescriptionStore + ToolDescriptionModule (DSPy)
#   tool_dataset_builder.py  — (task, tool) eval dataset generation
#   tool_description_v2.py   — GEPA v2 pipeline for tool descriptions
#   evolve_tool_description.py — CLI + main evolve() function

from evolution.tools.tool_module import ToolDescriptionStore, ToolDescriptionModule
from evolution.tools.tool_dataset_builder import build_dataset, ToolDescriptionDataset
from evolution.tools.evolve_tool_description import evolve
from evolution.tools.tool_description_v2 import run_tool_description_v2

__all__ = [
    "ToolDescriptionStore",
    "ToolDescriptionModule",
    "build_dataset",
    "ToolDescriptionDataset",
    "evolve",
    "run_tool_description_v2",
]
