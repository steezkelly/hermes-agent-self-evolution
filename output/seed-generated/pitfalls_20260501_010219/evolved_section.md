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