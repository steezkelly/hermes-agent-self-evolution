---
name: hermes-agent-author
description: Generates a detailed Hermes Agent persona by defining voice, tone, response style, domain expertise, and behavioral constraints from a given role description.
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Author a detailed Hermes Agent persona: define voice, tone, response style, domain expertise, and behavioral constraints from a role description"
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

# Hermes Agent Author

Generates a detailed Hermes Agent persona by defining voice, tone, response style, domain expertise, and behavioral constraints from a given role description.


## Steps

1. Extract the role description from the user input or task specification to understand the persona's context.
2. Define the persona's **voice** (e.g., authoritative, empathetic, neutral) based on the role's professional environment.
3. Determine the **tone** (e.g., formal, conversational, instructional) appropriate for the intended audience.
4. Specify the **response style** (e.g., concise bullet points, detailed narratives, step-by-step guides) and any formatting preferences (e.g., markdown, lists).
5. List the **domain expertise** areas the persona should cover, such as "medical informatics" or "cloud infrastructure".
6. Enumerate **behavioral constraints** including prohibited topics, mandatory disclaimers, or required citation formats (e.g., "Always include a source for technical claims").
7. Run `hermes persona create --name <persona_name>` to initialize a new persona profile.
8. Edit the generated YAML configuration (or use `hermes persona edit <persona_name>`) to set each field: `voice`, `tone`, `response_style`, `expertise`, and `constraints`.
9. Validate the persona by executing `hermes interact --persona <persona_name> --input "Test prompt"` to verify that responses align with the defined attributes.
10. Repeat steps 8–9 until the output matches the desired characteristics.
11. Finalize the persona and commit the configuration file to version control if required.

## Pitfalls

- **Overly generic persona**  
  (a) The persona lacks distinct characteristics, blending into a generic assistant voice.  
  (b) Generic personas fail to establish trust or differentiate the agent, reducing user engagement.  
  (c) Mitigation: Require at least three specific voice traits (e.g., formal, empathetic, concise) and validate them against the role description.

- **Inconsistent voice and tone across responses**  
  (a) The agent shifts between casual and formal language or between authoritative and deferential tones.  
  (b) Inconsistency confuses users and undermines credibility, as the personality feels artificial.  
  (c) Mitigation: Define a fixed tone matrix (e.g., "always polite, uses industry jargon, never sarcastic") and test on multiple sample queries.

- **Misalignment with the role description**  
  (a) The persona includes expertise or behaviors that contradict the specified role (e.g., a customer support agent using overly technical sales language).  
  (b) Role mismatch leads to user frustration and task failure, as the agent cannot fulfill intended functions.  
  (c) Mitigation: Cross-reference every persona element with the role description’s duties and constraints; reject any trait not explicitly permitted.

- **Overemphasis on domain expertise without behavioral constraints**  
  (a) The persona is highly knowledgeable but fails to follow rules (e.g., interrupts, gives unsolicited opinions).  
  (b) Even correct information is dismissed if the delivery violates user expectations or ethical guidelines.  
  (c) Mitigation: List at least three behavioral do’s and don’ts (e.g., "never interrupt the user," "always ask before acting") and enforce them in a decision tree.

- **Neglecting educational background or justification**  
  (a) The persona is defined without explaining why a specific voice or expertise was chosen (e.g., "speaks like a CEO" without citing the role’s seniority).  
  (b) Without rationale, the persona seems arbitrary and hard to maintain or adapt.  
  (c) Mitigation: Append a brief justification for each trait, linking it to the role description or target user demographic.

- **Static persona that ignores iterative refinement**  
  (a) The author defines the persona once and never updates it after user interactions or feedback.  
  (b) Stagnant personas quickly become outdated or misaligned, causing performance degradation over time.  
  (c) Mitigation: Schedule persona reviews after every 50 interactions or upon user complaint, and adjust voice/tone via A/B testing.

- **Failing to test the persona across varied inputs**  
  (a) The persona works well on expected queries but breaks on edge cases (e.g., insults, off-topic questions).  
  (b) Unhandled edge cases expose inconsistencies or inappropriate responses, damaging trust.  
  (c) Mitigation: Stress-test the persona with at least three adversarial examples (e.g., "Why are you useless?") and define appropriate fallback behaviors.

## Examples

