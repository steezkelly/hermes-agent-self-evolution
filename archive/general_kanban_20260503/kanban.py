"""
General Kanban — board state management for cross-project todos.

Columns (in display order):
  BACKLOG     — not yet started
  IN_PROGRESS — actively being worked
  BLOCKED     — stalled, waiting on something
  REVIEW      — done, awaiting verification/approval
  DONE        — completed

Storage: cards are stored in the JSON DB file (default: kanban_db.json alongside this file).
CRUD is additive-only via this module; state transitions go through move() so audit trail
is consistent.

Card schema:
  id          — UUID, immutable once assigned
  title       — short name (required)
  description — free text (optional)
  project     — project name tag (optional, free text)
  owner       — who owns this card (optional)
  priority    — critical / high / medium / low
  status      — current column (BACKLOG | IN_PROGRESS | BLOCKED | REVIEW | DONE)
  tags        — list of strings
  due         — ISO date string YYYY-MM-DD (optional)
  created_at  — ISO datetime
  updated_at  — ISO datetime
  moved_at    — ISO datetime of last status change
  archived    — bool, soft-delete
"""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

DB_FILE    = Path(__file__).parent / "kanban_db.json"
BOARD_FILE = Path(__file__).parent / "board-state.md"

COLUMNS = ["BACKLOG", "IN_PROGRESS", "BLOCKED", "REVIEW", "DONE"]

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

COLUMN_DESC = {
    "BACKLOG":     "Not yet started",
    "IN_PROGRESS": "Actively being worked",
    "BLOCKED":     "Stalled — waiting on something",
    "REVIEW":      "Done — awaiting verification or approval",
    "DONE":        "Completed",
}


# ── DB helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_db() -> dict:
    if not DB_FILE.exists():
        return {"cards": []}
    with open(DB_FILE) as f:
        return json.load(f)


def _save_db(db: dict) -> None:
    DB_FILE.write_text(json.dumps(db, indent=2))


# ── CRUD ─────────────────────────────────────────────────────────────────────

def add_card(
    title: str,
    description: str = "",
    project: str = "",
    owner: str = "",
    priority: str = "medium",
    status: str = "BACKLOG",
    tags: list = None,
    due: str = "",
) -> dict:
    """Create and insert a new card. Returns the card dict."""
    tags = tags or []
    db = _load_db()
    now = _now()
    card = {
        "id":          str(uuid.uuid4()),
        "title":       title,
        "description": description,
        "project":     project,
        "owner":       owner,
        "priority":    priority,
        "status":      status,
        "tags":        tags,
        "due":         due,
        "created_at":  now,
        "updated_at":  now,
        "moved_at":    now,
        "archived":    False,
    }
    db["cards"].insert(0, card)  # newest first
    _save_db(db)
    return card


def move_card(card_id: str, new_status: str) -> Optional[dict]:
    """Transition a card to a new column. Returns the updated card or None."""
    if new_status not in COLUMNS:
        raise ValueError(f"Invalid status '{new_status}'. Must be one of {COLUMNS}")

    db = _load_db()
    for card in db["cards"]:
        if card["id"] == card_id and not card.get("archived", False):
            card["status"]    = new_status
            card["moved_at"]  = _now()
            card["updated_at"] = _now()
            _save_db(db)
            return card
    return None


def update_card(card_id: str, **fields) -> Optional[dict]:
    """Update fields on a card. Returns updated card or None."""
    db = _load_db()
    for card in db["cards"]:
        if card["id"] == card_id and not card.get("archived", False):
            for k, v in fields.items():
                if k in ("title", "description", "project", "owner", "priority", "tags", "due"):
                    card[k] = v
            card["updated_at"] = _now()
            _save_db(db)
            return card
    return None


def archive_card(card_id: str) -> bool:
    """Soft-delete a card. Returns True if found and archived."""
    db = _load_db()
    for card in db["cards"]:
        if card["id"] == card_id:
            card["archived"]  = True
            card["updated_at"] = _now()
            _save_db(db)
            return True
    return False


