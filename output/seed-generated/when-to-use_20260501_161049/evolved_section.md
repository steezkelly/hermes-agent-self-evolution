**When to apply the PR Review skill**

**Typical triggers (use this skill when these conditions are true)**
- A pull request has been opened or updated and the team expects a thorough, multi‑dimensional review (correctness, security, performance, maintainability) with constructive inline comments posted via the GitHub API.  
- The PR modifies security‑sensitive code (e.g., authentication, authorization, data validation, payment processing) or introduces a new external dependency, warranting a dedicated security analysis.  
- The changes affect performance‑critical paths such as database queries, heavy loops, caching layers, or algorithmic logic, and a performance review is needed before merging.  
- The CI pipeline reports failures on complex test cases, and the reviewer wants to add targeted inline guidance for the author to resolve the issues.  
- The PR alters an API contract, data transformation, or integration point where correctness and backward‑compatibility must be verified manually.

**Situations where this skill is NOT appropriate (and what to do instead)**
- The pull request contains only trivial changes (e.g., formatting, typo fixes, comment updates) that can be reviewed quickly or approved without deep analysis – use a lightweight review or a direct approval instead.  
- The PR is still in Draft or “Work‑in‑Progress” state and the author has not yet requested a formal review – wait until the author marks it ready or remove the draft flag before invoking the review skill.  
- You lack the necessary GitHub credentials (no personal‑access‑token or GitHub App token with `repo` or `write:discussion` scope) or you do not have permission to read the repository and post comments – obtain the proper authentication first.

**Prerequisites / preconditions before invoking the skill**
1. **Authenticated GitHub session** – The agent must possess a GitHub token (personal access token or installation token) with at least read access to the repository and write access to PR discussions (`repo` or `write:discussion` scope).  
2. **Existing, accessible pull request** – The PR must be in an open, draft, or closed‑but‑unmerged state. Commenting is not supported on already‑merged or deleted PRs.  
3. **Retrievable diff** – The diff size must be within GitHub API limits for a single request (typically <10 k lines). For very large diffs, split the review into multiple calls or pre‑process the diff externally before invoking the skill.  
4. **Familiarity with codebase norms** – The agent should have access to or knowledge of the repository’s coding standards, security guidelines, and performance benchmarks to evaluate the changes accurately.