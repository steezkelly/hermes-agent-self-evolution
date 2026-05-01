---
name: synthesize-a-comprehensive-research-repo
description: Synthesize a comprehensive research report from web search, arXiv papers, and wiki notes on a given topic, producing an structured summary with key findings, disagreements, and open questions
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Synthesize a comprehensive research report from web search, arXiv papers, and wiki notes on a given topic, producing an structured summary with key findings, disagreements, and open questions"
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

# Synthesize A Comprehensive Research Repo

Synthesize a comprehensive research report from web search, arXiv papers, and wiki notes on a given topic, producing an structured summary with key findings, disagreements, and open questions


## Steps

1. Set the research topic as a variable (e.g., `topic = "quantum computing"`).
2. Conduct a web search using `web_search(query=topic)` to gather general information and recent developments.
3. Perform an arXiv search using `arxiv_search(query=topic, max_results=10)` to find relevant academic papers.
4. Retrieve wiki notes using `wiki_fetch(topic)` to obtain structured overviews and key facts.
5. Extract key findings, note any disagreements in the literature, and identify open research questions from the collected sources.
6. Synthesize the extracted information into a structured summary report, organized into sections: Key Findings, Disagreements, and Open Questions.

## Pitfalls

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

## Examples

**Input:** *Topic:* "Latest advances in solid-state battery technology (2024-2025)"
**Output:** The agent searches multiple sources (Google Scholar, arXiv, Wikipedia, tech news) and synthesizes a report with:  
- **Key Findings:** NIO’s semi-solid battery reaches 360 Wh/kg; QuantumScape’s lithium-metal anode shows 800+ cycles at 99.95% coulombic efficiency; sulfide-based electrolytes are dominant in R&D.  
- **Disagreements:** Toyota claims solid-state EVs by 2025, but analysts predict mass production nearer 2028-2030.  
- **Open Questions:** How to scale production of sulfide electrolytes without degrading air sensitivity? Can dendrite suppression be solved with graphene interlayers?  
- **Sources:** arXiv:2402.12345, NIO press release, Wikipedia “Solid-state battery” page (retrieved Jan 2025).

**Input:** *Topic:* "Recent debate on neuroplasticity in adult mammalian brains"
**Output:** The agent extracts from PubMed, preprint servers, and neuroscience blogs:  
- **Key Finding:** Single-cell RNA-seq confirms neurogenesis in the human hippocampus declines sharply after adolescence, with only sparse new neurons in adults.  
- **Disagreement:** Gould et al. (2024) argue for functional newborn neurons in the olfactory bulb, while Sorrells et al. (2024) find zero neurogenesis in adults.  
- **Open Question:** Could focal ischemia trigger latent neurogenic niches?  
- **Sources:** Nature Neuroscience 27(3), arXiv:2401.98765, Wikipedia “Adult neurogenesis” (retrieved Feb 2025).

**Input:** *Topic:* "Quantum computing supremacy experiments: 2023-2025 overview"
**Output:** Agent aggregates results from arXiv, IBM, Google, and Chinese Academy of Sciences:  
- **Key Findings:** Google’s Sycamore (2024) suggests quantum advantage for random circuit sampling; Chinese team uses 113-photon BosonSampling to claim “quantum computational advantage.”  
- **Disagreement:** Critics (e.g., Arute, Kalai) argue classical algorithms have nearly closed the gap via tensor network methods.  
- **Open Question:** Is there a clear practical problem (e.g., chemistry simulation) where quantum supremacy is unequivocal and useful?  
- **Sources:** arXiv:2310.14752, IBM blog, Wikipedia “Quantum supremacy” (retrieved Mar 2025).

## Constraints

- Do use at least three distinct web sources, two arXiv papers, and one wiki page as primary inputs for the report.
- Do cite all sources with proper references (URLs, arXiv IDs, or wiki page titles) in a consistent format.
- Do structure the summary into three mandatory sections: Key Findings, Disagreements, and Open Questions.
- Do ensure the report is strictly factual and based solely on the cited sources; avoid personal opinion or speculation.
- Don't include any information from sources that are not explicitly listed or cited.
- Do limit the final report to between 500 and 1500 words.
- Don't plagiarize: paraphrase content and use quotation marks where direct quotes are necessary, with citations.
- Do verify that arXiv papers are from recognized categories (e.g., cs, physics, math, biology) and are published or accepted for publication.
- Don't include content from sources that are outdated (more than 5 years old) unless the topic specifically requires historical context.
- Do check that the topic does not involve prohibited content (e.g., harmful, illegal, or unethical research).
- Don't include unverifiable claims, rumors, or information from non-credible sources (e.g., personal blogs, forums).
- Do ensure the report is self-contained and understandable to a general academic audience without requiring external reading.
- Do use standard English grammar and spelling; avoid jargon without definition.

## Verification

- **Check 1: Report Structure Completeness**  
  *Pass*: The generated report contains all required sections: an abstract, a list of key findings, a discussion of disagreements (if any exist in the literature), and a list of open questions.  
  *Fail*: Any of the required sections is missing or empty.

- **Check 2: Source Attribution**  
  *Pass*: At least 80% of the statements in the report cite a source (e.g., a web URL, arXiv ID, or wiki page reference). The report includes a references section listing all cited sources.  
  *Fail*: Fewer than 80% of statements have an explicit source citation, or the references section is missing.

