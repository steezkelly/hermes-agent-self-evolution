"""Constraint validators for evolved artifacts.

Every candidate variant must pass ALL constraints before it can be
considered valid. Failed constraints = immediate rejection.
"""

import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from evolution.core.config import EvolutionConfig


@dataclass
class ConstraintResult:
    """Result of constraint validation."""
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None


class ConstraintValidator:
    """Validates evolved artifacts against hard constraints."""

    def __init__(self, config: EvolutionConfig):
        self.config = config

    def validate_all(
        self,
        artifact_text: str,
        artifact_type: str,
        baseline_text: Optional[str] = None,
    ) -> list[ConstraintResult]:
        """Run all applicable constraints. Returns list of results."""
        results = []

        # 1. Size limits
        results.append(self._check_size(artifact_text, artifact_type))

        # 2. Growth limit (if baseline provided)
        if baseline_text:
            results.append(self._check_growth(artifact_text, baseline_text, artifact_type))

        # 3. Non-empty
        results.append(self._check_non_empty(artifact_text))

        # 4. Structural integrity
        if artifact_type == "skill":
            results.append(self._check_skill_structure(artifact_text))

        # 5. CLI command validity (skills only — check hermes commands actually exist)
        if artifact_type == "skill":
            results.append(self._check_cli_syntax(artifact_text))

        return results

    def run_test_suite(self, hermes_repo: Path) -> ConstraintResult:
        """Run the full hermes-agent test suite. Must pass 100%."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no"],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(hermes_repo),
            )

            if result.returncode == 0:
                return ConstraintResult(
                    passed=True,
                    constraint_name="test_suite",
                    message="All tests passed",
                    details=result.stdout.strip().split("\n")[-1] if result.stdout else "",
                )
            else:
                # Extract failure summary
                last_lines = result.stdout.strip().split("\n")[-5:] if result.stdout else []
                return ConstraintResult(
                    passed=False,
                    constraint_name="test_suite",
                    message="Test suite failed",
                    details="\n".join(last_lines),
                )
        except subprocess.TimeoutExpired:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message="Test suite timed out (300s)",
            )
        except Exception as e:
            return ConstraintResult(
                passed=False,
                constraint_name="test_suite",
                message=f"Failed to run tests: {e}",
            )

    def _check_size(self, text: str, artifact_type: str) -> ConstraintResult:
        size = len(text)
        if artifact_type == "skill":
            limit = self.config.max_skill_size
        elif artifact_type == "tool_description":
            limit = self.config.max_tool_desc_size
        elif artifact_type == "param_description":
            limit = self.config.max_param_desc_size
        else:
            limit = self.config.max_skill_size  # Default

        if size <= limit:
            return ConstraintResult(
                passed=True,
                constraint_name="size_limit",
                message=f"Size OK: {size}/{limit} chars",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="size_limit",
                message=f"Size exceeded: {size}/{limit} chars ({size - limit} over)",
            )

    def _check_growth(self, text: str, baseline: str, artifact_type: str) -> ConstraintResult:
        growth = (len(text) - len(baseline)) / max(1, len(baseline))
        # Size-aware growth limit: small skills get more room to grow.
        # Small skills (< 5KB) often need to add concrete details, file paths,
        # examples, and operational context. Large skills (> 20KB) are already
        # saturated and can't improve much anyway (GEPA ceiling).
        baseline_size = len(baseline)
        if baseline_size < 5_000:
            max_growth = 1.0   # +100% — allow small skills room to add detail
        elif baseline_size < 20_000:
            max_growth = 0.5   # +50% — moderate room for medium skills
        else:
            max_growth = 0.2   # +20% — large skills are saturated

        # Shrinkage limit: excessive deletion is a common failure mode where
        # GEPA replaces detailed content with vague summaries. The baseline_size
        # thresholds mirror growth (small skills can be refactored more aggressively).
        if baseline_size < 5_000:
            min_growth = -0.5   # -50% for small skills
        elif baseline_size < 20_000:
            min_growth = -0.3   # -30% for medium skills
        else:
            min_growth = -0.2   # -20% for large skills

        if growth < min_growth:
            return ConstraintResult(
                passed=False,
                constraint_name="growth_limit",
                message=f"Shrinkage too large: {growth:+.1%} (floor {min_growth:+.1%})",
            )

        if growth <= max_growth:
            return ConstraintResult(
                passed=True,
                constraint_name="growth_limit",
                message=f"Growth OK: {growth:+.1%} (max {max_growth:+.1%}, floor {min_growth:+.1%})",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="growth_limit",
                message=f"Growth exceeded: {growth:+.1%} (max {max_growth:+.1%})",
            )

    def _check_non_empty(self, text: str) -> ConstraintResult:
        if text.strip():
            return ConstraintResult(
                passed=True,
                constraint_name="non_empty",
                message="Artifact is non-empty",
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="non_empty",
                message="Artifact is empty",
            )

    def _check_skill_structure(self, text: str) -> ConstraintResult:
        """Check that a skill file has valid YAML frontmatter AND a substantive body.

        Frontmatter validation (YAML between --- markers):
        - Must start with ---
        - Must contain 'name:' field
        - Must contain 'description:' field

        Body validation (markdown after frontmatter):
        - Must have at least 2 of 3: headings, procedural content, substantial length
        This allows varied skill formats while ensuring meaningful content.
        """
        has_frontmatter = text.strip().startswith("---")
        has_name = "name:" in text[:500] if has_frontmatter else False
        has_description = "description:" in text[:500] if has_frontmatter else False

        frontmatter_ok = has_frontmatter and has_name and has_description

        # Separate body from frontmatter for body validation
        body = text
        if has_frontmatter:
            parts = text.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()

        # Body must have ≥2 of 3: headings, procedural content, substantial length
        has_headings = bool(re.search(r"^#+\s", body, re.MULTILINE))
        has_steps = any(
            marker in body.lower()
            for marker in ["step", "1.", "procedure", "how to", "instructions"]
        )
        has_content = len(body.strip()) > 100

        body_checks = {
            "headings": has_headings,
            "procedural content": has_steps,
            "substantial content": has_content,
        }
        body_passed = sum(body_checks.values()) >= 2

        if frontmatter_ok and body_passed:
            return ConstraintResult(
                passed=True,
                constraint_name="skill_structure",
                message="Skill has valid frontmatter (name + description) and substantive body",
            )

        missing = []
        if not has_frontmatter:
            missing.append("YAML frontmatter (---)")
        if not has_name:
            missing.append("name field")
        if not has_description:
            missing.append("description field")
        if not body_passed:
            failed_checks = [k for k, v in body_checks.items() if not v]
            missing.append(f"body lacks: {', '.join(failed_checks)}")

        return ConstraintResult(
            passed=False,
            constraint_name="skill_structure",
            message=f"Skill missing: {', '.join(missing)}",
        )

    def _check_cli_syntax(self, text: str) -> ConstraintResult:
        """Check that hermes CLI commands and config keys in the skill body are real.

        Hallucination failure mode: GEPA optimizes for keyword overlap against synthetic
        examples. The evolved skill may teach command structures that look plausible but
        contain fabricated config keys (e.g. 'hermes config set openrouter.model VALUE'
        when the actual config has 'OpenRouter' as an API-key section, not a config key
        namespace, and 'model' is the only top-level model key).

        This constraint:
        1. Parses the skill body for hermes CLI invocations in code blocks and inline text
        2. Extracts config key paths (including dot-notation like 'model.provider')
        3. Verifies each top-level key exists in live `hermes config show` output
        4. Catches fabricated namespaces (openrouter.*, anthropic.*, etc.) that don't exist
           as config key hierarchies
        """
        import re, subprocess

        # ── 1. Get valid top-level config keys from live hermes config show ──────
        config_show = subprocess.run(
            ['hermes', 'config', 'show'],
            capture_output=True, text=True, timeout=15,
        )
        valid_top_keys: set[str] = set()
        if config_show.returncode == 0:
            # Match lines like "  Model:        {...}" or "  Max turns:    150"
            # and section headers like "◆ API Keys"
            for m in re.finditer(r'^\s{2,}([a-z_][\w.]*):', config_show.stdout, re.MULTILINE):
                valid_top_keys.add(m.group(1).lower())
            for m in re.finditer(r'◆\s+([A-Z][A-Za-z\s/]+)', config_show.stdout, re.MULTILINE):
                section = m.group(1).strip().lower().replace(' ', '_').replace('/', '_')
                valid_top_keys.add(section)
            # Also add common aliases
            valid_top_keys.update({'model', 'provider', 'base_url', 'api_key',
                                   'max_turns', 'timeout', 'backend'})

        # ── 2. Parse hermes CLI commands from skill body ────────────────────────
        # Extract ALL hermes command lines from code blocks and narrative text
        all_lines = text.split('\n')
        cmd_lines = []
        in_code_block = False
        for line in all_lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            if 'hermes' in line.lower():
                cmd_lines.append(line.strip())

        # ── 3. Extract and validate config keys ─────────────────────────────────
        # Pattern: hermes ... set KEY VALUE (with optional quotes)
        key_val_pattern = re.compile(
            r'hermes\s+\w[^|]*\sset\s+([\w.]+)\s+["\']?([\w:/\-.]+)',
            re.IGNORECASE,
        )
        # Pattern: hermes ... set KEY (without value — just checking key existence)
        key_only_pattern = re.compile(
            r'hermes\s+\w[^|]*\sset\s+([\w.]+)(?:\s+["\']|$)',
            re.IGNORECASE,
        )

        failures: list[str] = []
        seen_failures: set[str] = set()

        for line in cmd_lines:
            # Extract config key paths from the line
            for m in key_val_pattern.finditer(line):
                key = m.group(1).lower()
                parts = key.split('.')
                top = parts[0]
                if valid_top_keys and top not in valid_top_keys:
                    if key not in seen_failures:
                        failures.append(
                            f"Skill body teaches non-existent config key '{key}' "
                            f"(line: {line[:80]!r})"
                        )
                        seen_failures.add(key)

        # ── 4. Validate subcommands exist ───────────────────────────────────────
        # Only flag subcommands that appear to be CLI invocations:
        # - In a code block (```bash, ```sh, ```)
        # - On a line that looks like a shell command (starts with $ or contains `hermes`)
        # - NOT narrative references like "hermes agent is..." or "hermes features"
        hermes_help = subprocess.run(
            ['hermes', '--help'],
            capture_output=True, text=True, timeout=10,
        )
        valid_subcommands: set[str] = set()
        if hermes_help.returncode == 0:
            m = re.search(r'\{([^}]+)\}', hermes_help.stdout)
            if m:
                valid_subcommands = {s.strip() for s in m.group(1).split(',')}

        in_code_block = False
        subcmd_pattern = re.compile(r'hermes\s+(\w+)', re.IGNORECASE)
        for line in all_lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            # Only treat as CLI invocation if:
            # (a) inside a code block, OR
            # (b) line looks like a command (starts with $ or has `hermes` as command position)
            is_code_context = in_code_block or line.strip().startswith('$')
            has_hermes_cmd = bool(re.search(r'\$?\s*hermes\s+(\w+)', line, re.IGNORECASE))
            if not (is_code_context and has_hermes_cmd):
                continue
            for m in subcmd_pattern.finditer(line):
                sub = m.group(1).lower()
                # These appear in narrative text about hermes, not as subcommands
                if sub in {'agent', 'features', 'capabilities', 'feature', 'tool',
                           'model', 'system', 'documentation', 'instructions', 'guide'}:
                    continue
                if sub not in ('config', 'set') and valid_subcommands and sub not in valid_subcommands:
                    key = f"subcmd:{sub}"
                    if key not in seen_failures:
                        failures.append(
                            f"Skill body teaches unknown hermes subcommand '{sub}'"
                        )
                        seen_failures.add(key)

        if failures:
            unique = list(dict.fromkeys(failures))[:5]
            return ConstraintResult(
                passed=False,
                constraint_name="cli_syntax",
                message=f"CLI hallucination risk: {'; '.join(unique)}",
                details="\n".join(unique),
            )

        return ConstraintResult(
            passed=True,
            constraint_name="cli_syntax",
            message="Skill CLI references are valid",
        )
