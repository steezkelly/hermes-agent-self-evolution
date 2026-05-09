"""Tests for report generation dependencies."""

import importlib.util
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reportlab_is_declared_for_generate_report_imports():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]

    assert any(dep.lower().startswith("reportlab") for dep in dependencies)


def test_generate_report_module_imports_after_project_install():
    spec = importlib.util.spec_from_file_location(
        "generate_report",
        ROOT / "generate_report.py",
    )
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert callable(module.build_report)
