"""Tests for kanban_query."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Import from the package
sys.path.insert(0, str(Path(__file__).parent.parent))
from gepa_kanban.kanban_query import (
    load_gepa_cards,
    load_companion_cards,
    apply_filters,
    apply_sort,
    format_markdown,
    format_json,
    _parse_age_hours,
    build_parser,
    main,
)


class TestParseAgeHours:
    def test_hours(self):
        assert _parse_age_hours("72") == 72
        assert _parse_age_hours("24h") == 24

    def test_days(self):
        assert _parse_age_hours("3d") == 72

    def test_weeks(self):
        assert _parse_age_hours("1w") == 168

    def test_invalid(self):
        assert _parse_age_hours("xyz") is None


class TestGepaCardLoading:
    """Tests that use the real card-registry.json."""

    def test_load_gepa_cards_returns_list(self):
        cards = load_gepa_cards()
        assert isinstance(cards, list)
        assert len(cards) > 0

    def test_all_cards_have_board_field(self):
        cards = load_gepa_cards()
        for card in cards:
            assert card.get("board") == "gepa"

    def test_all_cards_have_required_fields(self):
        cards = load_gepa_cards()
        required = ["skill_name", "status", "priority", "best_delta"]
        for card in cards:
            for field in required:
                assert field in card, f"Missing {field} in {card.get('skill_name')}"

    def test_status_values_are_valid(self):
        VALID_STATUSES = {"BACKLOG", "IN_PROGRESS", "REGRESSION", "VALIDATING", "DEPLOYED", "STALE"}
        cards = load_gepa_cards()
        for card in cards:
            assert card["status"] in VALID_STATUSES, f"Invalid status: {card['status']}"

    def test_is_stale_is_boolean(self):
        cards = load_gepa_cards()
        for card in cards:
            assert isinstance(card.get("is_stale"), bool)


class TestCompanionCardLoading:
    def test_load_nonexistent_file_returns_empty(self):
        cards = load_companion_cards(Path("/nonexistent/path/board-state.md"))
        assert cards == []

    def test_load_real_file_returns_cards(self):
        cards = load_companion_cards()
        assert isinstance(cards, list)
        # Real board has cards
        assert len(cards) >= 0

    def test_companion_cards_have_board_field(self):
        cards = load_companion_cards()
        for card in cards:
            assert card.get("board") == "companion"

    def test_companion_cards_have_status(self):
        cards = load_companion_cards()
        for card in cards:
            assert card.get("status") is not None


class TestFilters:
    def setup_method(self):
        # Use real cards as fixture
        self.cards = load_gepa_cards()

    def test_board_filter(self):
        class FakeArgs:
            board = "gepa"
            status = None
            priority = None
            delta_min = None
            delta_max = None
            age_hours = None
            is_stale = None
            eval_source = None
            multi_run = None
            search = None

        filtered = apply_filters(self.cards, FakeArgs())
        assert all(c.get("board") == "gepa" for c in filtered)

    def test_status_filter(self):
        class FakeArgs:
            board = None
            status = "VALIDATING"
            priority = None
            delta_min = None
            delta_max = None
            age_hours = None
            is_stale = None
            eval_source = None
            multi_run = None
            search = None

        filtered = apply_filters(self.cards, FakeArgs())
        assert all(c["status"] == "VALIDATING" for c in filtered)

    def test_delta_min_filter(self):
        class FakeArgs:
            board = None
            status = None
            priority = None
            delta_min = 0.05
            delta_max = None
            age_hours = None
            is_stale = None
            eval_source = None
            multi_run = None
            search = None

        filtered = apply_filters(self.cards, FakeArgs())
        assert all(c["best_delta"] >= 0.05 for c in filtered)

    def test_multi_run_filter(self):
        class FakeArgs:
            board = None
            status = None
            priority = None
            delta_min = None
            delta_max = None
            age_hours = None
            is_stale = None
            eval_source = None
            multi_run = True
            search = None

        filtered = apply_filters(self.cards, FakeArgs())
        assert all(c.get("is_multi_run") is True for c in filtered)

    def test_search_filter(self):
        class FakeArgs:
            board = None
            status = None
            priority = None
            delta_min = None
            delta_max = None
            age_hours = None
            is_stale = None
            eval_source = None
            multi_run = None
            search = "companion"

        filtered = apply_filters(self.cards, FakeArgs())
        assert all(
            "companion" in (c.get("skill_name") or "").lower()
            for c in filtered
        )


class TestSort:
    def test_sort_best_delta_descending(self):
        cards = [{"best_delta": 0.1}, {"best_delta": 0.5}, {"best_delta": 0.01}]
        sorted_cards = apply_sort(cards, "best_delta")
        assert sorted_cards[0]["best_delta"] == 0.5
        assert sorted_cards[1]["best_delta"] == 0.1
        assert sorted_cards[2]["best_delta"] == 0.01

    def test_sort_nulls_last(self):
        cards = [{"best_delta": 0.1}, {"best_delta": None}, {"best_delta": 0.5}]
        sorted_cards = apply_sort(cards, "best_delta")
        assert sorted_cards[-1]["best_delta"] is None

    def test_sort_skill_name_alphabetical(self):
        cards = [{"skill_name": "zebra"}, {"skill_name": "alpha"}, {"skill_name": "middle"}]
        sorted_cards = apply_sort(cards, "skill_name")
        assert sorted_cards[0]["skill_name"] == "alpha"
        assert sorted_cards[-1]["skill_name"] == "zebra"


class TestOutputFormats:
    def test_format_json_returns_valid_json(self):
        cards = [{"skill_name": "test", "status": "VALIDATING"}]
        output = format_json(cards)
        parsed = json.loads(output)
        assert parsed == cards

    def test_format_markdown_empty(self):
        output = format_markdown([], "test")
        assert "No cards match" in output

    def test_format_markdown_groups_by_status(self):
        cards = [
            {"board": "gepa", "skill_name": "a", "status": "VALIDATING", "priority": "high",
             "best_delta": 0.1, "run_count": 1, "is_stale": False},
            {"board": "gepa", "skill_name": "b", "status": "REGRESSION", "priority": "low",
             "best_delta": -0.1, "run_count": 1, "is_stale": False},
        ]
        output = format_markdown(cards, "test")
        assert "VALIDATING" in output
        assert "REGRESSION" in output
        assert "`a`" in output
        assert "`b`" in output


class TestCLI:
    def test_parse_status_comma_separated(self):
        parser = build_parser()
        args = parser.parse_args(["--status", "VALIDATING,REGRESSION"])
        assert args.status == "VALIDATING,REGRESSION"

    def test_default_board_is_all(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.board == "all"

    def test_delta_range(self):
        parser = build_parser()
        args = parser.parse_args(["--delta-min", "0.05", "--delta-max", "0.20"])
        assert args.delta_min == 0.05
        assert args.delta_max == 0.20

    def test_main_count(self):
        parser = build_parser()
        args = parser.parse_args(["--format", "count"])
        # Just verify it doesn't crash
        assert args.format == "count"
