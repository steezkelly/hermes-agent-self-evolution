"""Pre-run Calibration — Phase 2 of the GEPA Observatory.

Calibration protocol (from GEPA v3 brief):
    1. Generate 20 test cases.
    2. Score them against the ORIGINAL skill body with Tier-1. Record distribution.
    3. Score the same 20 against a DELIBERATELY DEGRADED body (remove every 3rd paragraph).
    4. Degraded mean should be < 0.50 and Original mean should be > 0.80.
       If not, the judge prompt or model is insufficient. DO NOT START EVOLUTION.

Usage (post-Phase 2):
    from evolution.core.observatory.calibrator import CalibrationRunner

    runner = CalibrationRunner(logger)
    result = runner.run(skill_body=skill_text, tasks=generated_tasks)
    if result.is_acceptable():
        print("Calibration passed — start evolution")
    else:
        print(f"Calibration FAILED: {result.failures}")
        raise SystemExit("Fix judge before starting GEPA")
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol
from evolution.core.observatory.logger import JudgeAuditLogger, get_logger


@dataclass
class CalibrationResult:
    """Result of a calibration run."""
    n_tasks: int
    original_mean: float
    degraded_mean: float
    original_scores: list[float]
    degraded_scores: list[float]
    acceptable: bool
    failures: list[str] = field(default_factory=list)

    def is_acceptable(self) -> bool:
        return self.acceptable

    def format(self) -> str:
        lines = [
            "=" * 60,
            "CALIBRATION REPORT",
            "=" * 60,
            f"  Tasks: {self.n_tasks}",
            f"  Original mean:   {self.original_mean:.4f}  (should be > 0.80)",
            f"  Degraded mean:   {self.degraded_mean:.4f}  (should be < 0.50)",
            f"  Delta:           {self.original_mean - self.degraded_mean:.4f}  (should be > 0.30)",
            f"  Status:          {'✓ PASS' if self.acceptable else '✗ FAIL'}",
        ]
        if self.failures:
            lines.append("")
            lines.append("  Failures:")
            for f in self.failures:
                lines.append(f"    - {f}")
        lines.append("=" * 60)
        return "\n".join(lines)


class CalibrationRunner:
    """Run pre-evolution calibration to verify judge quality.

    Not yet integrated — stub for Phase 2 implementation.
    """

    def __init__(self, logger: Optional[JudgeAuditLogger] = None):
        self._logger = logger or get_logger()

    def run(
        self,
        skill_body: str,
        degraded_body: str,
        tasks: list[dict],
        model: str = "minimax/minimax-m2.7",
    ) -> CalibrationResult:
        """Run calibration: score tasks against original and degraded bodies.

        Parameters
        ----------
        skill_body : str
            The original, unaltered skill body.
        degraded_body : str
            Deliberately degraded version (e.g., remove every 3rd paragraph,
            replace specific steps with vague generalities).
        tasks : list of dict
            Each dict must have: task_input, expected_behavior.
        model : str
            Model to use for scoring.

        Returns
        -------
        CalibrationResult
        """
        failures: list[str] = []
        original_scores: list[float] = []
        degraded_scores: list[float] = []

        try:
            from evolution.core.fitness import LLMJudge
            from evolution.core.config import EvolutionConfig
            config = EvolutionConfig(judge_model=model)
            judge = LLMJudge(config)
        except Exception as exc:
            # Fall back to stub scores if judge can't be initialized
            return CalibrationResult(
                n_tasks=len(tasks),
                original_mean=0.0,
                degraded_mean=0.0,
                original_scores=[],
                degraded_scores=[],
                acceptable=False,
                failures=[f"Judge unavailable: {exc}"],
            )

        for task in tasks:
            task_input = task.get("task_input", "")
            expected = task.get("expected_behavior", "")
            try:
                # Generate agent response from original skill body
                agent_out = self._call_agent(skill_body, task_input, model=model)
                fs = judge.score(
                    task_input=task_input,
                    expected_behavior=expected,
                    agent_output=agent_out,
                    skill_text=skill_body,
                )
                original_scores.append(fs.correctness)
            except Exception as exc:
                failures.append(f"Original scoring failed for task: {exc}")
                original_scores.append(0.0)

            try:
                # Generate agent response from degraded skill body
                agent_out_deg = self._call_agent(degraded_body, task_input, model=model)
                fs_deg = judge.score(
                    task_input=task_input,
                    expected_behavior=expected,
                    agent_output=agent_out_deg,
                    skill_text=degraded_body,
                )
                degraded_scores.append(fs_deg.correctness)
            except Exception as exc:
                failures.append(f"Degraded scoring failed for task: {exc}")
                degraded_scores.append(0.0)

        import numpy as np
        original_mean = float(np.mean(original_scores)) if original_scores else 0.0
        degraded_mean = float(np.mean(degraded_scores)) if degraded_scores else 0.0

        if original_mean <= 0.80:
            failures.append(f"Original mean {original_mean:.3f} <= 0.80 — judge too harsh or tasks wrong")
        if degraded_mean >= 0.50:
            failures.append(f"Degraded mean {degraded_mean:.3f} >= 0.50 — judge too lenient")
        if original_mean - degraded_mean <= 0.30:
            failures.append(f"Delta {original_mean - degraded_mean:.3f} <= 0.30 — judge cannot discriminate")

        return CalibrationResult(
            n_tasks=len(tasks),
            original_mean=original_mean,
            degraded_mean=degraded_mean,
            original_scores=original_scores,
            degraded_scores=degraded_scores,
            acceptable=len(failures) == 0,
            failures=failures,
        )

    def _call_agent(self, skill_body: str, task_input: str, model: str) -> str:
        """Call the agent with the skill body as system instructions.

        Uses the SAME call pattern as fitness._invoke_skill_as_agent() so
        calibration scores match real evolution scores.
        """
        from evolution.core.fitness import _invoke_skill_as_agent
        return _invoke_skill_as_agent(skill_body, task_input)
