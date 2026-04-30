"""kanban_query — structured query tool for GEPA and companion kanban boards.

Usage:
    python -m gepa_kanban.kanban_query [options]

Examples:
    # All VALIDATING cards across both boards
    python -m gepa_kanban.kanban_query --board all --status VALIDATING

    # Stale Gepa skills (older than 72h)
    python -m gepa_kanban.kanban_query --board gepa --age-hours 72

    # High-priority REGRESSION cards
    python -m gepa_kanban.kanban_query --board gepa --status REGRESSION --priority high

    # JSON output for scripting
    python -m gepa_kanban.kanban_query --board all --format json

    # Delta range filter
    python -m gepa_kanban.kanban_query --board gepa --delta-min 0.05 --sort best_delta

    # Companion system BLOCKED cards
    python -m gepa_kanban.kanban_query --board companion --status BLOCKED
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Board paths ────────────────────────────────────────────────────────────────

GEPA_BOARD_DIR = Path(__file__).parent
GEPA_REGISTRY = GEPA_BOARD_DIR / "card-registry.json"
COMPANION_BOARD_FILE = Path("/home/steve/hermes0/companion-system/kanban/board-state.md")


# ── Card loading ─────────────────────────────────────────────────────────────

def _parse_age_hours(age_str: str) -> Optional[int]:
    """Parse '72h', '1d', '2w' etc. Returns integer hours."""
    s = age_str.strip().lower()
    if s.endswith("h"):
        return int(s[:-1])
    if s.endswith("d"):
        return int(s[:-1]) * 24
    if s.endswith("w"):
        return int(s[:-1]) * 24 * 7
    try:
        return int(s)
    except ValueError:
        return None


def load_gepa_cards() -> list[dict]:
    """Load all GEPA skill cards from card-registry.json."""
    if not GEPA_REGISTRY.exists():
        return []
    with open(GEPA_REGISTRY) as f:
        raw = json.load(f)
    cards = []
    for card in raw:
        # Stale = card is actually in the STALE column (not just "not recent")
        card["is_stale"] = card.get("status", "").upper() == "STALE"
        card["board"] = "gepa"  # mark source for filtering
        cards.append(card)
    return cards


def load_companion_cards(board_md_path: Path = COMPANION_BOARD_FILE) -> list[dict]:
    """Parse a companion-system board-state.md into flat card dicts.

    Companion cards don't have delta/priority/runs — we synthesize nulls and
    derive priority from the [high|medium|low] tag in the markdown line.
    """
    if not board_md_path.exists():
        return []

    cards = []
    text = board_md_path.read_text()
    current_column = None
    current_time = datetime.now(timezone.utc)

    for line in text.splitlines():
        line = line.rstrip()
        # Column header
        col_match = re.match(r"^## \w+ \(([0-9]+)\)$", line)
        if col_match:
            current_column = line.split("## ")[1].split(" (")[0]
            continue
        # Card line: "- [priority] title (card_id) — owner"
        card_match = re.match(
            r"^- \[(\w+)\] (.+?) \(([0-9a-f]{8})\) — (.+)$",
            line,
        )
        if card_match and current_column:
            priority_str, title, card_id, owner = card_match.groups()
            priority = priority_str.lower()

            # Try to extract age from the line (companion board doesn't track this)
            # Use board file mtime as proxy
            age_seconds = (current_time - datetime.fromtimestamp(
                board_md_path.stat().st_mtime, tz=timezone.utc
            )).total_seconds()
            age_hours = age_seconds / 3600

            cards.append({
                "board": "companion",
                "card_id": card_id,
                "task_id": card_id,  # companion uses card_id as task_id
                "title": title.strip(),
                "owner_id": owner.strip(),
                "owner_role": None,  # not stored in markdown
                "priority": priority,
                "status": current_column.upper(),
                "created_at": None,
                "updated_at": None,
                "age_hours": age_hours,
                # Gepa-specific fields — null for companion cards
                "skill_name": None,
                "run_count": None,
                "regression_count": None,
                "latest_delta": None,
                "best_delta": None,
                "best_run": None,
                "eval_source": None,
                "iterations": None,
                "constraints_passed": None,
                "is_multi_run": None,
                "is_recent": None,
                "is_stale": None,
            })
    return cards


def load_all_cards() -> list[dict]:
    """Load and merge both boards."""
    return load_gepa_cards() + load_companion_cards()


# ── Query engine ─────────────────────────────────────────────────────────────

def apply_filters(cards: list[dict], args: argparse.Namespace) -> list[dict]:
    """Apply all filter arguments to the card list. Returns filtered list."""
    result = list(cards)

    # --board
    if getattr(args, "board", None) and args.board != "all":
        result = [c for c in result if c.get("board") == args.board]

    # --status
    if getattr(args, "status", None):
        statuses = [s.strip().upper() for s in args.status.split(",")]
        result = [c for c in result if c.get("status", "").upper() in statuses]

    # --priority
    if getattr(args, "priority", None):
        priorities = [p.strip().lower() for p in args.priority.split(",")]
        result = [c for c in result if c.get("priority", "").lower() in priorities]

    # --delta-min
    if getattr(args, "delta_min", None) is not None:
        result = [
            c for c in result
            if c.get("best_delta") is not None and c["best_delta"] >= args.delta_min
        ]

    # --delta-max
    if getattr(args, "delta_max", None) is not None:
        result = [
            c for c in result
            if c.get("best_delta") is not None and c["best_delta"] <= args.delta_max
        ]

    # --age-hours (is_stale filter: age > threshold)
    if getattr(args, "age_hours", None) is not None:
        threshold = args.age_hours
        result = [
            c for c in result
            if c.get("age_hours") is not None and c["age_hours"] > threshold
        ]

    # --is-stale (True = only stale, False = only recent)
    if getattr(args, "is_stale", None) is not None:
        result = [c for c in result if c.get("is_stale") == args.is_stale]

    # --eval-source
    if getattr(args, "eval_source", None):
        sources = [s.strip() for s in args.eval_source.split(",")]
        result = [c for c in result if c.get("eval_source") in sources]

    # --multi-run
    if getattr(args, "multi_run", None) is True:
        result = [c for c in result if c.get("is_multi_run") is True]

    # --search (title/skill_name free text)
    if getattr(args, "search", None):
        term = args.search.lower()
        result = [
            c for c in result
            if term in (c.get("skill_name") or "").lower()
            or term in (c.get("title") or "").lower()
            or term in (c.get("owner_id") or "").lower()
        ]

    return result


def apply_sort(cards: list[dict], sort_by: Optional[str]) -> list[dict]:
    """Sort cards by sort_by field. Descending for numeric, ascending for string."""
    if not sort_by:
        return cards

    def sort_key(c: dict):
        val = c.get(sort_by)
        if val is None:
            return (1, "")  # nulls sort last
        if isinstance(val, (int, float)):
            return (0, -val)  # numeric: descending (negate for desc)
        if isinstance(val, str):
            return (0, val.lower())
        return (0, str(val))

    return sorted(cards, key=sort_key)


# ── Output formatters ─────────────────────────────────────────────────────────

def format_markdown(cards: list[dict], board_label: str = "results") -> str:
    """Human-readable markdown table."""
    if not cards:
        return f"_No cards match your query ({board_label})._"

    lines = [f"# Kanban Query — {board_label}", f"_Total: {len(cards)} cards_\n"]

    # Group by status
    by_status: dict[str, list[dict]] = {}
    for c in cards:
        by_status.setdefault(c["status"], []).append(c)

    for status, group in by_status.items():
        lines.append(f"## {status} ({len(group)})")
        for card in group:
            if card.get("board") == "gepa":
                meta = []
                if card.get("best_delta") is not None:
                    meta.append(f"best={card['best_delta']:+.4f}")
                if card.get("run_count") is not None:
                    meta.append(f"runs={card['run_count']}")
                if card.get("eval_source"):
                    meta.append(f"src={card['eval_source']}")
                if card.get("is_multi_run"):
                    meta.append("multi-run")
                if card.get("is_stale"):
                    meta.append("STALE")
                tag = f"[{card['priority'] or '?'}]" if card.get("priority") else ""
                meta_str = " | ".join(meta) if meta else ""
                lines.append(f"- {tag} `{card['skill_name']}` {meta_str}")
            else:
                tag = f"[{card['priority'] or '?'}]" if card.get("priority") else ""
                owner = card.get("owner_id") or ""
                lines.append(f"- {tag} {card.get('title', card.get('skill_name','?'))} — {owner}")
        lines.append("")

    return "\n".join(lines).strip()


def format_json(cards: list[dict]) -> str:
    """Machine-readable JSON."""
    return json.dumps(cards, indent=2, default=str)


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the GEPA and companion kanban boards with filters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--board", default="all",
        choices=["gepa", "companion", "all"],
        help="Which board to query (default: all)",
    )
    parser.add_argument(
        "--status", dest="status",
        help="Filter by status column(s), comma-separated (e.g. VALIDATING,REGRESSION)",
    )
    parser.add_argument(
        "--priority", dest="priority",
        help="Filter by priority (e.g. high,medium,low)",
    )
    parser.add_argument(
        "--delta-min", dest="delta_min", type=float,
        help="Minimum best_delta (GEPA cards only)",
    )
    parser.add_argument(
        "--delta-max", dest="delta_max", type=float,
        help="Maximum best_delta (GEPA cards only)",
    )
    parser.add_argument(
        "--age-hours", dest="age_hours", type=int,
        help="Show only cards older than N hours (is_stale threshold)",
    )
    parser.add_argument(
        "--stale", dest="is_stale", action="store_const", const=True, default=None,
        help="Show only stale cards",
    )
    parser.add_argument(
        "--eval-source", dest="eval_source",
        help="Filter by eval_source (e.g. synthetic,golden,sessiondb)",
    )
    parser.add_argument(
        "--multi-run", dest="multi_run", action="store_true",
        help="Show only skills with multiple runs",
    )
    parser.add_argument(
        "--search",
        help="Free-text search across title/skill_name/owner",
    )
    parser.add_argument(
        "--sort", dest="sort_by",
        choices=["best_delta", "latest_delta", "run_count", "age_hours", "status", "priority", "skill_name"],
        help="Sort field (best_delta sorts descending; string fields sort ascending)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum number of cards to return",
    )
    parser.add_argument(
        "--format", dest="format", default="markdown",
        choices=["markdown", "json", "count"],
        help="Output format (default: markdown)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cards = load_all_cards()
    filtered = apply_filters(cards, args)

    if args.limit:
        filtered = filtered[:args.limit]

    if args.sort_by:
        filtered = apply_sort(filtered, args.sort_by)

    board_label = {
        "gepa": "GEPA board",
        "companion": "Companion board",
        "all": "both boards",
    }[args.board]

    if args.format == "count":
        print(f"{len(filtered)} cards match ({board_label})")
        return 0

    if args.format == "json":
        print(format_json(filtered))
        return 0

    # markdown (default)
    print(format_markdown(filtered, board_label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
