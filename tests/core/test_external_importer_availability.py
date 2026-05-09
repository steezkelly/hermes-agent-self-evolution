"""Tests for external importer source availability dry-runs."""

from evolution.core.external_importers import describe_source_availability


class AvailableImporter:
    @staticmethod
    def extract_messages():
        return [
            {"task_input": "first useful prompt"},
            {"task_input": "second useful prompt"},
        ]


class EmptyImporter:
    @staticmethod
    def extract_messages():
        return []


class ErrorImporter:
    @staticmethod
    def extract_messages():
        raise RuntimeError("history unreadable")


def test_describe_source_availability_reports_available_empty_and_errors():
    report = describe_source_availability(
        ["available", "empty", "error"],
        {
            "available": AvailableImporter,
            "empty": EmptyImporter,
            "error": ErrorImporter,
        },
    )

    assert report == {
        "available": {
            "available": True,
            "candidate_count": 2,
            "error": None,
        },
        "empty": {
            "available": False,
            "candidate_count": 0,
            "error": None,
        },
        "error": {
            "available": False,
            "candidate_count": 0,
            "error": "history unreadable",
        },
    }
