# Phase 5 Implementation Plan

**Date:** 2026-05-03
**Status:** Planning complete — ready for execution
**Est. Duration:** 3.5 days (P0 MVP)

## Design Decisions (Locked)

- **D1 — Capture Trigger:** 3+ tool calls per session
- **D2 — Rubric Generation:** Rule-based (first post-frontmatter section)
- **D3 — Failure Mode:** Silent failure with error logging

---

## P0 Implementations

### P0.1: Extend EvalExample + EvalDataset (`evolution/core/dataset_builder.py`)

**What:** Add missing fields and methods to support captured data.

**Changes to `EvalExample`:**
```python
@dataclass
class EvalExample:
    task_input: str
    expected_behavior: str
    difficulty: str = "medium"
    category: str = "general"
    source: str = "synthetic"
    # NEW FIELDS
    tool_sequence: list[str] = field(default_factory=list)
    complexity_score: int = 0
    session_id: str = ""
    success_pattern: str = ""

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EvalExample":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

**Changes to `EvalDataset`:**
```python
@dataclass
class EvalDataset:
    train: list[EvalExample] = field(default_factory=list)
    val: list[EvalExample] = field(default_factory=list)
    holdout: list[EvalExample] = field(default_factory=list)

    def merge(self, other: "EvalDataset") -> dict:
        """Merge another dataset into self, deduping by task_input."""
        seen = {ex.task_input for ex in self.all_examples}
        added_train = added_val = added_holdout = 0
        for ex in other.train:
            if ex.task_input not in seen:
                self.train.append(ex); seen.add(ex.task_input); added_train += 1
        for ex in other.val:
            if ex.task_input not in seen:
                self.val.append(ex); seen.add(ex.task_input); added_val += 1
        for ex in other.holdout:
            if ex.task_input not in seen:
                self.holdout.append(ex); seen.add(ex.task_input); added_holdout += 1
        return {"train": added_train, "val": added_val, "holdout": added_holdout}

    def save_atomic(self, path: Path):
        """Atomic save: write to temp file, then rename."""
        import tempfile
        path.mkdir(parents=True, exist_ok=True)
        for split_name, split_data in [("train", self.train), ("val", self.val), ("holdout", self.holdout)]:
            target = path / f"{split_name}.jsonl"
            tmp = path / f".{split_name}.jsonl.tmp"
            with open(tmp, "w") as f:
                for ex in split_data:
                    f.write(json.dumps(ex.to_dict()) + "\n")
            os.rename(tmp, target)
```

**Tests:** `tests/core/test_dataset_builder.py` — test merge, atomic save, backward compatibility.

**Estimated effort:** 2 hours

---

### P0.2: Add CapturedExampleEnricher + assign_split() (`evolution/tools/ingest_captured.py`)

**What:** Extract behavioral rubrics from capture data and assign to a single split.

```python
class CapturedExampleEnricher:
    """Convert captured skill data into a rich EvalExample."""

    @staticmethod
    def extract_rubric(task: str, body: str, tool_sequence: list[str], success_pattern: str) -> str:
        """Rule-based rubric extraction (D2: no LLM call)."""
        # Extract first section after frontmatter
        rubric = ""
        sections = re.split(r'\n(?=##?\s)', body.split('---', 2)[-1] if '---' in body else body)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.split('\n')
            heading = lines[0].lstrip('#').strip()
            if heading.startswith('name:') or heading.startswith('description:'):
                continue  # skip frontmatter-like lines
            rubric = '\n'.join(lines[1:]).strip()[:800]
            break

        if not rubric:
            rubric = body[:500]

        parts = [f"Task: {task}", f"Expected tools: {', '.join(tool_sequence)}", f"Success pattern: {success_pattern}"]
        if rubric:
            parts.append(f"Procedure: {rubric}")
        return "\n\n".join(parts)

    @classmethod
    def enrich(cls, data: dict) -> EvalExample:
        task = data.get("task", "")
        body = data.get("skill_body", "")
        tool_sequence = data.get("tool_sequence", [])
        success_pattern = data.get("success_pattern", "")
        total_tools = data.get("total_tool_calls", 0)
        tags = data.get("domain_tags", [])

        difficulty = "easy" if total_tools <= 2 else "medium" if total_tools <= 5 else "hard"

        return EvalExample(
            task_input=task,
            expected_behavior=cls.extract_rubric(task, body, tool_sequence, success_pattern),
            difficulty=difficulty,
            category=tags[0] if tags else "captured",
            source="captured",
            tool_sequence=tool_sequence,
            complexity_score=total_tools,
            session_id=data.get("session_id", ""),
            success_pattern=success_pattern,
        )


def assign_split(task_input: str) -> str:
    """Assign an example to exactly one split deterministically (D1)."""
    import hashlib
    h = int(hashlib.md5(task_input.encode()).hexdigest(), 16)
    return ["train", "val", "holdout"][h % 3]
