from src.adapters.search_mock import MockSearchProvider
from src.core.dedupe import dedupe
from src.core.scoring import score_all, top_n
from src.utils.config_loader import load_config


def test_top10_items_keep_source_urls_or_citations():
    cfg = load_config()
    provider = MockSearchProvider()
    result = provider.search("any", topic="all", time_range="24h")
    deduped = dedupe(result.items)
    scored = score_all(deduped, profile=cfg.profile, weights=cfg.output["scoring"]["weights"])
    top = top_n(scored, n=10)

    assert len(top) > 0
    for item in top:
        urls = item.post.citation_urls()
        assert urls, f"item {item.post} lost its source URLs"
        assert all(u.startswith("http") for u in urls)
