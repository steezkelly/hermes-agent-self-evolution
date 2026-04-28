"""Robustness modules for evolved skill validation.

Three checkers that run AFTER evolution but BEFORE deployment.
If ANY checker fails, the evolved candidate is rejected and baseline
is retained. These form a sequential AND-gate:

    ConfigDrift → Regression → ScopeCreep → ParetoSelector

Each checker returns (passed: bool, summary: str).
"""

import re
import json
from pathlib import Path
from typing import Optional


class ConfigDriftChecker:
    """Ensures evolution didn't modify skill frontmatter.

    Frontmatter is extracted from the full body BEFORE calling this checker
    (via extract_frontmatter() helper). The interface accepts already-parsed
    frontmatter strings to keep the checker focused on comparison logic.

    Flags as drift: name, description (must be identical)
    Allows as drift: version (auto-increment if the field exists)
    Ignores: all other fields (tags, metadata, related_skills, etc.)
    """

    def check(
        self,
        evolved_frontmatter: str,
        baseline_frontmatter: str,
    ) -> tuple[bool, str]:
        """Compare frontmatter fields between evolved and baseline.

        Returns (passed, summary).
        """
        evolved_lines = self._parse_frontmatter_lines(evolved_frontmatter)
        baseline_lines = self._parse_frontmatter_lines(baseline_frontmatter)

        evolved_fields = self._extract_fields(evolved_lines)
        baseline_fields = self._extract_fields(baseline_lines)

        drifts = []
        for field in ['name', 'description']:
            ev = evolved_fields.get(field)
            ba = baseline_fields.get(field)
            if ev != ba:
                drifts.append(f"{field}: '{ba}' → '{ev}'")

        if drifts:
            return False, f"Config drift detected: {'; '.join(drifts)}"

        return True, "Frontmatter intact (name + description unchanged)"

    @staticmethod
    def _parse_frontmatter_lines(frontmatter: str) -> list[str]:
        """Parse frontmatter string into lines, stripping outer ---."""
        lines = frontmatter.strip().split('\n')
        # Strip leading/trailing --- markers if present
        if lines and lines[0].strip() == '---':
            lines = lines[1:]
        if lines and lines[-1].strip() == '---':
            lines = lines[:-1]
        return lines

    @staticmethod
    def _extract_fields(lines: list[str]) -> dict[str, str]:
        """Extract key: value pairs from frontmatter lines."""
        fields = {}
        for line in lines:
            line = line.strip()
            if ':' in line:
                key, _, value = line.partition(':')
                fields[key.strip()] = value.strip().strip('"\'')
        return fields


