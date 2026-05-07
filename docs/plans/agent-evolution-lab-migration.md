# Agent Evolution Lab Migration Plan

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task if converting this plan into code/docs changes.

Goal: Move the fork from an upstream-named experimental branch toward a coherent Agent Evolution Lab identity without breaking useful links or upstream collaboration paths.

Architecture: Treat the current fork as the lab branch and upstream-compatible fixes as narrow branches based on `upstream/main`. Migrate identity in layers: docs first, repo metadata second, package/import renames only after the public story is stable.

Tech Stack: GitHub repo metadata, markdown docs, Python package metadata, pytest, gh CLI.

---

## Phase 0: Stabilize the story

Status: in progress.

Tasks:

1. Keep issues enabled on the fork.
2. Maintain issue #7 as the decision thread for naming and direction.
3. Keep `docs/project-direction.md` updated as the canonical direction note.
4. Add philosophy and public breadcrumb docs.
5. Update README to make the new direction visible immediately.

Verification:

```bash
gh issue view 7 --repo steezkelly/hermes-agent-self-evolution
python -m pytest -q
```

Expected:

- issue #7 open and linked from docs/comments
- tests passing

## Phase 1: Branding without URL rename

Status: next.

Tasks:

1. Add a README section titled `Agent Evolution Lab` near the top.
2. Add docs links:
   - `docs/philosophy.md`
   - `docs/project-direction.md`
   - `docs/public-breadcrumb-policy.md`
3. Keep repo name unchanged to preserve existing upstream breadcrumb links.
4. Use GitHub description/topics to signal the new identity.

Verification:

```bash
gh repo view steezkelly/hermes-agent-self-evolution --json description,repositoryTopics,url
```

Expected:

- description contains `Agent evolution lab`
- topics include `agent-evolution`, `autonomous-agents`, `skill-evolution`, `evaluation`

## Phase 2: Name decision

Status: pending Steve decision.

Default recommendation:

`agent-evolution-lab`

Alternatives:

- `hermes-evolution-lab`
- `companion-evolution-lab`
- `autopoiesis-lab`
- `skillforge`
- `evolvable-agents`

Decision criteria:

- discoverable by agent developers
- broad enough for tools/prompts/datasets/evals, not only skills
- not too tied to upstream if the product becomes independent
- short enough to remember

## Phase 3: Repository rename

Status: wait until Phase 2 decision.

If choosing `agent-evolution-lab`, rename with:

```bash
gh repo rename agent-evolution-lab --repo steezkelly/hermes-agent-self-evolution
```

Before executing:

1. Confirm GitHub redirects are acceptable.
2. Update local remote URL after rename:

```bash
git remote set-url origin https://github.com/steezkelly/agent-evolution-lab.git
```

3. Update README clone command.
4. Update docs links.
5. Leave a final note on old fork issue #7 if GitHub keeps issue redirects.

## Phase 4: Package naming

Status: later.

Do not immediately rename Python packages/import paths. `evolution.*` imports are generic enough and less disruptive than a package-wide rename.

Potential later changes:

- package display name in `pyproject.toml`
- CLI names
- README quickstart command names
- docs title strings

Guardrail:

No package/import rename without a dedicated migration PR and full tests.

## Phase 5: Public release checkpoint

Status: later.

Create a GitHub release after:

1. README reflects the new identity.
2. install/test path is stable from a fresh venv.
3. core known fork fixes are listed in a changelog.
4. public breadcrumb policy is followed.
5. at least one narrow upstream-compatible PR path is documented.

Candidate release name:

`v0.1.0-agent-evolution-lab-preview`

Verification:

```bash
python -m venv /tmp/ael-verify
. /tmp/ael-verify/bin/activate
pip install -e '.[dev]'
pytest -q
```

Expected:

- full suite passes
- README quickstart works
