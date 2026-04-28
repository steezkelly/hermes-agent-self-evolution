"""Router Benchmark — validate failure-pattern thresholds with synthetic data.

Generates synthetic scenario results with KNOWN ground-truth patterns,
runs the EvolutionRouter, and reports precision/recall for each pattern.

Usage:
    python -m tests.core.router_benchmark
"""

import sys
import json
from pathlib import Path
from typing import Optional

# Add repo to path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from evolution.core.router import EvolutionRouter
from evolution.core.types import RouterDecision, ScenarioResult, EvolutionSnapshot


# ── Synthetic test generators ──────────────────────────────────────────────

def make_scenario(scenario_id: str, passed: bool, reason: str = "",
                  score: float = 0.0) -> ScenarioResult:
    return ScenarioResult(
        scenario_id=scenario_id,
        passed=passed,
        score=score,
        failure_reason=reason,
        output=f"score={score:.2f}",
    )


def generate_edge_case(n_hard: int = 8, n_easy: int = 2) -> list[ScenarioResult]:
    """80%+ hard/adversarial failures → should classify as edge_case."""
    results = []
    for i in range(n_hard):
        results.append(make_scenario(f"hard_{i}", False, "hard", score=0.2))
    for i in range(n_easy):
        results.append(make_scenario(f"easy_{i}", False, "easy", score=0.8))
    return results


def generate_coverage(dominant_category: str = "api_call",
                      n_dominant: int = 6, n_other: int = 2,
                      passed: int = 2) -> list[ScenarioResult]:
    """60%+ failures in a single category → should classify as coverage."""
    results = []
    for i in range(n_dominant):
        results.append(make_scenario(f"{dominant_category}_{i}", False,
                                     dominant_category, score=0.3))
    for i in range(n_other):
        other_cat = "formatting" if dominant_category != "formatting" else "auth"
        results.append(make_scenario(f"{other_cat}_{i}", False,
                                     other_cat, score=0.5))
    for i in range(passed):
        results.append(make_scenario(f"pass_{i}", True, "", score=1.0))
    return results


def generate_structural(prev_body: str, curr_body: str,
                        n_failures: int = 4) -> tuple[str, str, list[ScenarioResult]]:
    """3+ new conditionals + no holdout gain → should classify as structural."""
    results = []
    for i in range(n_failures):
        results.append(make_scenario(f"fail_{i}", False, "medium", score=0.5))
    results.append(make_scenario("pass_1", True, "", score=1.0))
    return prev_body, curr_body, results


def generate_noise(n_failures: int = 5, n_pass: int = 5) -> list[ScenarioResult]:
    """Failures are random across difficulties — no clear pattern."""
    results = []
    reasons = ["easy", "medium", "hard", "api_call", "auth"]
    for i in range(n_failures):
        results.append(make_scenario(f"fail_{i}", False, reasons[i % len(reasons)], score=0.4))
    for i in range(n_pass):
        results.append(make_scenario(f"pass_{i}", True, "", score=1.0))
    return results


def generate_all_pass(n: int = 10) -> list[ScenarioResult]:
    """All scenarios pass — should return extend with confidence=1.0."""
    return [make_scenario(f"pass_{i}", True, "", score=1.0) for i in range(n)]


def generate_mixed_signal(hard_ratio: float = 0.5, n: int = 10) -> list[ScenarioResult]:
    """Mixed failures — edge case ratio varies for threshold testing."""
    n_hard = int(n * hard_ratio)
    results = []
    for i in range(n_hard):
        results.append(make_scenario(f"hard_{i}", False, "hard", score=0.2))
    for i in range(n - n_hard):
        results.append(make_scenario(f"easy_{i}", False, "easy", score=0.8))
    return results


# ── Test cases ────────────────────────────────────────────────────────────

def test_edge_case_pattern():
    """80%+ hard/adversarial failures → fix, edge_case."""
    router = EvolutionRouter()
    results = generate_edge_case(8, 2)  # 80% hard
    decision = router.classify(results, results, [], remaining_budget=10)
    expected = "edge_case"
    actual = decision.failure_pattern
    ok = actual == expected
    print(f"  edge_case: {'PASS' if ok else 'FAIL'} (expected={expected}, got={actual}, conf={decision.confidence:.2f})")
    return ok


def test_coverage_pattern():
    """Failures in 2+ categories but 60%+ in one → extend, coverage."""
    router = EvolutionRouter()
    results = generate_coverage("api_call", 6, 2, 2)  # 6/8 = 75% api_call
    decision = router.classify(results, results, [], remaining_budget=10)
    expected = "coverage"
    actual = decision.failure_pattern
    ok = actual == expected
    print(f"  coverage:  {'PASS' if ok else 'FAIL'} (expected={expected}, got={actual}, conf={decision.confidence:.2f})")
    return ok


def test_structural_pattern():
    """3+ new conditionals → fix, structural."""
    router = EvolutionRouter()
    prev = "# Simple\nJust do X."
    curr = "# Complex\nif A: do X\nelif B: do Y\nelse: do Z\nwhen ready: finish"
    _, _, results = generate_structural(prev, curr, 4)

    history = [
        EvolutionSnapshot(1, prev, 0.6, "", "t1"),
    ]
    # skill_body=curr is NOT in history — 4 new conditionals detected
    decision = router.classify(curr, results, history, remaining_budget=10)
    expected = "structural"
    actual = decision.failure_pattern
    ok = actual == expected
    print(f"  structural: {'PASS' if ok else 'FAIL'} (expected={expected}, got={actual}, conf={decision.confidence:.2f})")
    return ok