```

**Estimated effort:** 2 hours

---

### P0.3: Rewrite `save_as_sessiondb_example()` → `enrich_and_merge()`

**Replace the current function with:**

```python
def enrich_and_merge(candidate_path: Path, output_dir: Path) -> dict:
    """Convert a captured candidate to rich EvalExample and merge into dataset."""
    from evolution.core.dataset_builder import EvalDataset, EvalExample

    # 1. Load candidate
    data = json.loads(candidate_path.read_text())

    # 2. Enrich
    enriched = CapturedExampleEnricher.enrich(data)

    # 3. Assign to exactly one split
    split = assign_split(enriched.task_input)

    # 4. Load existing dataset (or create new)
    dataset = EvalDataset.load(output_dir) if output_dir.exists() else EvalDataset()

    # 5. Deduplicate: skip if same task_input already exists in target split
    target_list = getattr(dataset, split)
    if any(ex.task_input == enriched.task_input for ex in target_list):
        return {"status": "skipped", "reason": "duplicate task_input", "split": split}

    # 6. Append
    target_list.append(enriched)

    # 7. Atomic save
    dataset.save_atomic(output_dir)

    return {"status": "merged", "split": split, "task_input": enriched.task_input[:80]}
```

**Update `deploy_candidate()` to call `enrich_and_merge()` instead of `save_as_sessiondb_example()`.**

**Estimated effort:** 1 hour

---

### P0.4: Build Capture Plugin (`~/.hermes/hermes-agent/plugins/captured/`)

**Files to create:**

#### `plugin.yaml`
```yaml
name: captured
version: 1.0.0
description: "Capture deployable skill candidates from sessions with 3+ tool calls. Writes to ~/.hermes/captured/ for the self-evolution ingest pipeline."
hooks:
  - on_session_end
slash_commands:
  - /captured
```

#### `__init__.py`
```python
"""captured-skill plugin — auto-capture deployable skill candidates from sessions.

Wires two behaviours:
1. ``on_session_end`` hook — sessions with 3+ tool calls get analyzed for
   task description, tool sequence, domain tags, and candidate skill body.
2. ``/captured`` slash command — list pending, show stats, validate candidates.
"

from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CAPTURED_DIR = Path.home() / ".hermes" / "captured"
CAPTURED_DIR.mkdir(parents=True, exist_ok=True)
ERROR_LOG = Path.home() / ".hermes" / "capture_errors"
ERROR_LOG.mkdir(parents=True, exist_ok=True)


def _log_error(e: Exception, context: str) -> None:
    """Silent error logging (D3)."""
    from datetime import datetime, timezone
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "error": str(e),
    }
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = ERROR_LOG / f"{date_str}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
    logger.debug("capture error: %s — %s", context, e)


def _extract_tool_sequence(messages: list[dict]) -> list[str]:
    """Extract ordered list of unique tool names from session messages."""
    tools = []
    seen = set()
    for msg in messages:
        tcs = msg.get("tool_calls", [])
        for tc in tcs:
            fn = tc.get("function", {}).get("name", "")
            if fn and fn not in seen:
                tools.append(fn)
                seen.add(fn)
    return tools


def _extract_task(messages: list[dict]) -> str:
    """Extract the first user message as the task."""
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if content and len(content) > 10:
                return content[:500]
    return ""


def _generate_domain_tags(tool_sequence: list[str]) -> list[str]:
    """Heuristic domain tags from tool names."""
    tag_map = {
        "github": "github",
        "browser": "web",
        "web_search": "research",
        "search_files": "codebase",
        "terminal": "devops",
        "execute_code": "data-science",
        "read_file": "codebase",
        "write_file": "codebase",
        "memory": "memory",
        "send_message": "communication",
    }
    tags = set()
    for tool in tool_sequence:
        for prefix, tag in tag_map.items():
            if prefix in tool.lower():
                tags.add(tag)
                break
    return sorted(tags)


def _extract_skill_body(messages: list[dict]) -> str:
    """Heuristic: use the assistant's longest content as candidate body."""
    best = ""
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if len(content) > len(best):
                best = content
    return best[:2000]


def _is_capturable(messages: list[dict]) -> bool:
    """Check if session has 3+ tool calls (D1)."""
    count = 0
    for msg in messages:
        count += len(msg.get("tool_calls", []))
    return count >= 3


