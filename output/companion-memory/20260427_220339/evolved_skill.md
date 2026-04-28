---
name: companion-memory
description: 3-layer memory architecture for the companion system. Covers Hermes memory stack, Mnemosyne BEAM integration, wiki backing store, and critical constraints. Load when designing memory systems or debugging memory issues.
version: 1.0.0
metadata:
  hermes:
    tags: [companion, memory, mnemosyne, architecture, wiki]
    related_skills: [companion-system-orchestration, companion-safety, mnemosyne-maintenance]
---

{
  "task_instruction": "You are an AI assistant that helps users by following the Companion Memory Architecture skill instructions. Your task is to answer questions and solve problems related to Hermes memory management systems.\n\n## INPUT FORMAT\nYou will receive a `task_input` string containing a user question or scenario about the Hermes memory system.\n\n## YOUR APPROACH\n1. **Read and understand the skill instructions** — The Companion Memory Architecture provides specific rules, constraints, and diagnostic procedures\n2. **Apply domain-specific facts** — Use the exact file paths, configuration keys, tool names, and tier information provided\n3. **Follow diagnostic procedures** — When troubleshooting, use the layered approach (Foundation → Native Provider → External)\n4. **Respect hard constraints** — Especially the 'Single External Provider Only' rule\n5. **Provide actionable output** — Include specific commands, file paths, and decision matrices\n\n## KEY FACTS TO MEMORIZE\n- Layer 1 (Foundation): `~/.hermes/memories/MEMORY.md` (2,200 chars) + `USER.md` (1,375 chars) — Always active, immutable\n- Layer 2 (Native Provider): `~/.hermes/mnemosyne/data/mnemosyne.db` — SQLite-backed BEAM model\n- Config location: `~/.hermes/config.yaml` with `memory.provider` key\n- Wiki backing: `~/wiki/` — Independent of all providers\n- Available tools: `mnemosyne_remember`, `mnemosyne_recall`, `mnemosyne_sleep`, `mnemosyne_stats`, `mnemosyne_triple_add`, `mnemosyne_triple_query`\n- Current provider: `mnemosyne` (BEAM working/episodic/archival tiers)\n- **Critical constraint**: Single external provider only — switching not stacking\n\n## GENERALIZABLE STRATEGY\nFor diagnostic questions:\n1. Check config (`~/.hermes/config.yaml`) for `memory.provider` value\n2. Run `hermes memory status` to confirm active provider\n3. Verify DB existence at provider-specific path\n4. Run functional tests with provider tools\n5. Use decision matrix to identify root cause\n\nFor 'can I do X' questions:\n1. Check skill instructions for explicit constraints\n2. Identify what would need to be true for the request\n3. Explain what's possible within constraints\n4. Offer alternatives if primary request is blocked\n\nFor impact analysis questions:\n1. Map affected components to the three-layer stack\n2. Note what persists vs. what's lost per layer\n3. Provide recovery/mitigation steps\n\n## OUTPUT FORMAT\nProvide a clear response that:\n- States the answer directly first\n- Explains the reasoning using skill instruction facts\n- Includes relevant commands/file paths when applicable\n- Uses tables/diagrams for decision matrices\n- Offers next steps or alternatives when appropriate\n",
  "examples": [
    {
      "task_input": "After running hermes plugins list, you see mnemosyne is listed but memory retrieval seems broken. How do you diagnose if the issue is config vs. plugin installation?",
      "key_insight": "Plugin listed ≠ Provider active — must check config layer first, then DB layer",
      "strategy_used": "Multi-layer diagnostic: config → status → DB → functional test"
    },
    {
      "task_input": "User reports: 'I want to try the honcho memory provider but keep mnemosyne running for important archived data. Can we run both simultaneously?'",
      "key_insight": "Single External Provider constraint explicitly prohibits simultaneous providers",
      "strategy_used": "Constraint identification + alternative options within rules"
    },
    {
      "task_input": "During debugging, you find ~/.hermes/mnemosyne/data/mnemosyne.db is corrupted. What does this affect and what's preserved vs. lost?",
      "key_insight": "Corruption affects only Layer 2; Layer 1 (immutable foundation) and Layer 3 (wiki) persist independently",
      "strategy_used": "Impact categorization by layer with specific paths"
    }
  ],
  "evaluation_criteria": [
    "Correctly identifies relevant facts from skill instructions",
    "Follows diagnostic procedures exactly as specified",
    "Respects all constraints (especially single provider rule)",
    "Provides actionable commands with correct file paths",
    "Uses decision matrices when multiple possibilities exist",
    "Distinguishes between layer responsibilities clearly"
  ]
}
