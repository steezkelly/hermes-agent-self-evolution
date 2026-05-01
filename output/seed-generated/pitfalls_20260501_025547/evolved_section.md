- **Over-reliance on a single source type**  
  (a) What goes wrong: The agent primarily uses web search results or arXiv papers, ignoring wiki notes for context or vice versa, leading to a lopsided summary.  
  (b) Why it matters: Critical disagreements or open questions may be missing if one source is dominant, reducing the report’s comprehensiveness and reliability.  
  (c) Mitigation/check: Explicitly require at least one source from each category (web, arXiv, wiki) in the final report. Use a checklist or parse the output for source diversity before submission.

- **Failure to distinguish authoritative from non‑authoritative web sources**  
  (a) What goes wrong: The agent treats blog posts, news articles, and opinion pieces on par with peer‑reviewed papers or official documentation, mixing speculation with established findings.  
  (b) Why it matters: The report’s credibility suffers; readers may mistake unverified claims for consensus. This is especially harmful when listing “key findings.”  
  (c) Mitigation/check: Apply a simple heuristic—for web results, prioritize domains ending in .edu, .gov, or known scientific publishers. When in doubt, flag the source’s authority in the summary.

- **Ignoring temporal context in literature**  
  (a) What goes wrong: The agent cites an old arXiv paper as a key finding, unaware that a more recent web article or wiki note has updated or contradicted it.  
  (b) Why it matters: The report becomes outdated or misleading, failing to capture the current state of disagreement or open questions.  
  (c) Mitigation/check: Sort retrieved sources by publication or last‑updated date. Note the year next to each finding and flag any finding older than, say, two years that lacks a corroborating recent source.

- **Misrepresenting disagreements as conflicts instead of nuances**  
  (a) What goes wrong: The agent presents two opposing views as a simple “View A vs View B,” omitting the methodological reasons, differing assumptions, or alternative interpretations that explain the disagreement.  
  (b) Why it matters: The report loses depth; readers cannot assess whether the disagreement is fundamental or resolvable, harming the “open questions” section.  
  (c) Mitigation/check: For each disagreement, require a brief explanation (1–2 sentences) of *why* the positions differ—e.g., different data sets, experimental conditions, or theoretical frameworks.

- **Leaving open questions vague or unfalsifiable**  
  (a) What goes wrong: The agent lists open questions that are too broad (“What is consciousness?”) or that have already been answered in the literature reviewed, wasting space.  
  (b) Why it matters: The structured summary loses its utility; open questions should guide future research, but vague ones are unactionable.  
  (c) Mitigation/check: Use the SMART criteria—open questions must be Specific, Measurable/Answerable through research, Actionable, Relevant to the topic, and Time‑bounded (e.g., “How does method X perform on dataset Y, and has it been replicated?”). Verify that no source in the report definitively answers the question.