def get_card(card_id: str) -> Optional[dict]:
    """Return a single card by ID, or None."""
    db = _load_db()
    for card in db["cards"]:
        if card["id"] == card_id and not card.get("archived", False):
            return card
    return None


# ── Board rendering ───────────────────────────────────────────────────────────

def render_board(
    filter_status: str = None,
    filter_project: str = None,
    filter_owner: str = None,
    filter_priority: str = None,
    show_archived: bool = False,
) -> str:
    """
    Render the kanban board as markdown.
    Optionally filter by status, project, owner, or priority.
    """
    db = _load_db()
    cards = [
        c for c in db["cards"]
        if (show_archived or not c.get("archived", False))
        and (filter_status   is None or c["status"] == filter_status)
        and (filter_project  is None or c.get("project", "") == filter_project)
        and (filter_owner is None or c.get("owner", "") == filter_owner)
        and (filter_priority is None or c.get("priority", "") == filter_priority)
    ]

    lines = [
        "# General Kanban",
        f"Generated: {_now()}",
        f"Cards: {len(cards)}",
        "",
    ]

    # Summary bar
    col_counts = {c: 0 for c in COLUMNS}
    for card in cards:
        col_counts[card["status"]] = col_counts.get(card["status"], 0) + 1
    summary = " | ".join(f"**{c}** {col_counts.get(c, 0)}" for c in COLUMNS)
    lines.append(f"## Summary  {summary}")
    lines.append("")

    for col in COLUMNS:
        col_cards = [c for c in cards if c["status"] == col]
        if not col_cards:
            continue
        # Sort: priority then due date
        col_cards.sort(
            key=lambda c: (
                PRIORITY_ORDER.get(c.get("priority", "medium"), 2),
                c.get("due", "9999-99-99"),
            )
        )
        lines.append(f"## {col} — {COLUMN_DESC[col]} ({len(col_cards)})")
        lines.append("")
        for card in col_cards:
            lines.append(_render_card_row(card))
        lines.append("")

    return "\n".join(lines)


def _render_card_row(card: dict) -> str:
    parts = [f"**{card['title']}**"]
    if card.get("project"):
        parts.append(f"`{card['project']}`")
    if card.get("owner"):
        parts.append(f"👤 {card['owner']}")
    if card.get("priority") and card["priority"] not in ("medium", "low"):
        emoji = {"critical": "🔴", "high": "🟠", "low": "⚪"}.get(card["priority"], "")
        if emoji:
            parts.append(f"{emoji}")
    if card.get("due"):
        parts.append(f"📅 {card['due']}")
    tags = card.get("tags", [])
    if tags:
        parts.append(" ".join(f"`{t}`" for t in tags))
    parts.append(f"`{card['id'][:8]}`")
    return "- " + " | ".join(parts)