def _check_overlap(body: str) -> list[dict]:
    """Check overlap with existing skills via Jaccard."""
    overlaps = []
    body_words = set(body.lower().split())
    skills_dir = Path.home() / ".hermes" / "skills"
    if not skills_dir.exists():
        return overlaps
    for skill_dir in skills_dir.iterdir():
        md = skill_dir / "SKILL.md"
        if not md.exists():
            continue
        try:
            text = md.read_text().lower()
            skill_words = set(text.split())
            inter = body_words & skill_words
            jaccard = len(inter) / max(1, len(body_words | skill_words))
            if jaccard > 0.25:
                overlaps.append({
                    "skill_name": skill_dir.name,
                    "jaccard_similarity": round(jaccard, 3),
                })
        except Exception:
            continue
    return sorted(overlaps, key=lambda x: x["jaccard_similarity"], reverse=True)[:5]


def _save_candidate(session_id: str, messages: list[dict]) -> None:
    """Save a candidate if capturable."""
    tool_sequence = _extract_tool_sequence(messages)
    if len(tool_sequence) < 3:
        return  # D1: 3+ tool calls minimum

    task = _extract_task(messages)
    body = _extract_skill_body(messages)
    if len(body) < 50:
        return

    tags = _generate_domain_tags(tool_sequence)
    overlaps = _check_overlap(body)

    # Simple success pattern heuristic: describe what was accomplished
    success = "Completed with " + str(len(tool_sequence)) + " tools"
    # Check for explicit success markers in last assistant message
    last_assistant = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = msg.get("content", "")
            break
    if "success" in last_assistant.lower() or "✓" in last_assistant:
        success = "Successfully completed task"

    candidate = {
        "session_id": session_id,
        "task": task,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "domain_tags": tags,
        "total_tool_calls": sum(len(m.get("tool_calls", [])) for m in messages),
        "skill_body": body,
        "tool_sequence": tool_sequence,
        "success_pattern": success,
        "overlapping_skills": overlaps,
    }

    # Generate name
    name = re.sub(r"[^a-z0-9\s-]", "", task.lower())[:40].strip()
    name = re.sub(r"\s+", "-", name) or f"session-{session_id[:8]}"
    name = name.rstrip("-")

    candidate_path = CAPTURED_DIR / f"{name}.json"
    candidate_path.write_text(json.dumps(candidate, indent=2, ensure_ascii=False))
    logger.info("Captured candidate: %s (%d tools)", name, len(tool_sequence))


