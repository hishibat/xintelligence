"""check_hermes.py — doctor output parsing."""
from __future__ import annotations

from pathlib import Path

from scripts.check_hermes import check_xai_oauth, check_x_search_tool


FIXTURE = Path(__file__).parent / "fixtures" / "hermes_doctor_sample.txt"


def test_doctor_fixture_marks_xai_oauth_logged_in():
    text = FIXTURE.read_text(encoding="utf-8")
    ok, msg = check_xai_oauth(text)
    assert ok is True, f"expected logged-in marker. Got: {msg}"
    assert "logged in" in msg


def test_doctor_fixture_marks_x_search_available():
    text = FIXTURE.read_text(encoding="utf-8")
    ok, msg = check_x_search_tool(text)
    assert ok is True


def test_doctor_detects_missing_xai_oauth():
    text = "◆ Auth Providers\n  ⚠ xAI OAuth (not logged in)\n"
    ok, msg = check_xai_oauth(text)
    assert ok is False


def test_doctor_detects_missing_x_search_tool():
    text = "◆ Tool Availability\n  ⚠ x_search (disabled)\n  ✓ browser\n"
    ok, msg = check_x_search_tool(text)
    assert ok is False


def test_doctor_handles_garbage_input():
    for trash in ("", "no headers at all", "✗ everything is broken"):
        ok, _ = check_xai_oauth(trash)
        assert ok is False
        ok, _ = check_x_search_tool(trash)
        assert ok is False
