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