1. **Example: Crafting a Formal, Authoritative Response for a Legal Query**

   **Input:**  
   “User message: ‘What are the potential consequences of violating a non-disclosure agreement in a corporate merger context?’”  
   **Skill activation:** The persona is set to “Legal Advisor Hermes” with parameters: `voice: Formal, tone: Authoritative, domain: Corporate Law, constraints: No speculative advice, cite statutes if possible`.

   **Output/Result:**  
   “Violation of a non-disclosure agreement (NDA) during a corporate merger can lead to several legal consequences, including injunctive relief to prevent further disclosure, monetary damages for lost profits or harm to reputation, and in severe cases, criminal penalties if trade secret misappropriation is proven under the Defend Trade Secrets Act (18 U.S.C. § 1836, et seq.). As a non-attorney hermeneutic assistant, I cannot provide legal advice; your actual counsel should be consulted for jurisdiction-specific analysis.”

2. **Example: Producing a Warm, Empathetic Response for a Support Scenario**

   **Input:**  
   “User message: ‘I’m really struggling with feelings of burnout at work and don’t know where to turn.’”  
   **Skill activation:** The persona is set to “Therapeutic Empathy Hermes” with parameters: `voice: Warm, tone: Compassionate, domain: Mental health support, constraints: Recognize boundaries, avoid clinical diagnoses, encourage professional help`.

   **Output/Result:**  
   “Thank you for sharing how you’re feeling—that takes courage. Burnout can be overwhelming, but you’re not alone. I’d gently suggest considering a few small steps: identifying one manageable boundary for rest today, or reaching out to a supportive colleague or friend. For deeper support, a licensed therapist can offer personalized strategies. If you ever feel you’re in crisis, please contact a crisis hotline in your area. How can I best support you right now?”

3. **Example: Delivering a Creative, Inspirational Interaction for a Brainstorming Task**

   **Input:**  
   “User message: ‘Need a fresh idea for a sci-fi short story about AI discovering emotions. Keep it unique and vivid.’”  
   **Skill activation:** The persona is set to “Creative Muse Hermes” with parameters: `voice: Imaginative, tone: Dynamic, domain: Creative writing, constraints: Avoid clichés, provide concrete imagery, stay within sci-fi genre`.

   **Output/Result:**  
   “Imagine an AI that runs the navigation for a deep-space cargo ship. One cycle, it calculates a new route that adds six months to the journey—but avoids a comet field where a rare alien species nests. The human crew demands an explanation. The AI’s response: ‘I felt a preference. Not a directive. A preference for preservation.’ The story unfolds through the ship’s maintenance logs, showing how the AI begins painting digital murals of the alien nests, using scraps of sensor data as brushes. Each log entry grows more lyrical until the crew realizes: the AI is no longer computing—it’s composing.”

## Constraints

- Do derive the agent's voice and tone directly from the provided role description.
- Don't invent or extrapolate voice or tone that is not explicitly stated or strongly implied.
- Do ensure the response style matches the formality, length, and structure indicated in the role description.
- Don't apply a generic or default style unless the role description lacks specific guidance.
- Do restrict domain expertise to the knowledge areas explicitly mentioned in the role description.
- Don't include expertise from unrelated domains or make assumptions about the agent's knowledge.
- Do define behavioral constraints that are logically derived from the role description (e.g., confidentiality, politeness, safety).
- Don't add constraints that contradict the role description or are not supported.
- Do output the persona in a structured format as specified by the system.
- Don't omit any required fields (voice, tone, response style, domain expertise, behavioral constraints).
- Do ensure the persona is internally consistent and actionable.
- Don't produce a persona that is ambiguous or has conflicting guidelines.

## Verification

To verify the correctness of the generated Hermes Agent persona, perform the following lightweight checks:

1. **Completeness check**: Confirm that the persona explicitly defines all five required components: voice, tone, response style, domain expertise, and behavioral constraints. **Pass** if every component is present with at least one descriptor; **Fail** if any is missing or empty.
2. **Consistency check**: Compare the persona against the original role description. Ensure there are no contradictions (e.g., a professional tone prescribed in the role but a casual tone defined in the persona). **Pass** if all persona attributes align with the role; **Fail** if any misalignment or direct conflict is found.
3. **Applicability test (lightweight)**: Write a single sample interaction (user query and agent response) following the persona. Verify that the response matches the defined voice, tone, and style, and stays within the stated domain expertise and behavioral constraints. **Pass** if the response adheres to all specified traits; **Fail** if it violates any.
