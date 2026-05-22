"""trend_analyzer._extract_keywords — URL noise / stopwords filtering."""
from src.core.scoring import ScoreBreakdown
from src.core.schema import (
    ScoredItem,
    SearchCitationResult,
    VerificationTags,
)
from src.core.trend_analyzer import _extract_keywords


def _scored_citation(text: str) -> ScoredItem:
    cr = SearchCitationResult(
        summary=text, provider_name="hermes",
        cited_urls=[],
        verification=VerificationTags(),
    )
    return ScoredItem(post=cr, score=ScoreBreakdown(5, 5, 5, 5, 5, 5))


def test_https_and_url_fragments_excluded():
    items = [_scored_citation(
        "Hermes Agent released today. See https://x.com/example for more. "
        "posts about agentic workflow and low-refusal models. "
        "https posts describe a new approach."
    )]
    kws = _extract_keywords(items, k=8)
    # Pure URL / generic terms must NOT appear
    for forbidden in ("https", "posts", "describe", "http", "www", "com"):
        assert forbidden not in kws, f"forbidden '{forbidden}' leaked into emerging keywords: {kws}"


def test_meaningful_keywords_preserved():
    items = [_scored_citation(
        "Hermes openclaw agentic workflow low-refusal models. "
        "Hermes is an agent CLI for multiple providers. "
        "openclaw integrates with hermes."
    )]
    kws = _extract_keywords(items, k=5)
    # At least one domain term should survive
    assert any(kw in kws for kw in ("hermes", "openclaw", "agentic", "agent", "low-refusal")), (
        f"expected at least one domain term; got {kws}"
    )


def test_generic_verbs_filtered():
    items = [_scored_citation(
        "He says the system can do many things. He explained that users "
        "describe new features. People share their experiences."
    )]
    kws = _extract_keywords(items, k=8)
    for verb in ("says", "describe", "share", "explained", "share"):
        assert verb not in kws


def test_pure_digits_excluded():
    items = [_scored_citation(
        "Released 2026 with version 14 and 1000 users. The model has agents."
    )]
    kws = _extract_keywords(items, k=8)
    for d in ("2026", "14", "1000"):
        assert d not in kws


def test_short_tokens_excluded():
    items = [_scored_citation("ai is a big topic. ml ai gpt grok hermes.")]
    kws = _extract_keywords(items, k=5)
    for short in ("ai", "ml", "is", "a"):
        assert short not in kws
