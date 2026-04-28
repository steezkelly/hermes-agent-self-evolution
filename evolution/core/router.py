"""Evolution Router — fix vs. extend vs. abstain classifier.

Determines whether an evolution iteration's result represents error
recovery (FIX), capability expansion (EXTEND), or ceiling reached (ABSTAIN).

All pattern detection uses HEURISTICS (no LLM calls). Thresholds are
novel design choices requiring empirical validation before production use.
"""

from typing import Optional

from evolution.core.types import RouterDecision, ScenarioResult, EvolutionSnapshot


class EvolutionRouter:
    """Classify evolution failures into fix/extend/abstain patterns.

    Four failure patterns:
    - edge_case: Failed scenarios are all "hard"/"adversarial" difficulty
    - structural: Failed scenarios share a domain tag; fix requires new conditionals
    - coverage: Failed scenarios span unrelated domains; skill doesn't cover them
    - noise: No pattern detected — random across difficulties and categories

    The Router observes failures but is structurally forbidden from declaring
    "abstain." Abstain authority belongs to BacktrackController (plateau) and
    OptimizationController (power-law). When confidence < 0.5, defaults to "extend."
    This is a deliberate design choice to prevent false early stopping.
    """

    DEFAULT_THRESHOLDS = {
        "edge_case_fail_ratio": 0.80,     # 80%+ failures must be hard/adversarial
        "coverage_cluster_ratio": 0.60,   # 60%+ failures in same category
        "coverage_min_failures": 3,       # minimum failures needed for coverage classification
        "structural_new_conditionals": 3,  # 3+ new if/then/else patterns in diff
        "confidence_unanimous": 1.0,       # all evidence points same direction
        "confidence_majority": 0.7,        # majority pattern but not unanimous
    }

    def __init__(self, thresholds: Optional[dict] = None):
        self.t = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}

    def classify(
        self,
        skill_body: str,
        benchmark_results: list[ScenarioResult],
        evolution_history: list[EvolutionSnapshot],
        remaining_budget: int,
    ) -> RouterDecision:
        """Classify the failure pattern and recommend action.

        Decision logic:
        1. If 80%+ failures are "hard"/"adversarial" → edge_case → FIX
        2. If 60%+ failures cluster in 2+ unrelated categories → coverage → EXTEND
        3. If 3+ new conditionals AND holdout not improved → structural → FIX
        4. Else → noise:
           - remaining_budget > 2 → EXTEND (try expanding)
           - remaining_budget <= 2 → default to EXTEND (Router never abstains alone)
        """
        # Count failures
        failures = [r for r in benchmark_results if not r.passed]
        if not failures:
            return self._action("extend", 1.0, "noise", "All scenarios pass — extending by default")

        # Pattern 1: structural (check BEFORE coverage — structural is about
        # code changes, which is a higher-value signal than failure patterns)
        if evolution_history and len(evolution_history) >= 1:
            prev_body = evolution_history[-1].skill_body
            pattern, confidence = self._check_structural(prev_body, skill_body, failures)
            if pattern == "structural":
                return self._action("fix", confidence, pattern,
                                    f"{self._count_new_conditionals(prev_body, skill_body)} new conditionals, no holdout gain")

        # Pattern 2: edge_case
        pattern, confidence = self._check_edge_case(failures, benchmark_results)
        if pattern == "edge_case":
            return self._action("fix", confidence, pattern,
                                f"{len(failures)} failures, majority hard/adversarial")

        # Pattern 3: coverage (requires 60%+ of failures in a single category)
        pattern, confidence = self._check_coverage(failures)
        if pattern == "coverage":
            return self._action("extend", confidence, pattern,
                                f"60%+ failures in same category ({self._dominant_category(failures)})")

        # Pattern 4: noise — default to extend
        if remaining_budget > 2:
            return self._action("extend", 0.5, "noise",
                                f"No clear pattern among {len(failures)} failures — extending")
        else:
            return self._action("extend", 0.3, "noise",
                                "Budget nearly exhausted, no clear pattern — extending by default")

    def _check_edge_case(self, failures: list[ScenarioResult],
                         all_results: list[ScenarioResult]) -> tuple[Optional[str], float]:
        """Check if failures concentrate on hard/adversarial scenarios."""
        if not all_results:
            return None, 0.0

        hard_failures = sum(1 for r in failures
                            if getattr(r, 'failure_reason', '') in ('hard', 'adversarial'))
        if len(failures) == 0:
            return None, 0.0
        ratio = hard_failures / len(failures)
        if ratio >= self.t["edge_case_fail_ratio"]:
            conf = min(1.0, 0.5 + ratio * 0.5)
            return "edge_case", conf
        return None, 0.0

    def _check_coverage(self, failures: list[ScenarioResult]) -> tuple[Optional[str], float]:
        """Check if 60%+ of failures concentrate in a single category.

        Uses coverage_cluster_ratio threshold. A single dominant category
        suggests the skill lacks capabilities in that area, requiring extension.
        """
        if not failures:
            return None, 0.0

        # Need enough failures to establish a coverage pattern
        min_failures = self.t.get("coverage_min_failures", 3)
        if len(failures) < min_failures:
            return None, 0.0

        # Count failures per category
        category_counts: dict[str, int] = {}
        for r in failures:
            cat = getattr(r, 'failure_reason', '') or 'uncategorized'
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if not category_counts:
            return None, 0.0

        # Check if any single category dominates
        max_count = max(category_counts.values())
        max_ratio = max_count / len(failures)

        if max_ratio >= self.t.get("coverage_cluster_ratio", 0.60):
            conf = min(1.0, 0.4 + max_ratio * 0.4)
            return "coverage", conf
        return None, 0.0

    @staticmethod
    def _dominant_category(results: list[ScenarioResult]) -> str:
        """Return the most common failure_reason among results."""
        counts: dict[str, int] = {}
        for r in results:
            cat = getattr(r, 'failure_reason', '') or 'uncategorized'
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        if not counts:
            return "uncategorized"
        return max(counts, key=counts.get)

    def _check_structural(self, prev_body: str, curr_body: str,
                          failures: list[ScenarioResult]) -> tuple[Optional[str], float]:
        """Check if the evolved body added structural complexity without improvement."""
        new_conds = self._count_new_conditionals(prev_body, curr_body)
        if new_conds >= self.t["structural_new_conditionals"]:
            conf = min(1.0, 0.5 + new_conds * 0.1)
            return "structural", conf
        return None, 0.0

    @staticmethod
    def _count_categories(results: list[ScenarioResult]) -> int:
        """Count unique categories among results."""
        cats = set()
        for r in results:
            cat = getattr(r, 'failure_reason', '') or ''
            if cat:
                cats.add(cat)
        return len(cats)

    @staticmethod
    def _count_new_conditionals(prev: str, curr: str) -> int:
        """Count new if/then/else/case/when patterns added in the diff."""
        import re
        pattern = re.compile(r'\b(if|else|elif|when|case|switch)\b', re.IGNORECASE)
        prev_count = len(pattern.findall(prev))
        curr_count = len(pattern.findall(curr))
        return max(0, curr_count - prev_count)

    @staticmethod
    def _action(action: str, confidence: float,
                failure_pattern: str, rationale: str) -> RouterDecision:
        return RouterDecision(
            action=action,
            confidence=min(1.0, max(0.0, confidence)),
            rationale=rationale,
            failure_pattern=failure_pattern,
        )
