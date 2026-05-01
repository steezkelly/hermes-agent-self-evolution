To verify the correctness of this skill, perform the following lightweight checks:

1. **Test on a minimal directory**: Create a temporary directory containing a single Python file with known content, for example `hello.py` with `print("hello")`. Run the skill on that directory. The generated report must include:
   - File count: exactly 1
   - Line count per language: Python should show 1 line (or 0 if blank lines ignored, depending on pygount behavior; accept either as long as consistent)
   - Summary statistics present (e.g., total lines, languages detected)
   - *Pass* if the report matches these expectations; *Fail* if counts are wrong, or if the report is missing key sections.

2. **Test error handling for invalid input**: Run the skill with a non-existent directory path (e.g., `/nonexistent/path`). The skill must output an error message clearly indicating that the directory was not found (or cannot be accessed). *Pass* if an appropriate error is shown; *Fail* if the skill crashes without a user‑friendly message or produces a misleading report.

3. **Estimated complexity hotspots** (optional quick check): Use a small but nested codebase (e.g., a directory with one Python file containing a loop inside a function, plus a trivial file). The report’s “hotspots” section should highlight the file with the looping construct. *Pass* if the hotspot is correctly identified; *Fail* if it’s missing or misattributed (e.g., a single‑line file is flagged).