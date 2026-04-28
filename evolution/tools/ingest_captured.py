"""Ingest captured skill candidates from ~/.hermes/captured/.

Reads candidates saved by the captured-skill Hermes Agent plugin,
validates them, checks for overlap with existing skills, and optionally
runs the v2 evolution pipeline before deploying.

Usage:
    python -m evolution.tools.ingest_captured list
    python -m evolution.tools.ingest_captured validate <candidate>
    python -m evolution.tools.ingest_captured deploy <candidate>
    python -m evolution.tools.ingest_captured auto        # validate + deploy all
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# --- Paths ---
CAPTURED_DIR = Path(os.environ.get(
    "HERMES_HOME", str(Path.home() / ".hermes")
)) / "captured"

SKILLS_DIRS = [
    Path.home() / ".hermes" / "skills",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def list_candidates(status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all captured candidates."""
    if not CAPTURED_DIR.exists():
        return []
    candidates = []
    for f in sorted(CAPTURED_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if status_filter and data.get("status") != status_filter:
            continue
        candidates.append({
            "file": str(f),
            "session_id": data.get("session_id", ""),
            "task": data.get("task", "")[:100],
            "captured_at": data.get("captured_at", ""),
            "status": data.get("status", "unknown"),
            "domain_tags": data.get("domain_tags", []),
            "overlaps": len(data.get("overlapping_skills", [])),
            "tool_calls": data.get("total_tool_calls", 0),
        })
    return candidates


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_candidate(candidate_path: Path) -> tuple[bool, str, Dict[str, Any]]:
    """Validate a candidate. Returns (valid, reason, details)."""
    try:
        data = json.loads(candidate_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Cannot read: {e}", {}

    checks = {}

    # Check 1: Must have skill_body
    body = data.get("skill_body", "")
    if len(body) < 50:
        checks["body_length"] = f"Too short: {len(body)} chars (min 50)"
    else:
        checks["body_length"] = "OK"

    # Check 2: Must have frontmatter-compatible structure
    has_frontmatter = body.strip().startswith("---")
    has_name = "name:" in body[:300] if has_frontmatter else False
    has_heading = bool(re.search(r"^#{1,3}\s", body, re.MULTILINE))
    checks["structure"] = "OK" if (has_frontmatter or has_heading) else "No frontmatter or headings"

    # Check 3: Must have task
    task = data.get("task", "")
    if len(task) < 10:
        checks["task"] = f"Task too short: {task}"
    else:
        checks["task"] = "OK"

    # Check 4: Overlap with existing skills
    overlaps = _check_overlaps(body)
    if overlaps:
        top = overlaps[0]
        if top["jaccard_similarity"] > 0.5:
            checks["overlap"] = f"HIGH overlap with '{top['skill_name']}' (J={top['jaccard_similarity']:.2f})"
        else:
            checks["overlap"] = "OK"
    else:
        checks["overlap"] = "OK"

    # Overall validity
    failed = [k for k, v in checks.items() if v != "OK"]
    if failed:
        return False, f"Failed checks: {', '.join(failed)}", checks
    return True, "All checks passed", checks


def _check_overlaps(body: str) -> List[Dict[str, Any]]:
    """Check overlap with existing skills."""
    overlaps = []
    body_lower = body.lower()
    body_words = set(body_lower.split())

    for skills_dir in SKILLS_DIRS:
        if not skills_dir.exists():
            continue
        for skill_dir in skills_dir.iterdir():
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skill_text = skill_md.read_text()
                skill_lower = skill_text.lower()
                skill_words = set(skill_lower.split())

                intersection = body_words & skill_words
                jaccard = len(intersection) / max(1, len(body_words | skill_words))

                if jaccard > 0.25:
                    overlaps.append({
                        "skill_name": skill_dir.name,
                        "jaccard_similarity": round(jaccard, 3),
                        "matched_terms": len(intersection),
                    })
            except Exception:
                continue

    return sorted(overlaps, key=lambda x: x["jaccard_similarity"], reverse=True)[:5]


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------

def deploy_candidate(candidate_path: Path) -> tuple[bool, str]:
    """Deploy a validated candidate as a real skill.

    Creates a SKILL.md in ~/.hermes/skills/<name>/ and marks the
    candidate as 'deployed' in the captured store.
    """
    try:
        data = json.loads(candidate_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return False, f"Cannot read candidate: {e}"

    body = data.get("skill_body", "")
    task = data.get("task", "untitled-task")
    tags = data.get("domain_tags", [])

    # Generate a skill name from the task
    name = _generate_skill_name(task, body)

    # Check if skill already exists
    target_dir = Path.home() / ".hermes" / "skills" / name
    if target_dir.exists():
        return False, f"Skill '{name}' already exists at {target_dir}"

    # Build SKILL.md with proper frontmatter
    skill_md = (
        f"---\n"
        f"name: {name}\n"
        f"description: {task[:120]}\n"
        f"version: 1.0.0\n"
        f"metadata:\n"
        f"  captured_at: {data.get('captured_at', _now())}\n"
        f"  session_id: {data.get('session_id', '')}\n"
        f"  hermes:\n"
        f"    tags: [{', '.join(tags)}]\n"
        f"---\n"
        f"\n"
        f"{body}\n"
    )

    # Write skill
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "SKILL.md").write_text(skill_md)

    # Mark as deployed
    data["status"] = "deployed"
    data["deployed_at"] = _now()
    data["deployed_to"] = str(target_dir / "SKILL.md")
    candidate_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return True, f"Deployed to {target_dir / 'SKILL.md'}"


def _generate_skill_name(task: str, body: str) -> str:
    """Generate a kebab-case skill name from the task and body."""
    # Try to extract a skill name from the body's first heading
    heading_match = re.search(r"^#\s+(.+)", body, re.MULTILINE)
    if heading_match:
        name = heading_match.group(1).strip().lower()
    else:
        name = task.lower()

    # Clean to kebab-case
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"-+", "-", name)
    name = name[:48].strip("-")
    if not name:
        name = "captured-skill"
    return name


# ---------------------------------------------------------------------------
# Evolve integration
# ---------------------------------------------------------------------------

def evolve_and_deploy(candidate_path: Path, iterations: int = 5) -> tuple[bool, str]:
    """Validate, run v2 evolution pipeline, then deploy if improvement.

    Returns (success, message).
    """
    # Step 1: Validate
    valid, reason, checks = validate_candidate(candidate_path)
    if not valid:
        return False, f"Validation failed: {reason}"

    # Step 2: Read candidate
    data = json.loads(candidate_path.read_text())
    body = data.get("skill_body", "")
    task = data.get("task", "")[:80]

    # Step 3: Create temporary skill file for evolution
    name = _generate_skill_name(task, body)
    temp_skill_dir = Path("/tmp") / "captured-evolution" / name
    temp_skill_dir.mkdir(parents=True, exist_ok=True)
    temp_skill_path = temp_skill_dir / "SKILL.md"

    tags = data.get("domain_tags", [])
    tags_str = ", ".join(tags) if tags else "captured"
    temp_skill = (
        f"---\n"
        f"name: {name}\n"
        f"description: {task[:120]}\n"
        f"metadata:\n"
        f"  hermes:\n"
        f"    tags: [{tags_str}]\n"
        f"---\n"
        f"\n"
        f"{body}\n"
    )
    temp_skill_path.write_text(temp_skill)

    # Step 4: Run v2 evolution
    console.print(Panel(f"[bold cyan]🧪 Evolving captured candidate: {name}[/bold cyan]"))
    console.print(f"  Path: {candidate_path}")
    console.print(f"  Iterations: {iterations}")

    try:
        from evolution.core.gepa_v2_dispatch import v2_dispatch
        from evolution.core.config import get_hermes_agent_path

        # Copy the temp skill to the evolution pipeline's home skills dir
        home_skills = Path.home() / ".hermes" / "skills"
        candidate_skill_dir = home_skills / name
        if not candidate_skill_dir.exists():
            candidate_skill_dir.mkdir(parents=True, exist_ok=True)
            (candidate_skill_dir / "SKILL.md").write_text(temp_skill)

        report = v2_dispatch(
            skill_name=name,
            iterations=iterations,
            eval_source="synthetic",
            run_tests=False,
        )

        # Step 5: Check result
        if report.recommendation == "deploy":
            data["status"] = "evolved_deployed"
            data["improvement"] = report.improvement
            data["evolved_at"] = _now()
            candidate_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return True, (
                f"Evolved + deployed: improvement {report.improvement:+.3f}, "
                f"router: {report.router_decision.action}"
            )
        elif report.recommendation == "review":
            data["status"] = "evolved_pending_review"
            data["improvement"] = report.improvement
            candidate_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return True, (
                f"Evolved (needs review): improvement {report.improvement:+.3f}, "
                f"router: {report.router_decision.action}"
            )
        else:
            data["status"] = "evolved_rejected"
            data["improvement"] = report.improvement
            candidate_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            return False, (
                f"Evolution rejected: improvement {report.improvement:+.3f} "
                f"(below noise floor)"
            )

    except Exception as e:
        return False, f"Evolution failed: {e}"

    finally:
        # Clean up temp skill if candidate_skill_dir was newly created
        if candidate_skill_dir.exists() and candidate_skill_dir.parent == home_skills:
            import shutil
            shutil.rmtree(candidate_skill_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cli(args: List[str]) -> int:
    """Run the ingest CLI. Returns exit code."""
    if not args:
        args = ["--help"]

    if args[0] in ("--help", "-h", "help"):
        console.print("""[bold]ingest-captured — Self-Evolution Capture Pipeline[/bold]

Usage:
    python -m evolution.tools.ingest_captured list [status]     List candidates
    python -m evolution.tools.ingest_captured validate <file>   Validate a candidate
    python -m evolution.tools.ingest_captured deploy <file>     Deploy a validated candidate
    python -m evolution.tools.ingest_captured auto              Validate + deploy all pending
    python -m evolution.tools.ingest_captured evolve <file>     Evolve then deploy
    python -m evolution.tools.ingest_captured stats             Capture statistics
""")
        return 0

    cmd = args[0]

    if cmd == "list":
        status = args[1] if len(args) > 1 else None
        candidates = list_candidates(status)
        if not candidates:
            console.print("No captured candidates.")
            return 0

        table = Table(title=f"Captured Candidates ({len(candidates)})")
        table.add_column("Status", style="bold")
        table.add_column("Task", style="cyan")
        table.add_column("Tags", style="green")
        table.add_column("Tools", justify="right")
        table.add_column("Overlaps", justify="right")
        table.add_column("Captured", style="dim")

        for c in candidates:
            table.add_row(
                c["status"],
                c["task"][:50],
                ", ".join(c["domain_tags"][:2]),
                str(c["tool_calls"]),
                str(c["overlaps"]),
                c["captured_at"][:16],
            )
        console.print(table)
        return 0

    if cmd == "validate":
        target = Path(args[1])
        if not target.exists():
            # Try matching by session_id or filename
            candidates = list_candidates()
            matches = [c for c in candidates if args[1] in c["file"] or args[1] in c["session_id"]]
            if not matches:
                console.print(f"[red]Candidate not found: {args[1]}[/red]")
                return 1
            target = Path(matches[0]["file"])

        valid, reason, checks = validate_candidate(target)
        if valid:
            console.print(f"[green]✓ Valid: {reason}[/green]")
        else:
            console.print(f"[red]✗ {reason}[/red]")

        for check, result in checks.items():
            color = "green" if result == "OK" else "yellow" if "Minor" in result else "red"
            console.print(f"  [{color}]{check}: {result}[/{color}]")
        return 0 if valid else 1

    if cmd == "deploy":
        target = Path(args[1])
        if not target.exists():
            candidates = list_candidates(status_filter="pending")
            matches = [c for c in candidates if args[1] in c["file"] or args[1] in c["session_id"]]
            if not matches:
                console.print(f"[red]Pending candidate not found: {args[1]}[/red]")
                return 1
            target = Path(matches[0]["file"])

        success, msg = deploy_candidate(target)
        if success:
            console.print(f"[green]✓ {msg}[/green]")
        else:
            console.print(f"[red]✗ {msg}[/red]")
        return 0 if success else 1

    if cmd == "auto":
        candidates = list_candidates(status_filter="pending")
        if not candidates:
            console.print("No pending candidates to process.")
            return 0

        console.print(f"[bold]Processing {len(candidates)} pending candidates...[/bold]")
        validated = 0
        deployed = 0
        failed = 0

        for c in candidates:
            path = Path(c["file"])
            console.print(f"\n[cyan]Candidate: {c['task'][:60]}[/cyan]")

            # Validate
            valid, reason, checks = validate_candidate(path)
            if not valid:
                console.print(f"  [red]✗ Validation: {reason}[/red]")
                failed += 1
                continue
            console.print(f"  [green]✓ Valid[/green]")

            # Deploy
            success, msg = deploy_candidate(path)
            if success:
                console.print(f"  [green]✓ {msg}[/green]")
                deployed += 1
            else:
                console.print(f"  [red]✗ {msg}[/red]")
                failed += 1
            validated += 1

        console.print(f"\n[bold]Summary:[/bold] {validated} validated, {deployed} deployed, {failed} failed")
        return 0 if failed == 0 else 1

    if cmd == "evolve":
        target = Path(args[1])
        if not target.exists():
            candidates = list_candidates()
            matches = [c for c in candidates if args[1] in c["file"] or args[1] in c["session_id"]]
            if not matches:
                console.print(f"[red]Candidate not found: {args[1]}[/red]")
                return 1
            target = Path(matches[0]["file"])

        iterations = int(args[2]) if len(args) > 2 else 5
        success, msg = evolve_and_deploy(target, iterations)
        if success:
            console.print(f"[green]✓ {msg}[/green]")
        else:
            console.print(f"[red]✗ {msg}[/red]")
        return 0 if success else 1

    if cmd == "stats":
        all_c = list_candidates()
        pending = list_candidates(status_filter="pending")
        validated = list_candidates(status_filter="validated")
        deployed = list_candidates(status_filter="deployed")
        rejected = list_candidates(status_filter="rejected")
        console.print(f"[bold]Capture Statistics[/bold]")
        console.print(f"  Total candidates:  {len(all_c)}")
        console.print(f"  Pending:           {len(pending)}")
        console.print(f"  Validated:         {len(validated)}")
        console.print(f"  Deployed:          {len(deployed)}")
        console.print(f"  Rejected:          {len(rejected)}")
        if all_c:
            total_ops = sum(c["tool_calls"] for c in all_c)
            console.print(f"  Total tool calls:  {total_ops}")
        return 0

    console.print(f"[red]Unknown command: {cmd}[/red]")
    return 1


if __name__ == "__main__":
    sys.exit(run_cli(sys.argv[1:]))
