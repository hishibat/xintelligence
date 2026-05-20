from datetime import datetime, timezone

from src.core.schema import (
    SearchCitationResult,
    StructuredPost,
    VerificationTags,
)
from src.core.scoring import score_post, score_all, top_n
from src.utils.config_loader import load_config


def _now():
    return datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)


def test_score_post_full_returns_breakdown():
    cfg = load_config()
    p = StructuredPost(
        post_id="t1",
        text="Claude Code agent governance — practical lessons for enterprise AI.",
        url="https://x.com/x/1",
        provider_name="mock",
        author="A", author_handle="@a",
        created_at=_now(),
        metrics={"likes": 5000, "reposts": 800, "replies": 100, "views": 200000},
        verification=VerificationTags(),
    )
    score = score_post(p, profile=cfg.profile, weights=cfg.output["scoring"]["weights"], now=_now())
    assert score.method == "full"
    assert 0.0 <= score.total <= 10.0
    assert score.career_relevance > 0


def test_score_post_citation_fallback_when_no_metrics():
    cfg = load_config()
    cr = SearchCitationResult(
        summary="Hermes Agent 2.1 GA; Claude Code integration noted.",
        provider_name="hermes",
        cited_urls=["https://a", "https://b", "https://c"],
        confidence=0.7,
        verification=VerificationTags(),
        missing_fields=["author", "created_at", "engagement_metrics"],
    )
    score = score_post(cr, profile=cfg.profile, weights=cfg.output["scoring"]["weights"], now=_now())
    assert score.method == "citation_fallback"


def test_top_n_orders_by_total():
    cfg = load_config()
    posts = [
        StructuredPost(
            post_id=str(i), text=f"item {i}", url=f"https://x/{i}", provider_name="mock",
            metrics={"likes": i * 1000, "reposts": i * 100, "replies": i * 20, "views": i * 50000},
            created_at=_now(),
            verification=VerificationTags(),
        )
        for i in range(1, 6)
    ]
    scored = score_all(posts, profile=cfg.profile, weights=cfg.output["scoring"]["weights"], now=_now())
    top = top_n(scored, n=3)
    assert len(top) == 3
    assert top[0].score.total >= top[1].score.total >= top[2].score.total
