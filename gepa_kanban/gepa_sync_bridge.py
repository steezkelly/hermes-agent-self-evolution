#!/usr/bin/env python3
"""
GEPA → Built-in Kanban Sync Bridge

Reads the GEPA Skill Evolution Kanban card-registry.json and upserts
summary tasks into the built-in Hermes Kanban SQLite database.

This gives dashboard visibility into GEPA pipeline state without losing
the rich GEPA-specific tooling (delta scoring, eval source tracking, etc.).

Usage:
    python3 gepa_sync_bridge.py [--dry-run] [--delete-all]

--dry-run      Preview what would change without writing
--delete-all   Remove all GEPA-synced tasks from built-in kanban (reset)
"""

import json
import sqlite3
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

GEPA_REGISTRY = Path.home() / "hermes0" / "hermes-agent-self-evolution" / "gepa_kanban" / "card-registry.json"
KANBAN_DB     = Path.home() / ".hermes" / "kanban.db"
TENANT        = "gepa"
ASSIGNEE      = "gepa-pipeline"
WORKSPACE_PATH = str(Path.home() / "hermes0" / "hermes-agent-self-evolution")
GEPA_TASK_SKILLS = [
    "gepa-pipeline-operations",
    "hermes-self-evolution",
    "gepa-v2-regression-validation",
]
EXECUTION_PRESERVE_STATUSES = {"ready", "running", "done"}
ACTIONABLE_GEPA_STATUSES = {"BACKLOG", "IN_PROGRESS", "REGRESSION", "VALIDATING", "STALE"}

# GEPA column → built-in status mapping
STATUS_MAP = {
    "BACKLOG":     "todo",
    "IN_PROGRESS": "running",
    "REGRESSION":  "blocked",
    "VALIDATING":  "blocked",   # human review needed = blocked
    "DEPLOYED":    "done",
    "STALE":       "blocked",   # waiting for re-run
    "EVOLVED":     "done",      # alternate completion status
    "GEPA_COMPLETED": "done",   # legacy GEPA completion status
}

def map_status(gepa_status: str) -> str:
    return STATUS_MAP.get(gepa_status.upper(), "todo")

GEPA_BODY_TEMPLATE = """## GEPA Skill Evolution Card

- **GEPA status:** {gepa_status}
- **Skill:** {skill_name}
- **Best improvement:** {best_delta:+.4f} (run {best_run})
- **Latest run:** {latest_delta:+.4f} (run {latest_run})
- **Eval source:** {eval_source}
- **Iterations:** {iterations}
- **Constraints passed:** {constraints_passed}
- **Multi-run:** {is_multi_run}
- **Total runs:** {run_count} (regressions: {regression_count})

## Worker instructions

This is a GEPA skill-evolution/review card. Do not perform the named skill's domain work directly.
Work in `{workspace_path}` and use the GEPA registry, output reports, datasets, and evolution scripts.

- VALIDATING: inspect the evolved artifact/report for `{skill_name}`, compare it to the deployed SKILL.md, verify constraints, and recommend/deploy only if clearly safe.
- REGRESSION/STALE: diagnose the failed/stale run, regenerate datasets or rerun the current v2/batch evolution path only when evidence supports it.
- IN_PROGRESS with no live runner: recover it as stale/incomplete instead of leaving the built-in row running forever.

Finish the Kanban task with commands run, files inspected/changed, and the next decision.
"""


def load_gepa_cards(registry_path: Path) -> list[dict]:
    if not registry_path.exists():
        print(f"ERROR: GEPA registry not found at {registry_path}", file=sys.stderr)
        sys.exit(1)
    with open(registry_path) as f:
        return json.load(f)


