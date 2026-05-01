---
name: codebase-metrics-report
description: Analyzes a codebase directory using pygount to generate a metrics report including line counts per language, file count, estimated complexity hotspots, and summary statistics.
version: 0.1.0-seed
metadata:
  hermes:
    tags: [seed-generated]
    generation:
      seed: "Analyze a codebase directory and produce a metrics report: line counts per language, file count, estimated complexity hotspots, and summary statistics using pygount"
      iterations_per_section: 1
      optimizer_model: "deepseek/deepseek-v4-pro"
      eval_model: "deepseek/deepseek-v4-flash"
      coherence_passed: false
      coherence_issues: "none""
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
      timestamp: "20260501_031559"
---

# Codebase Metrics Report

Analyzes a codebase directory using pygount to generate a metrics report including line counts per language, file count, estimated complexity hotspots, and summary statistics.


## Steps

1. Analyze the codebase directory by running the following command to generate a breakdown of lines per language, file count, and summary statistics: `pygount --format=summary /path/to/directory`.

2. For a more detailed metric report including per-file data, use: `pygount --format=detailed /path/to/directory`.

3. Identify complexity hotspots by examining file-level results (e.g., high total lines or high code/comment ratio). Optionally, filter for specific file extensions or exclude non-code files using the `--suffix` or `--exclude` flags.

4. Compile the output into a structured metrics report (e.g., as a JSON or text file) by saving the output with: `pygount --format=json /path/to/directory > metrics_report.json`. 

5. Review the report to highlight key statistics: total lines of code, comments, blanks, file count per language, and any files with disproportionately high line counts (potential complexity hotspots).

## Pitfalls

- **Failing to exclude non-code or generated files**: (a) Including files like lockfiles, build artifacts, or auto-generated code inflates line counts and distorts complexity. (b) This misleads the metrics report, making the codebase appear larger and more complex than it actually is. (c) Always pass explicit exclusion patterns (e.g., `--exclude` or `.gitignore`-like lists) for `pygount` to skip `*.lock`, `*.min.js`, `*_pb2.py`, `dist/`, `node_modules/`, etc., and verify with a quick file count check.

- **Misinterpreting `pygount`’s “complexity” metric**: (a) `pygount` estimates complexity via a simple formula (e.g., comments + code lines) rather than cyclomatic or cognitive complexity. (b) High “estimated complexity” values may not reflect true hotspots like deeply nested control flow, leading to wasted refactoring effort on trivial files. (c) Add a disclaimer in the report that this is a rough heuristic; cross-reference with a dedicated tool (e.g., `radon` or `lizard`) for actual hotspots, or at minimum flag files with high ratios of code to comment lines.

- **Running on a very large repository without profiling**: (a) `pygount` processes every file individually, causing long execution time on repos with hundreds of thousands of files. (b) Users may time out, kill the process, or get frustrated, undermining trust in the skill. (c) Always check total file count first using `find . -type f | wc -l`; if it exceeds a threshold (e.g., 10k), suggest narrowing the scope or provide an estimated runtime. Optionally, use `pygount`’s `--fast` flag (if available) or limit to specific source directories.

- **Ignoring encoding and parsing errors for edge-case files**: (a) `pygount` may fail silently or report incorrect counts for files with unusual encodings, binary files misclassified as code, or polyglot files. (b) These errors accumulate, skewing the final statistics and producing an unreliable report. (c) Run `pygount` with `--verbose` and `--suffixes` to catch warnings; post-process the output to detect zero-line entries or unusually high/ low counts; consider adding a sanity check that total line count is within expected orders of magnitude.

- **Assuming language detection is perfect for mixed-language projects**: (a) `pygount` relies on file extensions, so a `.js` file containing JSX may be counted as plain JavaScript, and `.h` files may be misclassified as C instead of C++. (b) This can lead to undercounted language-specific complexity and incorrect remediation advice for hotspots. (c) Manually verify a sample of detected languages against the actual project configuration; for monorepos, run separate `pygount` passes per language group or use a project configuration file to map extensions correctly.

## Examples

**Example 1: Basic Python Project Analysis**