def test_noise_pattern():
    """Random failures with no pattern → extend, noise."""
    router = EvolutionRouter()
    results = generate_noise(5, 5)
    history = [
        EvolutionSnapshot(1, "# A", 0.6, "", "t1"),
        EvolutionSnapshot(2, "# B", 0.6, "", "t2"),
    ]
    decision = router.classify("# B", results, history, remaining_budget=10)
    expected = "noise"
    actual = decision.failure_pattern
    ok = actual == expected
    print(f"  noise:     {'PASS' if ok else 'FAIL'} (expected={expected}, got={actual}, conf={decision.confidence:.2f})")
    return ok


def test_all_pass_high_confidence():
    """All pass → extend with confidence=1.0."""
    router = EvolutionRouter()
    results = generate_all_pass(10)
    decision = router.classify(results, results, [], remaining_budget=10)
    ok = decision.action == "extend" and decision.confidence == 1.0
    print(f"  all_pass:  {'PASS' if ok else 'FAIL'} (action={decision.action}, conf={decision.confidence:.1f})")
    return ok


def test_low_budget_default():
    """Almost out of budget → extend, noise with low confidence."""
    router = EvolutionRouter()
    results = generate_noise(3, 1)
    decision = router.classify(results, results, [], remaining_budget=1)
    ok = decision.action == "extend" and decision.failure_pattern == "noise" and decision.confidence <= 0.5
    print(f"  low_budget:{'PASS' if ok else 'FAIL'} (action={decision.action}, conf={decision.confidence:.2f}, budget=1)")
    return ok


def test_edge_case_ratio_sweep():
    """Test edge_case threshold sensitivity: varies hard_ratio 0.5-0.9."""
    router = EvolutionRouter()
    results = {}
    for hard_pct in [50, 60, 70, 80, 85, 90]:
        results_list = generate_mixed_signal(hard_ratio=hard_pct / 100, n=20)
        decision = router.classify(results_list, results_list, [], remaining_budget=10)
        results[hard_pct] = (decision.failure_pattern, decision.confidence)

    # Test that 80% is the threshold
    threshold_correct = (
        results[80][0] == "edge_case" and
        results[70][0] != "edge_case"
    )
    print(f"  edge_sweep:{'PASS' if threshold_correct else 'FAIL'} (threshold=80%)")
    for pct, (pattern, conf) in sorted(results.items()):
        marker = "← threshold" if pct == 80 else ""
        print(f"    {pct}% hard → {pattern} (conf={conf:.2f}) {marker}")
    return threshold_correct


def test_empty_results():
    """Empty benchmark → extend with low confidence."""
    router = EvolutionRouter()
    decision = router.classify("# Empty", [], [], remaining_budget=10)
    ok = decision.action == "extend" and decision.failure_pattern == "noise"
    print(f"  empty:     {'PASS' if ok else 'FAIL'} (action={decision.action}, pattern={decision.failure_pattern})")
    return ok


def test_no_evolution_history():
    """No history → skip structural check, fall through to noise."""
    router = EvolutionRouter()
    results = generate_noise(3, 2)
    decision = router.classify("# Skill", results, [], remaining_budget=5)
    ok = decision.action == "extend" and decision.failure_pattern == "noise"
    print(f"  no_hist:   {'PASS' if ok else 'FAIL'} (action={decision.action}, pattern={decision.failure_pattern})")
    return ok


def test_edge_case_zero_failures():
    """0 edge_case failures → edge_case check returns None."""
    router = EvolutionRouter()
    results = [make_scenario("fail_1", False, "api_error", score=0.3)]
    decision = router.classify(results, results, [], remaining_budget=10)
    ok = decision.failure_pattern != "edge_case"
    print(f"  zero_hard: {'PASS' if ok else 'FAIL'} (pattern={decision.failure_pattern})")
    return ok


def test_mixed_edge_and_coverage():
    """Edge case takes priority over coverage when both match."""
    router = EvolutionRouter()
    results = [
        make_scenario("hard_api", False, "hard", score=0.2),
        make_scenario("hard_fmt", False, "hard", score=0.2),
        make_scenario("hard_auth", False, "hard", score=0.2),
        make_scenario("hard_type", False, "hard", score=0.2),
        make_scenario("easy_api", False, "api_call", score=0.7),
    ]
    # 4/5 = 80% hard → edge_case
    # 3 categories → would also trigger coverage if checked first
    decision = router.classify(results, results, [], remaining_budget=10)
    ok = decision.failure_pattern == "edge_case"
    print(f"  mixed_prio:{'PASS' if ok else 'FAIL'} (expected=edge_case, got={decision.failure_pattern}, {decision.confidence:.2f})")
    return ok


# ── Runner ────────────────────────────────────────────────────────────────

def run_all():
    print("=" * 60)
    print("Router Benchmark — Threshold Validation Suite")
    print("=" * 60)

    tests = [
        ("Edge case pattern", test_edge_case_pattern),
        ("Coverage pattern", test_coverage_pattern),
        ("Structural pattern", test_structural_pattern),
        ("Noise pattern", test_noise_pattern),
        ("All pass high confidence", test_all_pass_high_confidence),
        ("Low budget default", test_low_budget_default),
        ("Edge case ratio sweep", test_edge_case_ratio_sweep),
        ("Empty results", test_empty_results),
        ("No evolution history", test_no_evolution_history),
        ("Zero hard failures", test_edge_case_zero_failures),
        ("Mixed edge+coverage priority", test_mixed_edge_and_coverage),
    ]

    passed = 0
    failed = 0
    print()
    for name, test_fn in tests:
        print(f"[{name}]")
        try:
            ok = test_fn()
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
