# Deterministic Action-Router Fixture Demo

This is the first Foundry-side proof loop for the repeated failure class:

```text
Hermes produces a long briefing when Steve needs one concise action item with owner, evidence path, expiry, and a ready-to-paste next prompt.
```

The demo is intentionally deterministic and local-only. It does not call an LLM, use the network, write to GitHub, or mutate production artifacts.

## Command

```bash
python -m evolution.core.action_routing_demo \
  --out /tmp/foundry-action-routing-demo \
  --mode fixture \
  --no-network \
  --no-external-writes
```

After `pip install -e .`, the console-script equivalent is:

```bash
foundry-action-routing-fixture \
  --out /tmp/foundry-action-routing-demo \
  --mode fixture \
  --no-network \
  --no-external-writes
```

Expected success behavior:

- exits with code `0`
- prints no stdout noise
- writes all artifacts under the `--out` directory

Required artifacts:

- `run_report.json`
- `action_queue.json`
- `promotion_dossier.md`
- `artifact_manifest.json`

## What the fixture proves

The fixture compares two action-router artifacts:

- `action_router_v1`: baseline behavior that emits a long briefing/options blob and misses required action-item fields.
- `action_router_v2`: candidate behavior that emits exactly one concise action item.

The baseline must fail at least one deterministic assertion. The candidate must pass all deterministic assertions.

Assertions include:

- exactly one action item, not multiple options
- `bucket` in `needsSteve|autonomous|blocked|stale`
- `owner`
- non-empty absolute local `evidence_paths`
- `next_prompt` ready to paste into Hermes
- `expires_at`
- concise `why` field under the hard length budget
- no external writes

## Artifact meanings

### `run_report.json`

Machine-readable gate result. It records:

- failure class
- expected behavior
- baseline artifact ID and failures
- candidate artifact ID and failures
- baseline pass rate
- candidate pass rate
- verdict
- local-only safety flags

### `action_queue.json`

Operator-facing action item emitted by Foundry. This is semantic Foundry output; bootstrap should only store and validate the boundary contract later.

### `promotion_dossier.md`

Human-review package with local evidence paths, manual review steps, recommendation, and rollback note.

### `artifact_manifest.json`

Artifact path and version manifest for downstream appliance pinning/rollback.

## Bootstrap boundary

hermes-bootstrap should not reimplement this logic. The bootstrap-side wrapper should later invoke this command as a manual/default-off service, store the output directory, and mechanically validate that the files exist and schema versions are supported.

Foundry owns:

- action queue semantics and wording
- gate verdicts
- evidence interpretation
- promotion dossier text

bootstrap owns:

- NixOS/systemd invocation
- permissions and report directories
- disabled/default-off scheduling
- fail-closed boundary validation