def save_board() -> None:
    """Render current board state to board-state.md."""
    md = render_board()
    BOARD_FILE.write_text(md)
    print(f"Board saved → {BOARD_FILE}")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="General Kanban CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # add
    p = sub.add_parser("add", help="Add a new card")
    p.add_argument("title", help="Card title")
    p.add_argument("--desc", "-d", default="", help="Description")
    p.add_argument("--project", "-p", default="", help="Project name")
    p.add_argument("--owner", "-o", default="", help="Owner")
    p.add_argument("--priority", default="medium", choices=["critical","high","medium","low"])
    p.add_argument("--status", "-s", default="BACKLOG", choices=COLUMNS)
    p.add_argument("--tags", "-t", default="", help="Comma-separated tags")
    p.add_argument("--due", default="", help="Due date YYYY-MM-DD")

    # move
    p = sub.add_parser("move", help="Move a card to a different column")
    p.add_argument("card_id", help="Card ID (full or first 8 chars)")
    p.add_argument("status", choices=COLUMNS, help="New column")

    # update
    p = sub.add_parser("update", help="Update card fields")
    p.add_argument("card_id", help="Card ID")
    p.add_argument("--title", help="New title")
    p.add_argument("--desc", "-d", help="New description")
    p.add_argument("--project", "-p", help="New project")
    p.add_argument("--owner", "-o", help="New owner")
    p.add_argument("--priority", choices=["critical","high","medium","low"])
    p.add_argument("--tags", "-t", help="Comma-separated tags")
    p.add_argument("--due", help="New due date YYYY-MM-DD")

    # archive
    p = sub.add_parser("archive", help="Archive (soft-delete) a card")
    p.add_argument("card_id", help="Card ID")

    # list
    p = sub.add_parser("list", help="List cards (alias: render the board)")
    p.add_argument("--status", "-s", choices=COLUMNS, help="Filter by column")
    p.add_argument("--project", "-p", help="Filter by project")
    p.add_argument("--owner", "-o", help="Filter by owner")
    p.add_argument("--priority", choices=["critical","high","medium","low"])
    p.add_argument("--archived", action="store_true", help="Include archived cards")

    # show
    p = sub.add_parser("show", help="Show a single card's details")
    p.add_argument("card_id", help="Card ID (full or first 8 chars)")

    args = parser.parse_args()

    if args.cmd == "add":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        card = add_card(
            title=args.title,
            description=args.desc,
            project=args.project,
            owner=args.owner,
            priority=args.priority,
            status=args.status,
            tags=tags,
            due=args.due,
        )
        print(f"Added [{card['id'][:8]}] {card['title']} → {card['status']}")
        save_board()

    elif args.cmd == "move":
        # Resolve partial ID
        card_id = args.card_id
        if len(card_id) < 32:
            db = _load_db()
            matches = [c for c in db["cards"] if c["id"].startswith(card_id) and not c.get("archived")]
            if len(matches) == 1:
                card_id = matches[0]["id"]
            elif len(matches) == 0:
                print(f"No card found starting with '{card_id}'")
                exit(1)
            else:
                print(f"Ambiguous ID '{card_id}' — matches: {', '.join(c['id'][:8] for c in matches)}")
                exit(1)
        card = move_card(card_id, args.status)
        if card:
            print(f"Moved [{card['id'][:8]}] {card['title']} → {card['status']}")
            save_board()
        else:
            print(f"Card not found: {card_id}")

    elif args.cmd == "update":
        db = _load_db()
        card_id = args.card_id
        if len(card_id) < 32:
            matches = [c for c in db["cards"] if c["id"].startswith(card_id) and not c.get("archived")]
            if len(matches) == 1:
                card_id = matches[0]["id"]
            elif len(matches) == 0:
                print(f"No card found starting with '{card_id}'")
                exit(1)
        fields = {k: v for k, v in {
            "title": getattr(args, "title", None),
            "description": args.desc,
            "project": args.project,
            "owner": args.owner,
            "priority": args.priority,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None,
            "due": args.due,
        }.items() if v is not None and v != ""}
        card = update_card(card_id, **fields)
        if card:
            print(f"Updated [{card['id'][:8]}] {card['title']}")
            save_board()
        else:
            print(f"Card not found: {card_id}")

    elif args.cmd == "archive":
        if archive_card(args.card_id):
            print(f"Archived {args.card_id[:8]}")
            save_board()
        else:
            print(f"Card not found: {args.card_id}")

    elif args.cmd == "list":
        md = render_board(
            filter_status=args.status,
            filter_project=args.project,
            filter_owner=args.owner,
            filter_priority=args.priority,
            show_archived=args.archived,
        )
        print(md)

    elif args.cmd == "show":
        db = _load_db()
        card_id = args.card_id
        if len(card_id) < 32:
            matches = [c for c in db["cards"] if c["id"].startswith(card_id) and not c.get("archived")]
            if len(matches) == 1:
                card_id = matches[0]["id"]
        card = get_card(card_id)
        if card:
            print(json.dumps(card, indent=2))
        else:
            print(f"Card not found: {args.card_id}")