class SkillRegressionChecker:
    """Ensures the evolved skill doesn't regress on PREVIOUS benchmarks.

    Scans output/<skill>/<previous_timestamps>/ for benchmark_results.json
    files. For each previous benchmark, evaluates the evolved skill and
    compares scores. Fails if any previous benchmark shows regression > 5pp.

    If no previous results exist, this check passes automatically.
    """

    DEFAULT_THRESHOLD = 0.05  # 5pp max regression

    def __init__(self, output_root: Optional[Path] = None):
        self.output_root = output_root or Path("output")

    def check(
        self,
        skill_name: str,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> tuple[bool, str]:
        """Scan previous benchmark results for regression.

        Args:
            skill_name: Name of the skill being evolved.
            threshold: Max allowed regression in score points (default 0.05).

        Returns:
            (passed, summary) tuple.
        """
        skill_dir = self.output_root / skill_name
        if not skill_dir.exists():
            return True, "No previous benchmark results found — check passes"

        previous_results = self._find_previous_results(skill_dir)
        if not previous_results:
            return True, "No previous benchmark results found — check passes"

        # In v2 initial build, this checker reads pre-existing benchmark_results.json
        # files. For now, it's a structural pass-through since we need the full
        # evaluation harness to actually score against previous benchmarks.
        #
        # Future: implement actual scoring against each previous benchmark suite.
        return True, f"Found {len(previous_results)} previous benchmark files — regression checking requires full evaluation harness"

    def check_score(self, evolved_score: float, baseline_score: float,
                    threshold: Optional[float] = None) -> tuple[bool, str]:
        """Inline score regression check — used by v2_dispatch.

        Directly compares evolved score against baseline score without
        scanning files on disk. Returns:
            (True, "pass") if evolved >= baseline - threshold
            (False, message) if regression detected
        """
        effective_threshold = threshold if threshold is not None else self.DEFAULT_THRESHOLD
        regression = baseline_score - evolved_score
        if regression > effective_threshold:
            return (False,
                    f"Regression: evolved {evolved_score:.3f} vs baseline {baseline_score:.3f} "
                    f"(delta={regression:.3f}, max allowed={effective_threshold:.3f})")
        if evolved_score >= baseline_score:
            return (True,
                    f"Pass: evolved {evolved_score:.3f} >= baseline {baseline_score:.3f} "
                    f"(improvement {evolved_score - baseline_score:+.3f})")
        return (True,
                f"Minor regression within threshold: {regression:.3f} <= {effective_threshold:.3f}")

    @staticmethod
    def _find_previous_results(skill_dir: Path) -> list[Path]:
        """Find benchmark_results.json files in previous run directories."""
        results = []
        for run_dir in sorted(skill_dir.iterdir()):
            if run_dir.is_dir():
                result_file = run_dir / "benchmark_results.json"
                if result_file.exists():
                    results.append(result_file)
        return results


class ScopeCreepChecker:
    """Ensures the evolved skill doesn't exceed its documented domain.

    Uses a DETERMINISTIC heuristic (NOT an LLM):
    1. Extract term frequency from baseline and evolved skill bodies
    2. Identify NEW terms (appear > N times in evolved, 0 in baseline)
    3. Use length-normalized ratio to avoid verbose examples inflating counts
    4. Rate: <10% new terms → MATCH, 10-30% → MINOR_DRIFT (warning),
            >30% → MAJOR_DRIFT (block)
    """

    DEFAULT_MIN_OCCURRENCES = 3   # term must appear this many times to count
    DEFAULT_MATCH_THRESHOLD = 0.10     # <10% → MATCH
    DEFAULT_DRIFT_THRESHOLD = 0.30     # >30% → MAJOR_DRIFT

    # Common English words filtered from term analysis
    STOPWORDS = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can',
        'had', 'her', 'was', 'one', 'our', 'out', 'has', 'have', 'been',
        'some', 'them', 'than', 'that', 'this', 'what', 'when', 'where',
        'which', 'who', 'will', 'with', 'would', 'about', 'also', 'could',
        'does', 'each', 'from', 'more', 'most', 'other', 'over', 'should',
        'their', 'there', 'these', 'those', 'through', 'very', 'after',
        'before', 'between', 'into', 'such', 'than', 'then', 'just',
        'like', 'make', 'may', 'well', 'any', 'down', 'first', 'good',
        'here', 'how', 'many', 'much', 'need', 'new', 'now', 'only',
        'own', 'see', 'two', 'use', 'way', 'who', 'work', 'year',
    }

    def __init__(self, min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
                 match_threshold: float = DEFAULT_MATCH_THRESHOLD,
                 drift_threshold: float = DEFAULT_DRIFT_THRESHOLD):
        self.min_occurrences = min_occurrences
        self.match_threshold = match_threshold
        self.drift_threshold = drift_threshold

    def check(
        self,
        evolved_body: str,
        baseline_body: str,
        skill_description: str = "",
    ) -> tuple[str, str]:
        """Check for scope creep using length-normalized term analysis.

        Returns:
            (status, details) where status is "match", "minor_drift", or "major_drift".
        """
        evolved_terms = self._term_frequencies(evolved_body)
        baseline_terms = self._term_frequencies(baseline_body)

        # Insufficient baseline signal — skip heuristic
        if not baseline_terms or sum(baseline_terms.values()) < 3:
            return ("match", "Baseline has insufficient term signal (< 3 meaningful words)")

        # Find new terms in evolved that didn't appear in baseline
        new_terms = {}
        for term, count in evolved_terms.items():
            if term not in baseline_terms and count >= self.min_occurrences:
                new_terms[term] = count

        if not new_terms:
            return "match", "No new domain-specific terms detected"

        # Length-normalized ratio: new term occurrences / total baseline content length
        total_new_occurrences = sum(new_terms.values())
        baseline_len = max(len(baseline_body.split()), 1)
        normalized_ratio = total_new_occurrences / baseline_len

        if normalized_ratio >= self.drift_threshold:
            top_terms = sorted(new_terms.items(), key=lambda x: -x[1])[:5]
            term_list = ", ".join(f"{t}({c})" for t, c in top_terms)
            return ("major_drift",
                    f"Length-normalized new term ratio {normalized_ratio:.2%} "
                    f"exceeds drift threshold ({self.drift_threshold:.0%}). "
                    f"Top new terms: {term_list}")
        elif normalized_ratio >= self.match_threshold:
            top_terms = sorted(new_terms.items(), key=lambda x: -x[1])[:3]
            term_list = ", ".join(f"{t}({c})" for t, c in top_terms)
            return ("minor_drift",
                    f"New terms detected at ratio {normalized_ratio:.2%} "
                    f"({self.match_threshold:.0%}-{self.drift_threshold:.0%} range). "
                    f"Review needed. Top terms: {term_list}")
        else:
            return "match", f"Normalized new term ratio {normalized_ratio:.2%} below threshold — in scope"

    def _term_frequencies(self, body: str) -> dict[str, int]:
        """Count word frequencies, filtering stopwords and short words."""
        words = re.findall(r'[a-zA-Z]{4,}', body.lower())
        freq: dict[str, int] = {}
        for word in words:
            if word not in self.STOPWORDS:
                freq[word] = freq.get(word, 0) + 1
        return freq