def _on_session_end(
    session_id: str = "",
    completed: bool = True,
    interrupted: bool = False,
    **_: Any,
) -> None:
    """Capture candidate from session if criteria met."""
    if interrupted or not completed or not session_id:
        return

    try:
        # Load session messages from ~/.hermes/sessions/<session_id>.jsonl
        session_path = None
        # Session files are named: YYYYMMDD_HHMMSS_random.jsonl
        # or: request_dump_YYYYMMDD_HHMMSS...json
        # Try to find the file containing this session_id
        sessions_dir = Path.home() / ".hermes" / "sessions"
        for f in sessions_dir.iterdir():
            if session_id in f.name:
                session_path = f
                break

        if not session_path:
            _log_error(FileNotFoundError(f"Session file for {session_id} not found"), "session_lookup")
            return

        messages = []
        with open(session_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue

        if _is_capturable(messages):
            _save_candidate(session_id, messages)

    except Exception as exc:
        _log_error(exc, "capture")


def _slash_captured(query: str = "") -> str:
    """Handle /captured slash command."""
    query = query.strip().lower()
    if not query or query == "list" or query == "pending":
        candidates = sorted(CAPTURED_DIR.glob("*.json"), reverse=True)
        lines = [f"Captured candidates: {len(candidates)}", ""]
        for c in candidates[:10]:
            try:
                data = json.loads(c.read_text())
                lines.append(f"- {c.stem}: {data.get('status', '?')} | {len(data.get('tool_sequence', []))} tools | {data.get('task', '')[:60]}")
            except Exception:
                continue
        return "\n".join(lines)
    elif query == "stats":
        candidates = list(CAPTURED_DIR.glob("*.json"))
        statuses = {}
        total_tools = 0
        for c in candidates:
            try:
                data = json.loads(c.read_text())
                s = data.get("status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
                total_tools += data.get("total_tool_calls", 0)
            except Exception:
                continue
        lines = ["Capture Statistics:", f"  Candidates: {len(candidates)}", f"  Total tool calls tracked: {total_tools}", ""]
        for s, count in sorted(statuses.items()):
            lines.append(f"  {s}: {count}")
        return "\n".join(lines)
    return "Usage: /captured [list|stats|pending]"


def initialize(ctx: Any) -> None:
    """Register hooks and slash commands."""
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_slash_command("/captured", _slash_captured)
```

**Estimated effort:** 4 hours

---

### P0.5: End-to-End Verification

**Test the complete flow with a fake captured candidate:**

```python
import json, os, tempfile
from pathlib import Path
from evolution.tools.ingest_captured import validate_candidate, deploy_candidate
from evolution.core.dataset_builder import EvalDataset

# Create fake candidate
candidate = {
    "session_id": "test-123",
    "task": "Explain Jaccard similarity for text overlap detection",
    "captured_at": "2026-05-03T00:00:00Z",
    "status": "pending",
    "domain_tags": ["ml", "text-similarity"],
    "total_tool_calls": 4,
    "skill_body": "# Jaccard Text Overlap\n\nUse Jaccard similarity to detect overlap between a candidate skill body and existing skills.",
    "tool_sequence": ["web_search", "search_files"],
    "success_pattern": "Found 3 similar skills, highest J=0.35",
    "overlapping_skills": []
}
candidate_path = Path.home() / ".hermes" / "captured" / "test-jaccard.json"
candidate_path.write_text(json.dumps(candidate, indent=2))

# Validate
valid, reason, checks = validate_candidate(candidate_path)
assert valid, reason
print("✓ Validation passed")

# Deploy (also calls enrich_and_merge)
ok, msg = deploy_candidate(candidate_path)
assert ok, msg
print(f"✓ Deploy: {msg}")

# Check dataset
ds = EvalDataset.load(Path("datasets/skills/jaccard-text-overlap"))
total = len(ds.train) + len(ds.val) + len(ds.holdout)
assert total == 1, f"Expected 1 example across splits, got {total}"
# Ensure NOT in all 3 (Gap B fix)
assert sum(1 for s in [ds.train, ds.val, ds.holdout] if len(s) > 0) == 1
print("✓ Exactly one split has the example")

# Check rubric (Gap C fix)
ex = (ds.train or ds.val or ds.holdout)[0]
assert "tool" in ex.expected_behavior.lower() or "procedure" in ex.expected_behavior.lower()
assert len(ex.expected_behavior) < 1000
print("✓ Rubric extracted successfully")

# Check metadata (Gap F fix)
assert ex.tool_sequence == ["web_search", "search_files"]
assert ex.complexity_score == 4
assert ex.session_id == "test-123"
print("✓ Metadata fields preserved")

print("\n=== ALL CHECKS PASSED ===")
```

**Estimated effort:** 1 hour

---

## P1 Implementations (Post-Verification)

### P1.1: `--enrich` Flag for `ingest_captured auto`

After `deploy_candidate()`, optionally call `SyntheticDatasetBuilder.generate()` on the deployed SKILL.md, then `merge()` into the existing dataset.

### P1.2: Capture Plugin Integration Tests

- Test `_is_capturable` with 3, 2, 5 tool calls
- Test `_extract_tool_sequence` ordering uniqueness
- Test `_check_overlap` with known skill
- Test `_on_session_end` with fake session file
- Test `assign_split` deterministic distribution
- Test dedup prevents duplicate append

---

## Files to Modify / Create

| File | Action | Effort |
|------|--------|--------|
| `evolution/core/dataset_builder.py` | Extend EvalExample, add merge() and save_atomic() | 2h |
| `evolution/tools/ingest_captured.py` | Add CapturedExampleEnricher, assign_split(), rewrite save_as_sessiondb_example → enrich_and_merge | 3h |
| `~/.hermes/hermes-agent/plugins/captured/plugin.yaml` | Create | 5m |
| `~/.hermes/hermes-agent/plugins/captured/__init__.py` | Build full capture plugin | 4h |
| `tests/tools/test_ingest_captured.py` | Add tests for enrich, split, merge, dedup | 2h |
| `tests/core/test_dataset_builder.py` | Add tests for merge, atomic save | 1h |
| `tests/core/test_capture_plugin.py` | Integration tests (P1) | 2h |
| `docs/phase5_verification.py` | Standalone verification script | 1h |

---

## Daily Breakdown

| Day | Focus | Tasks | Checkpoints |
|-----|-------|-------|-------------|
| **Day 1 (4h)** | Dataset layer | Extend EvalExample + EvalDataset; merge; atomic save | `pytest tests/core/test_dataset_builder.py` passes |
| **Day 1 (4h)** | Ingest rewrite | CapturedExampleEnricher; assign_split; enrich_and_merge | Manual test with fake candidate succeeds |
| **Day 2 (4h)** | Capture plugin | Build capture.py + plugin.yaml + __init__.py | Plugin loads without error; `/captured stats` works |
| **Day 2 (4h)** | End-to-end | Verify real session file triggers capture; validate/deploy/merge works | Verification script (Section 8) passes |
| **Day 3 (4h)** | Tests + polish | Integration tests; edge cases; error handling; performance | All new tests pass; no regressions |
| **Day 3 (4h)** | Buffer / P1 | --enrich flag; deploy existing skill update path; merge with synthetic datasets | Synthetic enrichment works on demand |

---

## Do Not Proceed With Until Verified

- ContentEvolver redesign
- Seed density fix
- LLM-based rubric generation (P2)
- Any Phase 6+ roadmap changes

---

*Implementation plan complete. Ready to execute.*
