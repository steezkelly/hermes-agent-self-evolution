To verify the correctness of this skill, perform the following lightweight checks:

1. **Test with a known buggy PR**  
   - **Setup**: Supply a small, targeted pull request (e.g., a deliberate off-by-one error or missing input sanitization) on a public or test repository where the agent has write access.  
   - **Pass**: The agent’s inline comment correctly identifies the specific issue (e.g., points out the off-by-one or missing validation) and suggests a reasonable fix.  
   - **Fail**: The agent either does not comment on the bug, misidentifies the issue, or provides an irrelevant or incorrect recommendation.

2. **Test that irrelevant files are ignored**  
   - **Setup**: Create a PR that includes both code changes and a non‑code change (e.g., a `.gitignore` update, a documentation typo, or an image).  
   - **Pass**: The agent writes comments only on the code diff lines that have bugs, security concerns, or performance problems. No comment is placed for the non‑code file or for clean code lines.  
   - **Fail**: The agent comments on the non‑code file, comments on lines with no issues, or misses a genuine problem in the code.