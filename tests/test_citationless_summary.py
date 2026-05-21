"""summarize_citationless() — quality-signal aggregation."""
from __future__ import annotations

from src.core.manifest import summarize_citationless
from src.core.schema import (
    SearchCitationResult,
    StructuredPost,
    VerificationTags,
)


def _scr(topic: str, urls: list[str]) -> SearchCitationResult:
    return SearchCitationResult(
        summary="x", provider_name="hermes",
        cited_urls=urls, topic=topic,
        verification=VerificationTags(),
    )


def _sp(topic: str, url: str = "https://x.com/u/status/1") -> StructuredPost:
    return StructuredPost(
        post_id="p1", text="x", url=url, provider_name="mock",
        topic=topic, verification=VerificationTags(),
    )


def test_empty_input_returns_zeros():
    assert summarize_citationless([]) == (0, 0.0, [])


def test_all_with_citations_gives_zero_count():
    items = [_scr("t1", ["https://x.com/a/status/1"]),
             _scr("t1", ["https://x.com/b/status/2"])]
    count, ratio, high = summarize_citationless(items)
    assert count == 0
    assert ratio == 0.0
    assert high == []


def test_partial_citationless_counts_correctly():
    items = [_scr("t1", ["https://x.com/a/status/1"]),
             _scr("t1", []),
             _scr("t2", []),
             _scr("t2", ["https://x.com/b/status/2"])]
    count, ratio, high = summarize_citationless(items)
    assert count == 2
    assert ratio == 0.5


def test_high_ratio_topic_detected():
    # t1: 0/3 citationless (0%) — fine
    # t2: 4/5 citationless (80%) — flagged
    items = (
        [_scr("t1", ["https://x.com/a/status/1"]) for _ in range(3)]
        + [_scr("t2", []) for _ in range(4)]
        + [_scr("t2", ["https://x.com/b/status/2"])]
    )
    count, ratio, high = summarize_citationless(items)
    assert count == 4
    assert ratio == 0.5  # 4 / 8
    assert "t2" in high
    assert "t1" not in high


def test_structured_post_with_url_is_not_citationless():
    items = [_sp("t1"), _sp("t1"), _scr("t2", [])]
    count, ratio, high = summarize_citationless(items)
    assert count == 1
    assert "t2" in high  # 1/1 = 100% > 50%
    assert "t1" not in high


def test_threshold_default_is_50_percent():
    # Exactly 50% should NOT be flagged (the check is strictly greater than)
    items = [_scr("t1", []), _scr("t1", ["https://x.com/a/status/1"])]
    _, _, high = summarize_citationless(items, high_ratio_threshold=0.5)
    assert "t1" not in high
