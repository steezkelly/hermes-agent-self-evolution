"""diff_baselines — annotate the difference between GEPA baseline and evolved skills.

Usage:
    python3.12 -m gepa_kanban.diff_baselines [options]

Examples:
    # Diff the latest run of a skill
    python3.12 -m gepa_kanban.diff_baselines --skill companion-workflows

    # Diff a specific run
    python3.12 -m gepa_kanban.diff_baselines --skill companion-workflows --run 20260428_014430

    # JSON output for scripting
    python3.12 -m gepa_kanban.diff_baselines --skill companion-workflows --format json

    # Show only changed sections
    python3.12 -m gepa_kanban.diff_baselines --skill companion-safety --sections-only
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────

GEPA_OUTPUT = Path(__file__).parent.parent / "output"


# ── Core diffing ──────────────────────────────────────────────────────────────

def extract_sections(text: str) -> dict[str, list[str]]:
    """Split a skill markdown into sections by header lines.

    Returns dict: section_name -> list of lines in that section.
    Special key "_preamble" for lines before the first header.
    """
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"

    for line in lines:
        # Match markdown headers: # Section, ## Section, etc.
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            header_level = len(header_match.group(1))
            header_name = header_match.group(2).strip()
            # Use "H{n}" prefix to distinguish levels
            current = f"{'#' * header_level} {header_name}"
            if current not in sections:
                sections[current] = []
        else:
            sections.setdefault(current, []).append(line)

    return sections


def section_diff(baseline_text: str, evolved_text: str) -> dict:
    """Compute section-level changes between two skill texts.

    Returns a dict describing added, removed, and modified sections.
    """
    baseline_sections = extract_sections(baseline_text)
    evolved_sections = extract_sections(evolved_text)

    baseline_keys = set(baseline_sections.keys())
    evolved_keys = set(evolved_sections.keys())

    added = sorted(evolved_keys - baseline_keys)
    removed = sorted(baseline_keys - evolved_keys)
    common = sorted(baseline_keys & evolved_keys)

    modified = []
    for key in common:
        if baseline_sections[key] != evolved_sections[key]:
            # Compute line-level diff stats for this section
            bl = len(baseline_sections[key])
            ev = len(evolved_sections[key])
            delta_lines = ev - bl
            modified.append({
                "section": key,
                "baseline_lines": bl,
                "evolved_lines": ev,
                "delta_lines": delta_lines,
            })

    return {
        "added_sections": added,
        "removed_sections": removed,
        "modified_sections": modified,
    }


def compute_diff(baseline_text: str, evolved_text: str) -> dict:
    """Full diff between baseline and evolved skill texts.

    Returns a structured dict with stats, section changes, and line diff.
    """
    baseline_lines = baseline_text.splitlines()
    evolved_lines = evolved_text.splitlines()

    # Overall stats
    baseline_chars = len(baseline_text)
    evolved_chars = len(evolved_text)
    delta_chars = evolved_chars - baseline_chars

    baseline_lines_count = len(baseline_lines)
    evolved_lines_count = len(evolved_lines)
    delta_lines = evolved_lines_count - baseline_lines_count

    # Line-level unified diff
    diff_lines = list(difflib.unified_diff(
        baseline_lines,
        evolved_lines,
        fromfile="baseline_skill.md",
        tofile="evolved_skill.md",
        lineterm="",
    ))

    # Section analysis
    sections = section_diff(baseline_text, evolved_text)

    # Count +lines and -lines from the diff
    added_lines = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
    removed_lines = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

    return {
        "stats": {
            "baseline_chars": baseline_chars,
            "evolved_chars": evolved_chars,
            "delta_chars": delta_chars,
            "baseline_lines": baseline_lines_count,
            "evolved_lines": evolved_lines_count,
            "delta_lines": delta_lines,
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "net_lines": added_lines - removed_lines,
        },
        "sections": sections,
        "diff_lines": diff_lines,
    }


def find_runs(skill_name: str) -> list[str]:
    """List all run IDs for a skill, newest-first.

    Only includes directories that have both baseline_skill.md and evolved_skill.md.
    """
    skill_dir = GEPA_OUTPUT / skill_name
    if not skill_dir.is_dir():
        return []
    runs = []
    for d in skill_dir.iterdir():
        if not d.is_dir():
            continue
        # Must have both baseline and evolved skill
        if not (d / "baseline_skill.md").exists():
            continue
        if not (d / "evolved_skill.md").exists():
            continue
        runs.append(d.name)
    runs.sort(reverse=True)
    return runs


def diff_skill(skill_name: str, run_id: Optional[str] = None) -> dict:
    """Compute diff for a skill's latest run (or a specific run_id)."""
    runs = find_runs(skill_name)
    if not runs:
        raise FileNotFoundError(f"No runs found for skill: {skill_name}")

    if run_id is None:
        run_id = runs[0]
    elif run_id not in runs:
        raise ValueError(f"Run {run_id} not found for {skill_name}. Available: {runs}")

    run_dir = GEPA_OUTPUT / skill_name / run_id
    baseline_file = run_dir / "baseline_skill.md"
    evolved_file = run_dir / "evolved_skill.md"

    if not baseline_file.exists():
        raise FileNotFoundError(f"No baseline_skill.md in {run_dir}")
    if not evolved_file.exists():
        raise FileNotFoundError(f"No evolved_skill.md in {run_dir}")

    baseline_text = baseline_file.read_text()
    evolved_text = evolved_file.read_text()

    # Load metrics for context
    metrics_file = run_dir / "metrics.json"
    metrics = {}
    if metrics_file.exists():
        with open(metrics_file) as f:
            metrics = json.load(f)

    result = compute_diff(baseline_text, evolved_text)
    result["skill_name"] = skill_name
    result["run_id"] = run_id
    result["metrics"] = metrics

    return result


