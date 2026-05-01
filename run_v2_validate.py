#!/usr/bin/env python3
"""Unified GEPA v2.1 validation and evolution runner.

Consolidates 8 near-identical scripts (run_v2_validate_*.py, run_v2_evolution.py)
into a single parameterised entry point.

Usage:
    # Validate a skill
    python run_v2_validate.py --skill companion-interview-workflow --iterations 5

    # Evolve with a different model
    python run_v2_validate.py --skill ceo-orchestration --model nous/gpt-5.4-nano --eval-model nous/gpt-5.4-nano --mode evolve

    # Quick check (1 iteration, synthetic data)
    python run_v2_validate.py --skill hermes-agent --iterations 1 --eval-source synthetic

    # List known skills with v1 records
    python run_v2_validate.py --list
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from evolution.core.gepa_v2_dispatch import v2_dispatch
from evolution.core.types import EvolutionReport

# Known skill records (v1 best deltas for reference)
SKILL_RECORDS = {
    "ceo-orchestration":              {"v1_best": 0.0968, "eval_source": "sessiondb", "note": "Strongest v1 signal"},
    "companion-interview-pipeline":    {"v1_best": 0.0,    "eval_source": "golden",   "note": "No v1 improvement"},
    "companion-interview-workflow":    {"v1_best": 0.0177, "eval_source": "golden",   "note": "Moderate v1 signal"},
    "companion-memory":               {"v1_best": 0.0,    "eval_source": "synthetic","note": "No v1 improvement"},
    "companion-memory-tiers":         {"v1_best": 0.129,  "eval_source": "golden",   "note": "Strong v1 signal"},
    "companion-personas":             {"v1_best": 0.0,    "eval_source": "golden",   "note": "No v1 improvement"},
    "companion-roundtable":           {"v1_best": 0.0059, "eval_source": "golden",   "note": "Tiny v1 signal"},
    "companion-safety":               {"v1_best": 0.0,    "eval_source": "golden",   "note": "No v1 improvement"},
    "companion-system-orchestration": {"v1_best": 0.0418, "eval_source": "synthetic","note": "Moderate v1 signal"},
    "companion-workflows":            {"v1_best": 0.125,  "eval_source": "golden",   "note": "Known false positive (type change)"},
    "hermes-agent":                   {"v1_best": 0.1348, "eval_source": "synthetic","note": "Plateaued after 14 runs"},
    "mnemosyne-maintenance":          {"v1_best": 0.0,    "eval_source": "golden",   "note": "No v1 improvement"},
    "mnemosyne-self-evolution-tools": {"v1_best": 0.0717, "eval_source": "golden",   "note": "Strong v1 signal (1 run)"},
    "systematic-debugging":           {"v1_best": 0.0038, "eval_source": "synthetic","note": "Tiny v1 signal"},
}


def list_skills():
    print(f"{'Skill':40s} {'v1 Best':>8s} {'Source':12s} Note")
    print("-" * 80)
    for name, rec in sorted(SKILL_RECORDS.items()):
        delta = f"{rec['v1_best']:+.4f}" if rec['v1_best'] else " 0.0  "
        print(f"{name:40s} {delta:>8s} {rec['eval_source']:12s} {rec['note']}")


def resolve_model(model_arg: str, env_fallback: str = "minimax/minimax-m2.7") -> str:
    """Resolve a model string, applying the convention shortener."""
    if model_arg:
        return model_arg
    return env_fallback


def main():
    parser = argparse.ArgumentParser(
        description="Unified GEPA v2.1 validation and evolution runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--skill", type=str, help="Skill name to validate/evolve")
    parser.add_argument("--list", action="store_true", help="List known skills with v1 records")
    parser.add_argument("--iterations", type=int, default=5, help="GEPA iterations (default: 5)")
    parser.add_argument("--model", type=str, default="minimax/minimax-m2.7", help="Optimizer model (default: minimax/minimax-m2.7)")
    parser.add_argument("--eval-model", type=str, default=None, help="Eval model (default: same as --model)")
    parser.add_argument("--eval-source", type=str, choices=["synthetic", "golden", "sessiondb"], default=None,
                        help="Eval source override (default: from SKILL_RECORDS or 'synthetic')")
    parser.add_argument("--dataset-path", type=str, default=None, help="Path to existing eval dataset (JSONL)")
    parser.add_argument("--mode", type=str, choices=["validate", "evolve"], default="validate",
                        help="'validate' (default) runs v2_dispatch; 'evolve' calls evolve_skill --v2")
    parser.add_argument("--dry-run", action="store_true", help="Validate setup without running optimization")
    parser.add_argument("--run-tests", action="store_true", help="Run full pytest suite as constraint gate")
    parser.add_argument("--stats-csv", type=str, default=None, help="Append run stats to CSV for analysis")

    args = parser.parse_args()

    if args.list:
        list_skills()
        return

    if not args.skill:
        parser.error("--skill is required (or use --list)")

    # Resolve defaults from records
    record = SKILL_RECORDS.get(args.skill, {})
    eval_source = args.eval_source or record.get("eval_source", "synthetic")
    v1_best = record.get("v1_best", None)
    eval_model = args.eval_model or args.model

    # Banner
    print("=" * 60)
    label = "Evolution" if args.mode == "evolve" else "Validation"
    print(f"  GEPA v2.1 {label} Run")
    print(f"  Skill: {args.skill}" + (f" (v1 best: {v1_best:+.4f})" if v1_best else ""))
    print(f"  Mode: {args.mode}")
    print(f"  Iterations: {args.iterations}")
    print(f"  Eval source: {eval_source}")
    print(f"  Optimizer: {args.model}")
    print(f"  Eval: {eval_model}")
    if args.dataset_path:
        print(f"  Dataset: {args.dataset_path}")
    if args.dry_run:
        print(f"  [DRY RUN]")
    print("=" * 60)
    print()

    start = time.time()

    if args.mode == "evolve":
        # Run full evolution via evolve_skill CLI
        import subprocess
        cmd = [
            sys.executable, "-m", "evolution.skills.evolve_skill",
            "--skill", args.skill,
            "--v2",
            "--iterations", str(args.iterations),
            "--optimizer-model", args.model,
            "--eval-model", eval_model,
        ]
        if args.eval_source:
            cmd += ["--eval-source", eval_source]
        if args.dry_run:
            cmd += ["--dry-run"]
        if args.stats_csv:
            cmd += ["--stats-csv", args.stats_csv]
        result = subprocess.run(cmd, cwd=Path(__file__).parent)
        elapsed = time.time() - start
        print()
        print(f"  {'=' * 50}")
        print(f"  COMPLETE — {elapsed:.0f}s elapsed")
        print(f"  Exit code: {result.returncode}")
        print(f"  {'=' * 50}")
        return

    # Validate mode: run v2_dispatch directly
    report: EvolutionReport = v2_dispatch(
        skill_name=args.skill,
        iterations=args.iterations,
        eval_source=eval_source,
        dataset_path=args.dataset_path,
        optimizer_model=args.model,
        eval_model=eval_model,
        run_tests=args.run_tests,
        dry_run=args.dry_run,
    )
    elapsed = time.time() - start

    print()
    print(f"  {'=' * 60}")
    print(f"  COMPLETE — {elapsed:.0f}s elapsed")
    print(f"  Skill: {report.skill_name}")
    print(f"  Recommendation: {report.recommendation}")
    print(f"  Improvement: {report.improvement:+.4f}")
    print(f"  Router: {report.router_decision.action} ({report.router_decision.failure_pattern})")
    if hasattr(report.router_decision, 'confidence'):
        print(f"  Router confidence: {report.router_decision.confidence:.1%}")
    print(f"  Details: {report.details}")
    print(f"  {'=' * 60}")

    # Interpretation
    print()
    print("  INTERPRETATION:")
    threshold = 0.03
    if report.recommendation == "deploy":
        print(f"  PASS: v2 accepted and recommends deploy (improvement > {threshold})")
    elif report.recommendation == "review":
        print(f"  PARTIAL: v2 assigned 'review' (improvement positive but below {threshold} threshold)")
        print(f"  Check details for which constraint(s) triggered warnings")
    elif report.recommendation == "reject":
        if report.improvement < 0:
            print(f"  GEPA generated a worse solution — rejection is correct behavior")
        elif v1_best and report.improvement > v1_best * 0.5:
            print(f"  CONCERN: v2 rejected despite meaningful improvement (>{v1_best*0.5:.4f}).")
            print(f"  This suggests over-rejection by constraints.")
        elif report.improvement > 0:
            print(f"  BORDERLINE: improvement positive but small ({report.improvement:+.4f})")
            print(f"  Below noise-floor level. Rejection may be reasonable.")
        else:
            print(f"  GEPA produced no improvement this run.")
            print(f"  GEPA is non-deterministic — multiple runs may tell a different story")


if __name__ == "__main__":
    main()
