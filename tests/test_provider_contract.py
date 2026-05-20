from src.adapters.search_base import SearchProvider
from src.adapters.search_mock import MockSearchProvider


def test_mock_provider_returns_search_result_with_capabilities():
    provider = MockSearchProvider()
    result = provider.search("test", topic="all", time_range="24h")
    assert result.provider_name == "mock"
    assert result.capabilities is not None
    # capability flags must be booleans (no None)
    caps = result.capabilities.to_dict()
    assert all(isinstance(v, bool) for v in caps.values())
    # source_urls preserved and deduped
    assert len(result.source_urls) == len(set(result.source_urls))


def test_provider_subclasses_must_implement_search():
    class Broken(SearchProvider):
        pass
    try:
        Broken()  # type: ignore[abstract]
    except TypeError:
        # abstract method check works
        return
    raise AssertionError("Expected TypeError for missing abstract method")


def test_capabilities_keys_complete():
    from src.adapters.search_base import CAPS_MOCK, CAPS_HERMES, CAPS_XAI, CAPS_X_API
    required = {
        "supports_raw_post_text", "supports_author", "supports_created_at",
        "supports_engagement_metrics", "supports_thread_context",
        "supports_citations", "supports_time_range", "supports_query_operators",
    }
    for c in (CAPS_MOCK, CAPS_HERMES, CAPS_XAI, CAPS_X_API):
        d = c.to_dict()
        assert set(d.keys()) == required, f"missing keys for capability: {required - set(d.keys())}"
