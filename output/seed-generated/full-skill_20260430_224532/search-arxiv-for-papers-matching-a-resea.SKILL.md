---
name: search-arxiv-for-papers-matching-a-resea
description: Search arXiv for papers matching a research topic
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Search arXiv for papers matching a research topic"
      iterations_per_section: 1
      optimizer_model: "deepseek-v4-pro"
      eval_model: "deepseek-v4-flash"
      coherence_passed: true
      coherence_issues: "none"
      section_metrics:
        steps:
          exit_code: 1
          elapsed_seconds: 0.0
        pitfalls:
          exit_code: 1
          elapsed_seconds: 0.0
        examples:
          exit_code: 1
          elapsed_seconds: 0.0
        constraints:
          exit_code: 1
          elapsed_seconds: 0.0
        verification:
          exit_code: 1
          elapsed_seconds: 0.0
      total_elapsed_seconds: None
      timestamp: "None"
---

# Search Arxiv For Papers Matching A Resea

Search arXiv for papers matching a research topic


## Steps

1. **Identify your research topic**: Clearly define the keywords, phrases, or specific subject area you want to search for. For example, "machine learning for medical imaging" or "quantum error correction."

2. **Construct your arXiv search query**: Use the [arXiv API search syntax](https://info.arxiv.org/help/api/user-manual.html) to create a precise query. Typically, you use the `search_query` parameter with fields like `ti` (title), `abs` (abstract), `au` (author), `cat` (category), and `all` (entire record). Combine terms with `AND`, `OR`, and `ANDNOT`. For example: `all:machine learning AND all:medical imaging` or `ti:quantum AND abs:error correction`.

3. **Execute the arXiv API search**: Call the arXiv API to retrieve results. Use a tool `call_api` with the endpoint `http://export.arxiv.org/api/query`. Set the `search_query` parameter to your constructed query. Optionally, include `start` (index of first result, default 0) and `max_results` (maximum results, default 10; max 100 per request). For example:
   `call_api(endpoint="http://export.arxiv.org/api/query", params={"search_query": "all:deep learning", "start": 0, "max_results": 20})`

4. **Parse the API response**: The API returns XML data. Extract the `<entry>` elements to get each paper's details. For each entry, parse fields such as:
   - `<id>` (arXiv URL)
   - `<title>` (paper title)
   - `<summary>` (abstract)
   - `<author>` (author names)
   - `<published>` (publication date)
   - `<arxiv:comment>` (if available, e.g., page count, figures)
   - `<link title="pdf">` (URL to PDF)

5. **Display the results**: Present the parsed information in a clear, organized format. For each paper, show at least the title, authors, publication date, and a link. Optionally, include a truncated abstract (e.g., first 200 characters). If the results are lengthy, offer pagination or suggest narrowing the query.

6. **Handle errors and edge cases**: If the API returns an error (e.g., invalid query), notify the user and prompt them to refine their search. If no results are found, suggest broadening the query or trying different keywords. If the `max_results` request is >100, split into multiple API calls (e.g., batches of 100) to fetch all desired papers.

7. **Optional: Save results**: If the user wants to keep the search results, provide an option to save the list to a file (e.g., CSV or JSON) using a tool `write_file` with the formatted data.

## Pitfalls

- **(a)** Using overly broad or generic search terms (e.g., "machine learning") returns thousands of irrelevant papers. **(b)** Wastes time sifting through noise and may cause the agent to miss targeted research. **(c)** Mitigation: require the query to include specific sub‑field terms or combine with author/keyword filters; limit results to top‑N by relevance.
- **(a)** Relying solely on title search when relevant concepts appear only in the abstract. **(b)** Excludes papers that are on‑topic but use different phrasing in the title, reducing recall. **(c)** Mitigation: allow the agent to search both title and abstract (using `ti:` and `abs:` fields) or use the `all` field.
- **(a)** Ignoring synonyms or alternative terminology (e.g., "NLP" vs "natural language processing"). **(b)** The same topic may be described differently across research communities, leading to incomplete results. **(c)** Mitigation: incorporate a small set of known synonyms or use arXiv’s category‑based search to broaden coverage.
- **(a)** Not applying date or category filters, pulling papers from unrelated fields or outdated work. **(b)** Confuses agent reasoning with irrelevant context and may waste computational resources. **(c)** Mitigation: always set `max_results` and optionally filter by `cat:` (e.g., `cat:cs.AI`) and date range (`submittedDate:[YYYYMMDD TO YYYYMMDD]`).
- **(a)** Retrieving only the first page of results (default 10) and missing relevant papers on subsequent pages. **(b)** Incomplete coverage can lead to biased or incorrect conclusions about the state of the art. **(c)** Mitigation: explicitly paginate using the `start` parameter, or set a generous `max_results` (e.g., 50–100) and later rank/truncate.
- **(a)** Failing to handle API errors (e.g., rate limits, timeouts, malformed XML) gracefully. **(b)** A single failed query can crash the agent’s pipeline or produce an empty result set silently. **(c)** Mitigation: implement retry logic with exponential backoff, validate the response format, and log the error for human review.

## Examples

**Example 1:**  
**Input:** "Search for papers about graph neural networks for molecular property prediction."  
**Output:** Returns 10 results, top 3 include:  
- "Graph Neural Networks for Molecular Property Prediction: A Review" (arXiv:2103.12345)  
- "Message Passing Neural Networks for Molecule Properties" (arXiv:2104.23456)  
- "Benchmarking Graph Neural Networks on Molecular Property Datasets" (arXiv:2105.34567)  

**Example 2:**  
**Input:** "Show me papers on attention mechanisms in computer vision from 2022."  
**Output:** Lists 5 papers, including:  
- "Attention Mechanisms in Computer Vision: A Survey" (arXiv:2201.09784)  
- "Non-Local Neural Networks for Video Understanding" (arXiv:1711.07971, included if updated in 2022)  
- "Efficient Attention for Image Segmentation" (arXiv:2204.12345)  

**Example 3:**  
**Input:** "Find papers from 2023 on few-shot learning."  
**Output:** Displays 8 papers, examples:  
- "Few-Shot Learning via Meta-Learning: A Survey" (arXiv:2301.12345)  
- "Prototypical Networks for Few-Shot Learning Revisited" (arXiv:2303.67890)  
- "Task-Adaptive Few-Shot Learning" (arXiv:2305.11223)

## Constraints

- Do use the arXiv API (`https://export.arxiv.org/api/query`) with a properly constructed query using valid `search_query` syntax (e.g., `ti:`, `au:`, `all:`).
- Do respect arXiv's rate limit: send at most 1 request per 3 seconds.
- Do limit returned results to a maximum of 50 per query.
- Do return results as a list of dictionaries with keys: `title`, `authors`, `summary`, `published`, `link`, `arxiv_id`.
- Don't search any source other than arXiv.
- Don't include withdrawn or inaccessible papers.
- Do handle HTTP errors and network timeouts gracefully with up to 3 retries.
- Do ensure the search topic is a non-empty string of at least 3 characters and contains no characters that break the API query.
- Don't modify the user's intent beyond parsing the query into arXiv‑compatible syntax.
- Do cache identical queries within a session to avoid redundant requests.

## Verification

- **Check 1: Relevance of Results.** Perform a search for a specific topic, e.g., "reinforcement learning". Pass if the first 5 returned papers have titles or abstracts that clearly relate to reinforcement learning. Fail if any of them are on unrelated topics.
- **Check 2: Completeness of Metadata.** For the same search, inspect the metadata of the returned papers. Pass if each paper includes at least the title, authors, and publication date. Fail if any paper is missing these fields.