def ensure_gepa_assignee(conn: sqlite3.Connection):
    """Verify the executable GEPA assignee profile exists before syncing.

    The DB accepts arbitrary assignee strings, but the dispatcher can only
    spawn real Hermes profiles. Failing early prevents silent crash loops and
    rows that look assigned but are not executable.
    """
    try:
        from hermes_cli.profiles import profile_exists
        exists = profile_exists(ASSIGNEE)
    except Exception:
        import subprocess
        proc = subprocess.run(
            ["hermes", "profile", "list"],
            capture_output=True,
            text=True,
            check=False,
        )
        exists = proc.returncode == 0 and ASSIGNEE in (proc.stdout or "")
    if not exists:
        print(
            f"ERROR: required Hermes profile '{ASSIGNEE}' does not exist. "
            f"Create it with: hermes profile create {ASSIGNEE} --clone",
            file=sys.stderr,
        )
        sys.exit(2)


def find_existing_gepa_task(conn: sqlite3.Connection, skill_name: str) -> str | None:
    cur = conn.execute(
        "SELECT id FROM tasks WHERE tenant = ? AND title = ?",
        (TENANT, f"GEPA: {skill_name}")
    )
    row = cur.fetchone()
    return row[0] if row else None


def existing_gepa_task_status(conn: sqlite3.Connection, task_id: str | None) -> str | None:
    if not task_id:
        return None
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return row[0] if row else None


