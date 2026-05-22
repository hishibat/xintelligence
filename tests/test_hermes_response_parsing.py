"""Hermes response parsing — `-z` oneshot stdout → SearchCitationResult."""
from __future__ import annotations

from pathlib import Path

from src.adapters.search_hermes import HermesSearchProvider, X_URL_PATTERN
from src.core.schema import SearchCitationResult


FIXTURE = Path(__file__).parent / "fixtures" / "hermes_smoke_response.txt"


def test_x_url_pattern_extracts_status_urls():
    sample = (
        "A recent X post says Claude Code can do X. "
        "Sources: https://x.com/i/status/2056482709548249230\n"
        "Also see https://x.com/elonmusk/status/1234567890 for context."
    )
    urls = X_URL_PATTERN.findall(sample)
    assert "https://x.com/i/status/2056482709548249230" in urls
    assert "https://x.com/elonmusk/status/1234567890" in urls
    assert len(urls) == 2


def test_fixture_yields_at_least_one_url():
    text = FIXTURE.read_text(encoding="utf-8")
    urls = X_URL_PATTERN.findall(text)
    assert len(urls) >= 1
    assert any("x.com" in u for u in urls)


def test_to_citation_result_populates_all_required_fields():
    text = FIXTURE.read_text(encoding="utf-8")
    provider = HermesSearchProvider()
    result = provider._to_citation_result(
        stdout=text, stderr="", topic="claude_code",
        raw_path=Path("/tmp/raw_response_path.stdout"),
        extra_warnings=[],
    )
    assert isinstance(result, SearchCitationResult)
    assert result.summary == text.strip()
    assert result.provider_response == text.strip()
    assert result.cited_urls, "cited_urls must contain at least one URL"
    assert all(u.startswith("https://") for u in result.cited_urls)
    # cited_posts mirrors cited_urls with snippet/title None
    assert len(result.cited_posts) == len(result.cited_urls)
    for cp in result.cited_posts:
        assert cp["url"] in result.cited_urls
        assert cp["snippet"] is None and cp["title"] is None
    # missing_fields contract
    for fld in ("author", "author_handle", "created_at",
                "engagement_metrics", "thread_context", "raw_post_text"):
        assert fld in result.missing_fields
    # Path stored as a string from the original Path object; compare by basename
    # to stay platform-agnostic (Windows uses '\\', POSIX uses '/').
    assert result.raw_response_path is not None
    assert result.raw_response_path.endswith("raw_response_path.stdout")
    assert result.provider_name == "hermes"


def test_parse_warnings_when_no_urls():
    provider = HermesSearchProvider()
    result = provider._to_citation_result(
        stdout="Some answer body with no x.com links at all.\nSources: (none)",
        stderr="",
        topic="ai_agents",
        raw_path=None,
        extra_warnings=[],
    )
    assert any("no x.com" in w.lower() for w in result.parse_warnings)


def test_parse_warnings_when_no_sources_block():
    provider = HermesSearchProvider()
    result = provider._to_citation_result(
        stdout="A bare answer with a link https://x.com/i/status/1 but no sources marker.",
        stderr="",
        topic="x",
        raw_path=None,
        extra_warnings=[],
    )
    assert any("Sources" in w for w in result.parse_warnings)


def test_parse_warnings_when_stderr_present():
    provider = HermesSearchProvider()
    result = provider._to_citation_result(
        stdout="ok body Sources: https://x.com/i/status/9",
        stderr="some warning text from hermes",
        topic="x",
        raw_path=None,
        extra_warnings=[],
    )
    assert any("stderr" in w for w in result.parse_warnings)
