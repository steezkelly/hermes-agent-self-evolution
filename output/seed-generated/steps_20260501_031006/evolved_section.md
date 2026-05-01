1. Analyze the codebase directory by running the following command to generate a breakdown of lines per language, file count, and summary statistics: `pygount --format=summary /path/to/directory`.

2. For a more detailed metric report including per-file data, use: `pygount --format=detailed /path/to/directory`.

3. Identify complexity hotspots by examining file-level results (e.g., high total lines or high code/comment ratio). Optionally, filter for specific file extensions or exclude non-code files using the `--suffix` or `--exclude` flags.

4. Compile the output into a structured metrics report (e.g., as a JSON or text file) by saving the output with: `pygount --format=json /path/to/directory > metrics_report.json`. 

5. Review the report to highlight key statistics: total lines of code, comments, blanks, file count per language, and any files with disproportionately high line counts (potential complexity hotspots).