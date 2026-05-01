---
name: design-a-multi-agent-companion-coordinat
description: Design a multi-agent companion coordination protocol: define roles, communication patterns, delegation rules, and escalation paths for a team of companion agents
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Design a multi-agent companion coordination protocol: define roles, communication patterns, delegation rules, and escalation paths for a team of companion agents"
      iterations_per_section: 1
      optimizer_model: "deepseek/deepseek-v4-pro"
      eval_model: "deepseek/deepseek-v4-flash"
      coherence_passed: true
      coherence_issues: "none"
      section_metrics:
        steps:
          exit_code: 0
          elapsed_seconds: 0.0
        pitfalls:
          exit_code: 0
          elapsed_seconds: 0.0
        examples:
          exit_code: 0
          elapsed_seconds: 0.0
        constraints:
          exit_code: 0
          elapsed_seconds: 0.0
        verification:
          exit_code: 0
          elapsed_seconds: 0.0
      total_elapsed_seconds: None
      timestamp: ""
---

# Design A Multi Agent Companion Coordinat

Design a multi-agent companion coordination protocol: define roles, communication patterns, delegation rules, and escalation paths for a team of companion agents


## Steps

1. List all companion agents that will participate in the protocol using `hermes agent list`. Identify their primary functions, capabilities, and current status (online/offline).
2. Define distinct roles for each agent (e.g., primary companion, backup companion, specialist). Create a role assignment file using `hermes task create --name role_definition --template "ROLE: {agent_name} -> {role}"`.
3. Specify communication patterns between agents. Choose from direct messaging, broadcast, or group chat. For each pattern, document the channel name and message format (e.g., JSON schema). Use `hermes config set communication.patterns '{"direct": ["primary", "backup"], "broadcast": ["all"]}'` to store the configuration.
4. Establish delegation rules based on agent capabilities and current load. For example, if a primary companion fails to respond within 5 seconds, delegate to the backup. Write these rules in a delegation policy file using `hermes task create --name delegation_rules --template "RULE: {trigger} -> {delegate_to}"`.
5. Define escalation paths for unresolved issues. Specify thresholds (e.g., after 3 delegation attempts or if no agent can handle the request) and the target (human supervisor or supervisor agent). Save this as an escalation chain using `hermes config set escalation.paths '[{"condition": "unresolved_after_3_attempts", "target": "supervisor_agent"}]'`.
6. Validate the protocol design by running a simulation using `hermes run --skill simulate_coordination --input config_protocol.json`. Review the logs with `hermes log --tail 20` to check for conflicts or gaps.
7. Iterate on the protocol based on simulation results: update role assignments, communication patterns, or rules using `hermes config set` again. Repeat step 6 until all interactions behave as expected.
8. Finalize the protocol by exporting the configuration as a reusable skill artifact using `hermes artifact export --name companion_coordination_protocol`.

## Pitfalls

- **Ambiguous role definitions**: (a) Roles are not clearly delineated, leading to agents either competing for the same task or neglecting responsibilities. (b) This causes duplicate work, missed tasks, and user frustration due to inconsistent responses. (c) **Mitigation**: Explicitly document role boundaries with a responsibility matrix and implement a conflict resolution mechanism (e.g., priority-based arbitration).
- **Inefficient communication patterns**: (a) Agents send excessive or unstructured messages, resulting in high overhead and misinterpretation of intent. (b) This slows coordination and increases error rates, degrading user experience. (c) **Mitigation**: Standardize communication using a shared message schema (e.g., JSON with required fields) and enforce a limit on broadcast messages; use a centralized audit log for context.
- **Ineffective delegation rules**: (a) Agents lack clear criteria for when and to whom to delegate, causing tasks to be assigned to the wrong agent or not delegated at all. (b) This wastes capabilities, increases latency, and reduces overall efficiency. (c) **Mitigation**: Maintain a capability registry for each agent and implement rule-based delegation (e.g., match task type to agent skill score).
- **Undefined escalation paths**: (a) When an agent fails or is stuck, there is no backup procedure, leaving the user unresolved. (b) This erodes trust and can cause permanent task abandonment. (c) **Mitigation**: Define a hierarchical escalation chain with timeouts (e.g., 5 seconds per level) and designate fallback agents for each role.
- **Over-reliance on a central coordinator**: (a) All coordination flows through a single agent, creating a single point of failure. (b) If that coordinator crashes, the entire system becomes unresponsive. (c) **Mitigation**: Implement a decentralized coordination protocol (e.g., gossip-based handoff) or deploy redundant coordinators with automatic failover.
- **Inconsistent state synchronization**: (a) Agents maintain separate views of shared context (e.g., user session, task progress), leading to contradictory actions. (b) This confuses the user and may cause irreversible errors. (c) **Mitigation**: Use a shared state store with optimistic concurrency control (e.g., versioned database) and enforce eventual consistency with periodic reconciliation.
- **Inadequate error handling**: (a) Failures during delegation or task execution are not gracefully handled, leading to cascading errors. (b) This destabilizes the agent team and can cause system-wide crashes. (c) **Mitigation**: Implement retry logic with exponential backoff, circuit breakers, and alerting mechanisms for persistent failures.
- **Lack of agent authentication**: (a) Agents can impersonate one another or accept commands from untrusted sources. (b) This opens the door to malicious actions, data leaks, or unauthorized operations. (c) **Mitigation**: Use mutual TLS or API tokens for inter-agent communication, and validate all requests against a trusted identity registry.

