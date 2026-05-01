# General Kanban — Quick Start

A cross-project todo board. Lives alongside the GEPA Skill Evolution Kanban.

**Location:** `~/hermes0/hermes-agent-self-evolution/general_kanban/`

## Commands

```bash
cd ~/hermes0/hermes-agent-self-evolution/general_kanban

# Add a card
python3 kanban.py add "Fix login bug" --desc "Users can't log in with SSO" --project auth --priority critical --due 2026-05-05
python3 kanban.py add "Update docs" --project docs --priority medium

# Move a card (partial ID works — first 8 chars OK if unique)
python3 kanban.py move 4ad54130 IN_PROGRESS
python3 kanban.py move 4ad54130 REVIEW

# Update fields
python3 kanban.py update 4ad54130 --priority critical --due 2026-05-10

# List / filter
python3 kanban.py list
python3 kanban.py list --status IN_PROGRESS
python3 kanban.py list --project auth
python3 kanban.py list --owner steve
python3 kanban.py list --priority critical

# Show full card JSON
python3 kanban.py show 4ad54130

# Archive (soft-delete)
python3 kanban.py archive 4ad54130

# Include archived in list
python3 kanban.py list --archived
```

## Columns

| Column | When to use |
|--------|-------------|
| BACKLOG | Not yet started |
| IN_PROGRESS | Actively being worked |
| BLOCKED | Stalled — waiting on something |
| REVIEW | Done — awaiting verification or approval |
| DONE | Completed |

## Card Fields

All fields optional except `title`.

| Field | Type | Notes |
|-------|------|-------|
| title | string | Required |
| description | string | Free text |
| project | string | Project name tag |
| owner | string | Who's responsible |
| priority | critical/high/medium/low | Default: medium |
| status | column name | Default: BACKLOG |
| tags | string[] | Arbitrary labels |
| due | YYYY-MM-DD | Optional due date |
| created_at | ISO datetime | Auto-set |
| updated_at | ISO datetime | Auto-updated |
| moved_at | ISO datetime | Auto-updated on status change |
| archived | bool | Soft-delete flag |

## Files

- `kanban.py` — source of truth + CLI
- `kanban_db.json` — the card database
- `board-state.md` — rendered markdown (auto-generated)
- `card-schema.json` — JSON schema for cards
- `kanban-schema.md` — this file (schema docs)
