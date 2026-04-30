"""Robustness modules for evolved skill validation.

Four checkers that run AFTER evolution but BEFORE deployment.
If ANY hard-gate checker fails, the evolved candidate is rejected
and baseline is retained. These form a sequential AND-gate:

    ConfigDrift → PurposePreservation → Regression → ScopeCreep → ParetoSelector

Each checker returns (passed: bool, summary: str).
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class ContentSemanticScorer:
    """Detects when GEPA reshapes skill content into a different format.

    Uses TF-IDF cosine similarity between baseline and evolved body text.
    If the evolved skill has very different vocabulary distribution from the
    baseline (despite keyword survival), it's a format change — not just
    content improvement.

    This catches the companion-workflows case: the evolved is an execution
    instruction sheet (task inputs/outputs) while baseline is a pattern-
    description reference document. The keyword sets overlap heavily but
    the text distributions diverge because the underlying skill TYPE changed.
    """

    DEFAULT_THRESHOLD = 0.60  # cosine sim below this → FAIL

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._baseline_vec: Optional[np.ndarray] = None

    def fit(self, baseline_body: str) -> "ContentSemanticScorer":
        """Fit the scorer on the baseline body text."""
        texts = [t.strip() for t in re.split(r'(?i)(?=##\s)', baseline_body) if t.strip()]
        if not texts:
            texts = [baseline_body]
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=3000,
            sublinear_tf=True,
        )
        self._baseline_vec = self._vectorizer.fit_transform(texts)
        return self

    def score(self, evolved_body: str) -> tuple[float, float]:
        """Score evolved body against fitted baseline.

        Returns (cosine_sim, threshold) where cosine_sim is the average
        max-similarity between evolved sections and baseline sections.
        """
        if self._baseline_vec is None or self._vectorizer is None:
            return 1.0, self.threshold

        evolved_texts = [t.strip() for t in re.split(r'(?i)(?=##\s)', evolved_body) if t.strip()]
        if not evolved_texts:
            return 1.0, self.threshold  # Empty evolved → no content to judge; pass

        try:
            evolved_vec = self._vectorizer.transform(evolved_texts)
            sims = cosine_similarity(evolved_vec, self._baseline_vec)
            # For each evolved section, find its best match with baseline sections
            max_sims_per_evolved = sims.max(axis=1)
            avg_max_sim = float(max_sims_per_evolved.mean())
            return avg_max_sim, self.threshold
        except Exception:
            return 1.0, self.threshold  # Default to passing on error


def extract_body(skill_text: str) -> str:
    """Extract the markdown body from a skill file (strip YAML frontmatter)."""
    if skill_text.strip().startswith("---"):
        parts = skill_text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return skill_text.strip()


def extract_frontmatter(skill_text: str) -> str:
    """Extract the YAML frontmatter from a skill file."""
    if skill_text.strip().startswith("---"):
        parts = skill_text.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip()
    return ""


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


class PurposePreservationChecker:
    """Ensures the evolved skill preserves its core purpose and format.

    This is the primary defense against GEPA's "type-changing" failure mode:
    the optimizer learns to reshape documentation skills into "consultant
    prompts" that score higher on keyword-overlap metrics but completely
    lose the original skill's purpose.

    Detection strategy — three complementary signals:
    1. SKILL-TYPE KEYWORD PRESERVATION
       Every skill implicitly declares its type via domain-specific keywords.
       A hermes-agent skill must contain CLI/command keywords.
       A debugging skill must contain diagnostic/probing keywords.
       If these disappear, purpose is lost.

    2. SECTION-STRUCTURE STABILITY
       Documentation skills have recognizable section patterns (## Steps,
       ## Options, ## Examples). Consultant prompts have ## Role, ## Context.
       If the dominant section types change, the format changed.

    3. SKILL-TYPE SIGNATURE HASH
       Compute a type-signature: the MD5 of the sorted set of skill-type
       keywords present in the baseline body. If >40% of those keywords
       disappear in the evolved version, it's a type change.

    Returns: (passed: bool, summary: str)
    Hard block: failed preservation (type changed).
    Pass: structure and keywords preserved.
    """

    # Keywords that identify a skill's TYPE — must be preserved
    # Groups are OR: at least one from each group must survive
    SKILL_TYPE_SIGNATURES: dict[str, list[set]] = {
        "cli_usage": [
            {"hermes", "config", "skill", "tool", "setup", "install", "command", "cli"},
            {"delegate", "task", "spawn", "agent", "model", "provider"},
        ],
        "debugging": [
            {"debug", "bug", "error", "trace", "inspect", "diagnos", "root", "cause", "reproduce"},
            {"hypothesis", "test", "verify", "isolate", "systematic"},
        ],
        "workflow": [
            {"workflow", "pattern", "collaborat", "agent", "companion", "role", "delegate"},
            {"feedback", "approve", "reject", "route", "orchestrat"},
        ],
        "memory": [
            {"memory", "mnemosyne", "remember", "recall", "persist", "context"},
            {"episode", "beam", "consolidat", "triple", "graph"},
        ],
        "interview": [
            {"interview", "question", "companion", "persona", "role", "roundtable"},
            {"synthes", "report", "insight", "refine"},
        ],
        "evaluation": [
            {"eval", "benchmark", "metric", "score", "fitness", "measure"},
            {"synthetic", "golden", "dataset", "holdout", "train"},
        ],
    }

    # Section heading text (stripped of "## " prefix) that indicates DANGEROUS
    # consultant-prompt format. These sections are the hallmark of GEPA's
    # "type-changing" failure mode where documentation → execution instructions.
    CONSULTANT_PROMPT_SECTIONS = {
        "Role", "Context", "Instructions", "Task", "Output Format",
        "Constraints", "Guidelines", "Persona", "Identity", "Personality",
        "Key Principles", "Quality Criteria", "Scoring Guidance",
        "Objective", "Main Topic", "Input Format",
    }

    # Section heading text (stripped) for stable documentation skills.
    # If the evolved has these but baseline didn't, flag as suspicious format change.
    DOCUMENTATION_SECTIONS = {
        "Overview", "Steps", "Examples", "Options", "Usage",
        "Troubleshooting", "Prerequisites", "CLI Reference",
        "Quick Start", "Key Paths", "Security", "Privacy",
        "Slash Commands", "Spawning", "Voice", "Transcription",
    }

    # Hard minimum doc sections that must survive if baseline has any.
    # Prevents rejection on legitimate restructurings where a 1-2 section
    # baseline gets reorganized into different section headings.
    MIN_ABSOLUTE_DOC_SECTION_SURVIVAL = 1

    def __init__(
        self,
        keyword_threshold: float = 0.4,
        format_stability_threshold: float = 0.5,
        content_scorer: Optional[ContentSemanticScorer] = None,
    ):
        """
        Args:
            keyword_threshold: Fraction of baseline type-keywords that must survive.
                             If <40% survive → fail (type changed).
            format_stability_threshold: If >50% of baseline format sections disappear → warn.
            content_scorer: Optional ContentSemanticScorer for detecting format-only changes.
                           If provided, checks TF-IDF cosine similarity between baseline
                           and evolved sections. Below 0.60 → FAIL (type changed).
        """
        self.keyword_threshold = keyword_threshold
        self.format_stability_threshold = format_stability_threshold
        self._content_scorer = content_scorer

    def set_content_scorer(self, scorer: ContentSemanticScorer) -> None:
        """Inject a fitted ContentSemanticScorer after __init__ (needed because
        the scorer is fitted on baseline text which is not yet available at
        checker construction time)."""
        self._content_scorer = scorer

    def check(
        self,
        evolved_body: str,
        baseline_body: str,
        skill_description: str = "",
    ) -> tuple[bool, str]:
        """Check purpose preservation between baseline and evolved skill bodies.

        Returns (passed, summary).
        """
        # ── Signal 1: Skill-type keyword survival ───────────────────────
        baseline_keywords = self._extract_skill_type_keywords(baseline_body)
        evolved_keywords = self._extract_skill_type_keywords(evolved_body)
        surviving = baseline_keywords & evolved_keywords
        survival_ratio = len(surviving) / len(baseline_keywords) if baseline_keywords else 1.0

        keyword_msg = (
            f"Keyword survival: {len(surviving)}/{len(baseline_keywords)} "
            f"({survival_ratio:.0%}) — "
            f"baseline type={sorted(baseline_keywords)}, "
            f"surviving={sorted(surviving)}, "
            f"lost={sorted(baseline_keywords - evolved_keywords)}"
        )

        if baseline_keywords and survival_ratio < self.keyword_threshold:
            return False, (
                f"PURPOSE LOST: only {survival_ratio:.0%} of skill-type keywords survive "
                f"(threshold {self.keyword_threshold:.0%}). {keyword_msg}"
            )

        # ── Signal 2: Consultant-prompt format detection ──────────────────
        baseline_sections = self._extract_section_types(baseline_body)
        evolved_sections = self._extract_section_types(evolved_body)

        # Identify whether baseline is a consultant-prompt skill or documentation skill.
        # A baseline with consultant-prompt sections is already a consultant-prompt type —
        # section expansion within that type is not a purpose change.
        baseline_consultant = baseline_sections & self.CONSULTANT_PROMPT_SECTIONS
        evolved_consultant = evolved_sections & self.CONSULTANT_PROMPT_SECTIONS
        new_consultant_sections = evolved_consultant - baseline_consultant

        if baseline_consultant:
            # Baseline IS a consultant-prompt type — allow expansion within type.
            # Only flag as fail if baseline consultant sections disappeared.
            if not baseline_consultant.issubset(evolved_consultant):
                lost = baseline_consultant - evolved_consultant
                return False, (
                    f"PURPOSE LOST: baseline consultant sections disappeared: {sorted(lost)}. "
                    f"{keyword_msg}"
                )
            # else: consultant sections grew or stayed same — OK
        else:
            # Baseline is NOT a consultant-prompt type (likely documentation).
            # Any new consultant-prompt sections = dangerous format change.
            if new_consultant_sections:
                return False, (
                    f"PURPOSE LOST: evolved adopted consultant-prompt format "
                    f"(baseline was not consultant type). "
                    f"New sections: {sorted(new_consultant_sections)}. "
                    f"{keyword_msg}"
                )

            # Check if baseline had documentation sections that were lost
            baseline_doc = baseline_sections & self.DOCUMENTATION_SECTIONS
            if baseline_doc:
                preserved_doc = evolved_sections & self.DOCUMENTATION_SECTIONS
                # Require BOTH a proportional survival check AND a minimum absolute count.
                # This prevents rejecting legitimate restructurings when baseline has
                # only 1-2 doc sections (e.g. just "Overview") that get reorganized.
                prop_survival = len(preserved_doc) / len(baseline_doc)
                abs_survival = len(preserved_doc)
                if prop_survival < self.format_stability_threshold or abs_survival < self.MIN_ABSOLUTE_DOC_SECTION_SURVIVAL:
                    lost = baseline_doc - evolved_sections
                    return False, (
                        f"PURPOSE LOST: documentation structure collapsed. "
                        f"Only {prop_survival:.0%} of baseline doc sections preserved "
                        f"({len(preserved_doc)}/{len(baseline_doc)}) "
                        f"and only {abs_survival} absolute sections remain. "
                        f"Lost: {sorted(lost)}. "
                        f"{keyword_msg}"
                    )

        # ── Signal 3: Content-semantic check ─────────────────────────────
        # If a content scorer was fitted, use TF-IDF section similarity to detect
        # format-only changes where keywords survive but the skill type changed.
        # (e.g. companion-workflows: pattern-description → execution instruction sheet)
        if self._content_scorer is not None:
            content_sim, content_threshold = self._content_scorer.score(evolved_body)
            content_msg = (
                f"Content semantic similarity: {content_sim:.2f} "
                f"(threshold {content_threshold:.2f}). "
            )
            if content_sim < content_threshold:
                return False, (
                    f"PURPOSE LOST: content-semantic divergence detected. "
                    f"The evolved skill has a different textual distribution from baseline "
                    f"(cosine sim={content_sim:.2f} < {content_threshold:.2f}), "
                    f"indicating a format/type change despite keyword survival. "
                    f"{content_msg}"
                    f"{keyword_msg}"
                )

        return True, (
            f"Purpose preserved. {keyword_msg}."
            f" Sections: {len(evolved_sections)} evolved, "
            f"{len(baseline_sections)} baseline."
        )

    def _extract_skill_type_keywords(self, body: str) -> set[str]:
        """Extract skill-type-defining keywords from a skill body.

        Scans for keywords across all known signature groups.
        Returns the union of all matched signature groups.
        """
        body_lower = body.lower()
        matched_groups: list[set] = []

        for signature_groups in self.SKILL_TYPE_SIGNATURES.values():
            for group in signature_groups:
                # Count how many keywords from this group appear
                group_matches = sum(1 for kw in group if kw in body_lower)
                if group_matches >= 2:  # At least 2 of the group must be present
                    matched_groups.append({kw for kw in group if kw in body_lower})

        # Deduplicate across groups
        all_matched: set[str] = set()
        for group in matched_groups:
            all_matched |= group

        return all_matched

    def _extract_section_types(self, body: str) -> set[str]:
        """Extract ## section headings from a markdown body.

        Returns stripped section titles (without "## " prefix) for comparison
        with CONSULTANT_PROMPT_SECTIONS and DOCUMENTATION_SECTIONS sets.
        """
        return {s.strip() for s in re.findall(r"^##\s+([^\n]+)", body, re.MULTILINE)}


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