## Examples

**Example 1: Simple Task Delegation via Role-Based Communication**

- **Input:** A user asks, "I need a recipe for a dairy-free chocolate cake."

- **Protocol Execution:**
    1. User Input Agent receives the request and classifies it under "Cooking & Diet."
    2. Delegation Rule: This topic is routed to the Food & Nutrition Companion Agent.
    3. Communication Pattern: The Food Agent accesses its recipe database and filters for "dairy-free" and "chocolate cake."
    4. The agent returns a short recipe with a link to a full source.

- **Output/Result (to user):** "Here’s a simple dairy-free chocolate cake recipe: 1 ½ cups flour, 1 cup sugar, ⅓ cup cocoa powder, 1 tsp baking soda, ½ tsp salt, 1 cup water, ⅓ cup vegetable oil, 1 tbsp vinegar, 1 tsp vanilla. Mix dry ingredients, add wet, bake at 350°F for 30 min. Full instructions: [link]"

---

**Example 2: Escalation Path for Out-of-Scope Request**

- **Input:** "Can you check my blood pressure from my wearable and tell me if it’s dangerous?"

- **Protocol Execution:**
    1. Health Monitoring Agent receives request. It detects this involves medical diagnosis.
    2. Escalation Rule: The agent cannot provide medical advice. It follows the escalation path:  
       - Level 1: Inform the user of limitations.  
       - Level 2: If user persists, offer to connect to a human healthcare provider via a secure link.
    3. Communication Pattern: The agent sends a polite refusal and a referral to a telehealth service.

- **Output/Result (to user):** "I cannot interpret blood pressure readings for medical diagnosis. For safety, please consult a healthcare professional. Would you like me to connect you to a telehealth provider?"

---

**Example 3: Multi-Agent Coordination and Conflict Resolution**

- **Input:** "I have a dentist appointment at 3 PM today, but also a project deadline at 5 PM. Help me plan."

- **Protocol Execution:**
    1. Scheduling Agent and Task Management Agent both claim relevance.  
    2. Delegation Rule: A collaborative task is established.  
       - Scheduling Agent handles the dentist appointment (time, location, travel).  
       - Task Management Agent handles the deadline (steps, estimated work time).  
    3. Communication Pattern: Agents negotiate without conflict. The Task Agent calculates 2 hours needed for the project. The Scheduling Agent notes travel time (30 min).  
    4. Combined output.

- **Output/Result (to user):** "Here’s a plan:  
   - Dentist at 3:00 PM (leave home by 2:25 PM).  
   - Return by 3:45 PM.  
   - Work on project from 3:45 PM to 5:45 PM.  
   - Submit by 5:00 PM? You might need to start earlier or adjust. Would you like me to block out time now?"

## Constraints

- Do explicitly define each agent's role and capabilities before any task delegation.
- Do use a standardized message format (JSON with fields: sender_id, receiver_id, message_type, payload, timestamp) for all inter-agent communication.
- Do confirm task delegation via an acknowledgment message within 5 seconds; if not received, the delegating agent must escalate to the designated coordinator.
- Don't allow agents to delegate tasks to themselves or to agents with conflicting roles.
- Don't permit communication outside the approved protocol channels (e.g., no direct agent-to-external-API calls without coordinator mediation).
- Escalation paths must be acyclic and terminate at a single ultimate coordinator agent to prevent infinite loops.
- Do log all communication and delegation actions with timestamps; retain logs for at least 30 days for debugging and auditing.
- Don't modify another agent's internal state or memory; all state changes must go through the protocol's designated state management agent.

## Verification

To verify the correctness of the multi-agent companion coordination protocol, perform the following lightweight tests:

1. **Role and Delegation Consistency Check**  
   - For each defined role (e.g., primary companion, specialist, supervisor), verify that at least one delegation rule is specified (e.g., "a primary companion may delegate medical queries to the health specialist").  
   - **Pass**: All roles have at least one delegation rule, and no rules conflict (e.g., two roles both claim authority over the same task type).  
   - **Fail**: Any role lacks a delegation rule, or a rule creates circular delegation (e.g., A delegates to B, B delegates back to A without termination).

2. **Escalation Path Simulation**  
   - Simulate a scenario where a primary companion receives a request it cannot handle (e.g., a legal question with no assigned specialist).  
   - Manually inspect the protocol’s escalation definition: verify it specifies the trigger (e.g., timeout or explicit failure), the next agent or channel (e.g., supervisor agent or fallback to human), and the expected response within a defined timeframe.  
   - **Pass**: The escalation path is clearly documented (trigger, target, expected action) and leads to a resolvable endpoint (e.g., a human handoff or a higher-level agent).  
   - **Fail**: The escalation path is missing, ambiguous, or loops infinitely (e.g., no defined final handler).

These checks ensure the protocol’s core components—roles, delegation, and escalation—are correctly defined and actionable.