# ── Output formatters ─────────────────────────────────────────────────────────

def format_markdown(result: dict) -> str:
    """Human-readable annotated diff."""
    skill = result["skill_name"]
    run = result["run_id"]
    stats = result["stats"]
    sections = result["sections"]
    metrics = result.get("metrics", {})

    lines = []
    lines.append(f"# Diff — {skill} ({run})")
    lines.append("")

    # Metrics banner
    delta = metrics.get("improvement", 0)
    delta_pct = (delta / max(abs(metrics.get("baseline_score", 1)), 0.001)) * 100
    lines.append(f"**improvement:** {delta:+.4f} ({delta_pct:+.1f}%) | "
                 f"**constraints:** {'✓' if metrics.get('constraints_passed') else '✗'} | "
                 f"**src:** {metrics.get('eval_source', '?')} | "
                 f"**optimizer:** {metrics.get('optimizer_type', '?')}")
    lines.append("")

    # Size summary
    s = stats
    char_delta_pct = (s["delta_chars"] / max(s["baseline_chars"], 1)) * 100
    lines.append(f"## Size  baseline={s['baseline_chars']:,} chars → evolved={s['evolved_chars']:,} chars "
                 f"({s['delta_chars']:+d} / {char_delta_pct:+.1f}%)")
    lines.append("")

    # Section changes
    if sections["added_sections"] or sections["removed_sections"] or sections["modified_sections"]:
        lines.append("## Sections")

        if sections["added_sections"]:
            lines.append(f"  **Added:** {', '.join(sections['added_sections'])}")

        if sections["removed_sections"]:
            lines.append(f"  **Removed:** {', '.join(sections['removed_sections'])}")

        if sections["modified_sections"]:
            for mod in sections["modified_sections"]:
                d = mod["delta_lines"]
                sign = "+" if d > 0 else ""
                lines.append(f"  *{mod['section']}* ({mod['baseline_lines']}→{mod['evolved_lines']}, {sign}{d} lines)")

        lines.append("")

    # Line diff
    diff_lines = result["diff_lines"]
    if diff_lines:
        # Truncate very long diffs
        max_lines = 200
        if len(diff_lines) > max_lines:
            shown = diff_lines[:max_lines]
            hidden = len(diff_lines) - max_lines
            lines.append(f"## Diff (first {max_lines} of {len(diff_lines)} lines — {hidden} hidden)")
            lines.append("```diff")
            lines.extend(shown)
            lines.append(f"... ({hidden} more lines) ...")
            lines.append("```")
        else:
            lines.append("## Diff")
            lines.append("```diff")
            lines.extend(diff_lines)
            lines.append("```")
    else:
        lines.append("## Diff")
        lines.append("_No text changes detected (baseline and evolved are identical at the line level)._")

    return "\n".join(lines)


def format_json(result: dict) -> str:
    """Machine-readable JSON. Excludes full diff_lines to keep it compact."""
    output = {
        "skill_name": result["skill_name"],
        "run_id": result["run_id"],
        "stats": result["stats"],
        "sections": result["sections"],
        "metrics": {k: v for k, v in result.get("metrics", {}).items()
                     if k in ("improvement", "baseline_score", "evolved_score",
                              "constraints_passed", "eval_source", "optimizer_type",
                              "iterations", "elapsed_seconds")},
    }
    return json.dumps(output, indent=2)


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diff GEPA baseline vs evolved skill for a given run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skill", required=True,
        help="Skill name (directory under output/)",
    )
    parser.add_argument(
        "--run",
        help="Specific run ID (YYYYMMDD_HHMMSS). Default: latest run.",
    )
    parser.add_argument(
        "--sections-only", action="store_true",
        help="Show only section-level changes, no line diff",
    )
    parser.add_argument(
        "--format", dest="format", default="markdown",
        choices=["markdown", "json"],
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--list-runs", dest="list_runs", action="store_true",
        help="List all runs for the skill and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    runs = find_runs(args.skill)
    if not runs:
        print(f"Error: No runs found for skill '{args.skill}'", file=sys.stderr)
        return 1

    if args.list_runs:
        print(f"Runs for '{args.skill}' (newest-first):")
        for r in runs:
            metrics_file = GEPA_OUTPUT / args.skill / r / "metrics.json"
            improvement = "?"
            if metrics_file.exists():
                with open(metrics_file) as f:
                    m = json.load(f)
                improvement = f"{m.get('improvement', 0):+.4f}"
            print(f"  {r}  improvement={improvement}")
        return 0

    try:
        result = diff_skill(args.skill, args.run)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.sections_only:
        # Return only section-level changes as text
        sections = result["sections"]
        if not any(sections.values()):
            print(f"No section changes for {args.skill}/{result['run_id']}")
            return 0
        lines = [f"# Sections — {result['skill_name']} ({result['run_id']})", ""]
        if sections["added_sections"]:
            lines.append(f"Added:   {', '.join(sections['added_sections'])}")
        if sections["removed_sections"]:
            lines.append(f"Removed: {', '.join(sections['removed_sections'])}")
        if sections["modified_sections"]:
            for mod in sections["modified_sections"]:
                d = mod["delta_lines"]
                sign = "+" if d > 0 else ""
                lines.append(f"Modified: {mod['section']} ({mod['baseline_lines']}→{mod['evolved_lines']}, {sign}{d}L)")
        print("\n".join(lines))
        return 0

    if args.format == "json":
        print(format_json(result))
    else:
        print(format_markdown(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
