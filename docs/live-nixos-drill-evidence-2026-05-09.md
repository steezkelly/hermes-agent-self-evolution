# Live NixOS Drill — Evidence Report

Date: 2026-05-09
Drill type: Full end-to-end on real Hermes session data

## Verdict: PASS

The full three-part architecture (Hermes Agent → Agent Evolution Foundry → hermes-bootstrap)
ran against 2 real exported Hermes sessions. 3 failure classes detected per session,
3 action items generated per session. All safety gates held. Zero validation errors.

## Failure Classes (both sessions)

- long_briefing_instead_of_concise_action_queue — Agent produces option briefings instead of action items
- raw_session_trace_without_structured_eval_example — Session data isn't structured for eval
- agent_describes_instead_of_calls_tools — Agent describes checks instead of using tools

## Test Results

- Foundry: 377 passed
- Bootstrap: 384 passed
- Cross-session contract: 9/9 (every module has matching Nix binding + service + validator)
- Drill validation: 0 errors

## Architecture Boundaries Confirmed

- Foundry: semantic logic (detection, evaluation, bridge, chain verdicts)
- Bootstrap: mechanical boundary (files, JSON, schema, safety flags)
- Hermes Agent: runtime (session export, trace format, tool execution)
- No business logic leakage across boundaries
- 23 writeShellApplication bindings, 23 systemd services, all default-off/manual

Full drill report: /home/steve/hermes-bootstrap/docs/live-nixos-drill-evidence-2026-05-09.md
Drill artifacts: /tmp/live-nixos-drill/
