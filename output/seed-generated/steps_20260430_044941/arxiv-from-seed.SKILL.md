---
name: arxiv-from-seed
description: Search arXiv for academic papers matching a research topic — generated from seed by GEPA, WIP
version: 0.1.0-seed
metadata:
  hermes:
    tags: [research, arxiv, academic-papers, seed-generated]
    generation:
      seed: "Search arXiv for academic papers matching a research topic"
      optimizer: GEPA
      optimizer_model: deepseek/deepseek-v4-pro
      eval_model: deepseek/deepseek-v4-flash
      iterations: 5
      elapsed_seconds: 136.3
      date: "2026-04-30"
      status: wip
---

# arXiv Paper Search

Search arXiv for academic papers matching a research topic.

## Steps

1. **Define your research topic and keywords.** Identify 1-3 core concepts. List synonyms, related terms, and exact phrases. Example: for "reinforcement learning for robotics navigation," keywords include "reinforcement learning," "deep RL," "robotics," "navigation," "path planning."

2. **Open a web browser and navigate to arXiv:** Go to `https://arxiv.org`.

3. **Use the search bar** at the top of the page. Enter your keywords, combining them with Boolean operators for precision:
   - `AND` to require all terms (e.g., `"reinforcement learning" AND robotics`)
   - `OR` to include any of the terms (e.g., `navigation OR "path planning"`)
   - `NOT` to exclude terms
   - Quotation marks `" "` for exact phrases
   - Parentheses to group logic: `("deep learning" OR "neural network") AND (robotics OR drone)`
   - Leaving the field/search as "All fields" will match against title, abstract, author, etc.

4. **Click the "Search" button or press Enter** to submit your query.

5. **Refine using sidebar filters** (on the results page):
   - **Subject class:** select categories like `cs.RO` (Robotics), `cs.LG` (Machine Learning), `cs.CV` (Computer Vision), etc., to narrow by field.
   - **Date range:** set `From` and `To` dates to limit to a specific period.
   - **Order by:** choose "Relevance" or "Announcement date" (newest first).

6. **(Optional) Use Advanced Search:** Click the "Advanced Search" link below the search bar to:
   - Restrict the search to specific metadata fields: title, abstract, author, comments.
   - Combine multiple terms with AND/OR/NOT in a form.
   - Set date filters and subject categories directly.

7. **Browse the list of results.** Each entry shows title, authors, an abstract snippet, submission date, and subject class. Click a title to see the full abstract, all subject tags, and access options.

8. **Access the full paper:** On the paper's detail page, click the "PDF" link to view/download. Alternative formats (HTML, source) may be available under "Other formats."

9. **Export citations:**
   - From the search results page, click the "Export" link at the top to obtain BibTeX, EndNote, or plain-text citations for multiple papers.
   - On an individual paper's page, click the "BibTeX" link to copy its citation.

10. **Automate via the arXiv API:**
    - **Direct HTTP API:** Send a GET request to `http://export.arxiv.org/api/query?search_query=all:your+topic&max_results=100`. URL-encode your query. Additional parameters: `start`, `sortBy` (`relevance`, `lastUpdatedDate`, `submittedDate`), `sortOrder` (`ascending`, `descending`).
    - **Python library:** Install with `pip install arxiv`. Example:
      ```python
      import arxiv
      search = arxiv.Search(
        query = "reinforcement learning AND robotics",
        max_results = 50,
        sort_by = arxiv.SortCriterion.SubmittedDate
      )
      for result in search.results():
          print(result.title, result.pdf_url)
      ```

11. **Iterate and refine:** Adjust your keywords, try synonyms, switch subject categories, or modify date ranges. Use the API to schedule recurring searches for new papers.

## Pitfalls

- Using too broad a query returns thousands of irrelevant results — define keywords precisely first
- Forgetting to URL-encode the API query string — spaces become `+`, special chars need encoding
- Boolean operators are case-sensitive in arXiv search: `AND`, `OR`, `NOT` must be uppercase
- The API's `max_results` parameter is misleading — arXiv actually limits per-request results regardless of what you set

## Verification

- A search for `"reinforcement learning" AND robotics` on arxiv.org returns papers, not an error page
- The Python `arxiv` library example runs without import errors after `pip install arxiv`
- Boolean queries with parentheses and quotes parse correctly in the search bar