def sync_card(conn: sqlite3.Connection, card: dict, dry_run: bool) -> str:
    skill_name     = card["skill_name"]
    gepa_status    = card.get("status", "BACKLOG")
    builtin_status = map_status(gepa_status)
    best_delta     = card.get("best_delta") or 0.0
    latest_delta   = card.get("latest_delta") or 0.0
    best_run       = card.get("best_run", "?") or "?"
    latest_run     = card.get("latest_run", "?") or "?"
    eval_source    = card.get("eval_source", "?") or "?"
    iterations     = card.get("iterations", 0) or 0
    constraints    = card.get("constraints_passed", True)
    is_multi_run   = card.get("is_multi_run", False)
    run_count      = card.get("run_count", 0) or 0
    regression_cnt = card.get("regression_count", 0) or 0
    priority       = {"high": 3, "medium": 2, "low": 1}.get(card.get("priority", "low"), 1)

    existing_id = find_existing_gepa_task(conn, skill_name)
    existing_status = existing_gepa_task_status(conn, existing_id)
    if (
        existing_id
        and existing_status in EXECUTION_PRESERVE_STATUSES
        and str(gepa_status).upper() in ACTIONABLE_GEPA_STATUSES
    ):
        # Once a GEPA card has been released into the built-in dispatcher,
        # do not let a registry refresh silently shove it back to blocked.
        # The task's worker should complete/block it with an auditable handoff.
        builtin_status = existing_status

    body = GEPA_BODY_TEMPLATE.format(
        gepa_status     = gepa_status,
        skill_name      = skill_name,
        best_delta      = best_delta,
        best_run        = best_run,
        latest_delta    = latest_delta,
        latest_run      = latest_run,
        eval_source     = eval_source,
        iterations      = iterations,
        constraints_passed = constraints,
        is_multi_run    = is_multi_run,
        run_count       = run_count,
        regression_count = regression_cnt,
        workspace_path   = WORKSPACE_PATH,
    )

    metadata = {
        "gepa": True,
        "skill_name": skill_name,
        "best_delta": best_delta,
        "latest_delta": latest_delta,
        "gepa_status": gepa_status,
        "eval_source": eval_source,
        "run_count": run_count,
        "regression_count": regression_cnt,
        "constraints_passed": constraints,
    }

    now = int(datetime.now(timezone.utc).timestamp())

    if existing_id:
        # Update existing task
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                body = ?,
                assignee = ?,
                priority = ?,
                result = ?,
                workspace_kind = ?,
                workspace_path = ?,
                max_runtime_seconds = COALESCE(max_runtime_seconds, 7200),
                skills = ?
            WHERE id = ?
            """,
            (
                builtin_status,
                body,
                ASSIGNEE,
                priority,
                json.dumps(metadata),
                "dir",
                WORKSPACE_PATH,
                json.dumps(GEPA_TASK_SKILLS),
                existing_id,
            )
        )
        conn.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (existing_id, "gepa-sync", f"Sync: {gepa_status} | best={best_delta:+.4f} | latest={latest_delta:+.4f}", now)
        )
        action = "updated"
    else:
        # Create new task
        task_id = f"gepa_{skill_name.replace('-', '_')}"
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, body, assignee, status, priority,
                created_by, created_at, workspace_kind, workspace_path,
                tenant, result, skills, max_runtime_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                f"GEPA: {skill_name}",
                body,
                ASSIGNEE,
                builtin_status,
                priority,
                "gepa-sync",
                now,
                "dir",
                WORKSPACE_PATH,
                TENANT,
                json.dumps(metadata),
                json.dumps(GEPA_TASK_SKILLS),
                7200,
            )
        )
        conn.execute(
            "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
            (task_id, "created", json.dumps({"assignee": ASSIGNEE, "status": builtin_status, "tenant": TENANT, "skills": GEPA_TASK_SKILLS}), now)
        )
        existing_id = task_id
        action = "created"

    if not dry_run:
        conn.commit()

    return f"{action} {skill_name}: {gepa_status} → {builtin_status} (id={existing_id})"


def _delete_task(conn: sqlite3.Connection, tid: str) -> None:
    """Delete a task and all dependent kanban rows."""
    conn.execute("DELETE FROM task_events WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM task_comments WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM task_runs WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM task_links WHERE parent_id = ? OR child_id = ?", (tid, tid))
    conn.execute("DELETE FROM kanban_notify_subs WHERE task_id = ?", (tid,))
    conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))


def delete_all_gepa_tasks(conn: sqlite3.Connection, dry_run: bool) -> int:
    """Remove all tasks with tenant='gepa' from built-in kanban."""
    cur = conn.execute("SELECT id FROM tasks WHERE tenant = ?", (TENANT,))
    ids = [r[0] for r in cur.fetchall()]

    if dry_run:
        print(f"[DRY RUN] Would delete {len(ids)} GEPA tasks")
        return len(ids)

    for tid in ids:
        _delete_task(conn, tid)

    conn.commit()
    print(f"Deleted {len(ids)} GEPA tasks")
    return len(ids)


def delete_stale_gepa_tasks(conn: sqlite3.Connection, live_task_ids: set[str], dry_run: bool) -> int:
    """Remove GEPA tasks that no longer exist in card-registry.json.

    The sync bridge is source-of-truth from card-registry.json. Without this
    cleanup, renamed/removed skills stay in ~/.hermes/kanban.db forever and
    make the health monitor report JSON/DB count mismatches.
    """
    cur = conn.execute("SELECT id FROM tasks WHERE tenant = ?", (TENANT,))
    stale_ids = [r[0] for r in cur.fetchall() if r[0] not in live_task_ids]

    if dry_run:
        print(f"[DRY RUN] Would delete {len(stale_ids)} stale GEPA tasks: {', '.join(stale_ids)}")
        return len(stale_ids)

    for tid in stale_ids:
        _delete_task(conn, tid)
    if stale_ids:
        conn.commit()
        print(f"Deleted {len(stale_ids)} stale GEPA tasks: {', '.join(stale_ids)}")
    return len(stale_ids)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync GEPA kanban to built-in kanban")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--delete-all", action="store_true", help="Remove all GEPA-synced tasks")
    args = parser.parse_args(argv)

    cards = load_gepa_cards(GEPA_REGISTRY)

    with sqlite3.connect(KANBAN_DB) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")

        if args.delete_all:
            delete_all_gepa_tasks(conn, args.dry_run)
            return 0

        ensure_gepa_assignee(conn)

        results = []
        live_task_ids: set[str] = set()
        for card in cards:
            msg = sync_card(conn, card, args.dry_run)
            results.append(msg)
            live_task_ids.add(find_existing_gepa_task(conn, card["skill_name"]) or f"gepa_{card['skill_name'].replace('-', '_')}")

        stale_deleted = delete_stale_gepa_tasks(conn, live_task_ids, args.dry_run)

        for msg in results:
            print(msg)

        print(f"\nSynced {len(cards)} GEPA cards → {KANBAN_DB}")
        if stale_deleted:
            print(f"Removed {stale_deleted} stale GEPA tasks not present in registry")
        if args.dry_run:
            conn.rollback()

    return 0


if __name__ == "__main__":
    sys.exit(main())