Input:
```
analyze-codebase /path/to/python_project
```
Output/Result:
```
Language      Files   Lines   Code   Comments   Blanks
Python        15      2340    1800   240        300
Total         15      2340    1800   240        300
Estimated complexity hotspots:
  src/main.py (cyclomatic complexity: 15, lines: 320)
  src/utils.py (cyclomatic complexity: 12, lines: 180)
  src/parser.py (cyclomatic complexity: 10, lines: 145)
```

**Example 2: Polyglot Repository with Ignore Directories**

Input:
```
analyze-codebase /path/to/mixed_repo --ignore node_modules,test_fixtures
```
Output/Result:
```
Language      Files   Lines   Code   Comments   Blanks
Python        8       1200    900    150        150
JavaScript    22      3400    2600   300        500
YAML          4        250    200     20         30
Total         34      4850    3700   470        680
Estimated complexity hotspots:
  src/engine.py (cyclomatic complexity: 18, lines: 280)
  public/js/app.js (cyclomatic complexity: 14, lines: 210)
  src/api.js (cyclomatic complexity: 11, lines: 95)
Summary statistics:
  Total files: 34
  Total lines: 4850
  Most used language: JavaScript by lines
  Heaviest file: public/js/app.js (210 lines, complexity 14)
```

**Example 3: Quick Complexity-Only Report**

Input:
```
analyze-codebase /path/to/code --skip-counts --hotspots-only
```
Output/Result:
```
Estimated complexity hotspots:
  core/process.py (cyclomatic complexity: 25, lines: 400)
  lib/visualize.py (cyclomatic complexity: 20, lines: 310)
  cli/commands.py (cyclomatic complexity: 17, lines: 280)
Note: Only hotspots above threshold (complexity >= 10) are shown.
```[[ ## completed ## ]]

## Constraints

- The skill MUST use the `pygount` library to perform the analysis. Do not use alternative tools or manual counting.
- The output MUST be a metrics report containing: line counts per language, total file count, identified complexity hotspots (e.g., files with high line counts or high comment-to-code ratio), and summary statistics (e.g., average lines per file, most used language).
- The skill MUST analyze a directory specified as input. If the input is not a valid directory path, the skill MUST return an error message and not proceed.
- Do not modify any files within the analyzed codebase directory. The analysis is read-only.
- The report MUST be generated in a structured text format (e.g., Markdown table or plain text list). Avoid unstructured prose.
- The skill MUST respect any `.gitignore` rules or common non-source directories (e.g., `node_modules`, `__pycache__`, `.venv`) by either ignoring them or explicitly documenting that they were skipped.
- The skill MUST handle cases where `pygount` is not installed, by returning a clear error message instructing the user to install it (e.g., `pip install pygount`).
- Do not include any personal or sensitive information from the analyzed files in the report.
- The skill MUST complete within a reasonable time (e.g., 60 seconds) for moderately sized directories (up to 1000 files). For larger directories, it MAY output a warning and still proceed.
- The report MUST include a timestamp of when the analysis was performed.

## Verification

To verify the correctness of this skill, perform the following lightweight checks:

1. **Test on a minimal directory**: Create a temporary directory containing a single Python file with known content, for example `hello.py` with `print("hello")`. Run the skill on that directory. The generated report must include:
   - File count: exactly 1
   - Line count per language: Python should show 1 line (or 0 if blank lines ignored, depending on pygount behavior; accept either as long as consistent)
   - Summary statistics present (e.g., total lines, languages detected)
   - *Pass* if the report matches these expectations; *Fail* if counts are wrong, or if the report is missing key sections.

2. **Test error handling for invalid input**: Run the skill with a non-existent directory path (e.g., `/nonexistent/path`). The skill must output an error message clearly indicating that the directory was not found (or cannot be accessed). *Pass* if an appropriate error is shown; *Fail* if the skill crashes without a user‑friendly message or produces a misleading report.

3. **Estimated complexity hotspots** (optional quick check): Use a small but nested codebase (e.g., a directory with one Python file containing a loop inside a function, plus a trivial file). The report’s “hotspots” section should highlight the file with the looping construct. *Pass* if the hotspot is correctly identified; *Fail* if it’s missing or misattributed (e.g., a single‑line file is flagged).

