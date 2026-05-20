from src.adapters.search_mock import MockSearchProvider
from src.core.schema import SearchCitationResult


def test_citation_results_declare_missing_fields():
    provider = MockSearchProvider()
    result = provider.search("any", topic="all", time_range="24h")
    citation_items = [it for it in result.items if isinstance(it, SearchCitationResult)]
    assert citation_items, "fixtures must include at least one SearchCitationResult"
    for it in citation_items:
        # Hermes-style results should explicitly mark these as missing
        assert "engagement_metrics" in it.missing_fields
        assert "author" in it.missing_fields


def test_search_result_aggregates_missing_fields():
    provider = MockSearchProvider()
    result = provider.search("any", topic="all", time_range="24h")
    # Aggregation should produce a sorted unique list
    assert result.missing_fields == sorted(set(result.missing_fields))
