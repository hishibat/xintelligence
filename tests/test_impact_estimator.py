"""src.core.impact_estimator — rule-based scoring."""
from __future__ import annotations

from src.core.impact_estimator import ImpactEstimate, estimate_impact


def test_score_in_1_to_10_range():
    est = estimate_impact(channel="x_post", draft_text="x" * 120,
                          source_url_count=2)
    assert 1.0 <= est.estimated_impact_score <= 10.0


def test_no_sources_penalised():
    with_src = estimate_impact(channel="x_post", draft_text="x" * 120, source_url_count=3)
    without = estimate_impact(channel="x_post", draft_text="x" * 120, source_url_count=0)
    assert without.estimated_impact_score < with_src.estimated_impact_score


def test_official_source_boosts():
    base = estimate_impact(channel="x_post", draft_text="x" * 120, source_url_count=2)
    with_off = estimate_impact(
        channel="x_post", draft_text="x" * 120, source_url_count=2,
        has_official_source=True,
    )
    assert with_off.estimated_impact_score > base.estimated_impact_score


def test_frontier_models_no_source_penalty():
    base = estimate_impact(channel="x_post", draft_text="x" * 120,
                           source_url_count=0, topic="ai_agents")
    frontier = estimate_impact(channel="x_post", draft_text="x" * 120,
                               source_url_count=0, topic="frontier_models")
    assert frontier.estimated_impact_score < base.estimated_impact_score


def test_hook_pattern_japanese():
    no_hook = estimate_impact(channel="x_post",
                              draft_text="ニュースを淡々と紹介します。" + "x" * 80,
                              source_url_count=2)
    hooked = estimate_impact(channel="x_post",
                             draft_text="なぜこれが重要か。" + "x" * 80,
                             source_url_count=2)
    assert hooked.estimated_impact_score >= no_hook.estimated_impact_score


def test_x_post_too_long_penalty():
    short = estimate_impact(channel="x_post", draft_text="x" * 150,
                            source_url_count=2)
    long_ = estimate_impact(channel="x_post", draft_text="x" * 400,
                            source_url_count=2)
    assert short.estimated_impact_score > long_.estimated_impact_score


def test_linkedin_word_count_band():
    body = " ".join(["word"] * 700)  # 700 words
    est = estimate_impact(channel="linkedin", draft_text=body, source_url_count=2)
    assert any("standard LinkedIn essay" in r for r in est.reasoning)


def test_high_citationless_run_penalises():
    clean = estimate_impact(channel="x_post", draft_text="x" * 120,
                            source_url_count=2, citationless_ratio=0.0)
    dirty = estimate_impact(channel="x_post", draft_text="x" * 120,
                            source_url_count=2, citationless_ratio=0.75)
    assert clean.estimated_impact_score > dirty.estimated_impact_score


def test_to_dict_serialisable():
    est = estimate_impact(channel="x_post", draft_text="x" * 120, source_url_count=2)
    d = est.to_dict()
    assert "estimated_impact_score" in d
    assert "virality_potential" in d
    assert "reasoning" in d and isinstance(d["reasoning"], list)
    assert "disclaimer" in d


def test_confidence_is_low_for_rule_based():
    est = estimate_impact(channel="x_post", draft_text="x" * 120, source_url_count=2)
    assert est.confidence == "low"


def test_band_thresholds():
    # very low (no sources, generic text)
    low = estimate_impact(channel="x_post", draft_text="generic", source_url_count=0,
                          citationless_ratio=0.8, topic="frontier_models")
    assert low.virality_potential == "low"

    # high (great hook + sources + official)
    hi_text = "なぜ重要か。" + "x" * 100
    high = estimate_impact(
        channel="x_post", draft_text=hi_text, source_url_count=5,
        has_official_source=True, has_founder_source=True,
    )
    assert high.virality_potential in ("medium", "high")
