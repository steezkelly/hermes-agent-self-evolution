"""Tests for evolution.core.observatory.health

Covers: alert thresholds, sustained breach detection, empty data handling.
"""

import tempfile
from pathlib import Path

import pytest

from evolution.core.observatory.health import (
    JudgeHealthMonitor,
    HealthReport,
    Alert,
    ALERT_THRESHOLDS,
)
from evolution.core.observatory.logger import JudgeAuditLogger


@pytest.fixture
def tmp_monitor():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "health.db"
        logger = JudgeAuditLogger(db_path=db)
        monitor = JudgeHealthMonitor(logger)
        yield monitor, logger


class TestEmptyData:
    def test_empty_health_report(self, tmp_monitor):
        monitor, _ = tmp_monitor
        report = monitor.health_report(generations_since=0)
        assert report.generations == []
        assert report.total_calls == 0
        assert report.alerts == []
        assert report.mean_score is None
        assert report.std_score is None


class TestStdDevFlatAlert:
    def test_std_dev_flat_3_generations(self, tmp_monitor):
        monitor, logger = tmp_monitor
        # 3 generations, low variance scores → std_dev below 0.08
        for gen in [1, 2, 3]:
            for i in range(5):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=0.50 + (i * 0.01),  # very tight cluster
                )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "STD_DEV_FLAT" in codes

    def test_std_dev_flat_not_triggered_with_gap(self, tmp_monitor):
        monitor, logger = tmp_monitor
        # Generations 1,2 flat — gen 3 missing — gen 4 flat
        for gen in [1, 2, 4]:
            for i in range(5):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=0.50,
                )
        report = monitor.health_report(generations_since=0)
        # Not 3 consecutive
        codes = [a.code for a in report.alerts]
        assert "STD_DEV_FLAT" not in codes

    def test_std_dev_high_no_alert(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for gen in [1, 2, 3]:
            for i, s in enumerate([0.1, 0.5, 0.9]):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=s,
                )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "STD_DEV_FLAT" not in codes


class TestMeanCeilingAlert:
    def test_rubber_stamp_3_generations(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for gen in [1, 2, 3]:
            for i in range(5):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=0.95,
                )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "RUBBER_STAMP" in codes

    def test_rubber_stamp_not_triggered_with_gap(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for gen in [1, 2, 4]:
            for i in range(5):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=0.95,
                )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "RUBBER_STAMP" not in codes


class TestMeanFloorAlert:
    def test_overly_harsh_3_generations(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for gen in [1, 2, 3]:
            for i in range(5):
                logger.log(
                    generation=gen,
                    skill_name="test",
                    model_used="m",
                    task_id=f"g{gen}_t{i}",
                    expected_behavior="e",
                    actual_behavior="a",
                    rubric="r",
                    raw_score=0.10,
                )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "OVERLY_HARSH" in codes


class TestErrorRateAlert:
    def test_error_rate_alert(self, tmp_monitor):
        monitor, logger = tmp_monitor
        # 4 calls, 1 error → 25% > 0.5%
        for i in range(3):
            logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"ok{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.8,
            )
        logger.log_error(
            generation=1, skill_name="test", model_used="m", task_id="err",
            expected_behavior="e", rubric="r", error_flag="ValueError",
        )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "JUDGE_ERRORS" in codes

    def test_error_rate_no_alert(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for i in range(200):
            logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"ok{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.8,
            )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "JUDGE_ERRORS" not in codes


class TestDeadZoneAlert:
    def test_dead_zone_alert(self, tmp_monitor):
        monitor, logger = tmp_monitor
        # 90% in dead zones (>80% threshold)
        for i in range(90):
            logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"dz{i}",
                expected_behavior="e", actual_behavior="a", rubric="r",
                raw_score=0.01 if i % 2 == 0 else 0.99,
            )
        for i in range(10):
            logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"mid{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
            )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "DEAD_ZONE" in codes

    def test_dead_zone_no_alert(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for i in range(50):
            logger.log(
                generation=1, skill_name="test", model_used="m", task_id=f"mid{i}",
                expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.5,
            )
        report = monitor.health_report(generations_since=0)
        codes = [a.code for a in report.alerts]
        assert "DEAD_ZONE" not in codes


class TestHealthReportFormat:
    def test_format_includes_key_data(self, tmp_monitor):
        monitor, logger = tmp_monitor
        logger.log(
            generation=1, skill_name="test", model_used="m", task_id="t1",
            expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.8,
        )
        report = monitor.health_report(generations_since=0)
        text = report.format()
        assert "GEPA JUDGE HEALTH REPORT" in text
        assert "Total judge calls" in text
        assert "Mean score" in text
        assert "✓ No alerts" in text

    def test_format_with_alerts(self, tmp_monitor):
        monitor, logger = tmp_monitor
        for gen in [1, 2, 3]:
            for i in range(5):
                logger.log(
                    generation=gen, skill_name="test", model_used="m", task_id=f"g{gen}_t{i}",
                    expected_behavior="e", actual_behavior="a", rubric="r", raw_score=0.95,
                )
        report = monitor.health_report(generations_since=0)
        text = report.format()
        assert "ALERTS" in text
        assert "RUBBER_STAMP" in text


class TestAlertDataclass:
    def test_alert_fields(self):
        a = Alert(
            code="TEST",
            message="test message",
            generations_affected=[1, 2, 3],
            current_value=0.5,
            threshold=0.6,
            severity="warning",
        )
        assert a.severity == "warning"
        assert a.current_value == 0.5
