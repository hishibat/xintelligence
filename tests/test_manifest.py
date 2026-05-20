import json
from pathlib import Path

from src.adapters.search_mock import MockSearchProvider
from src.core.dedupe import dedupe
from src.core.manifest import build_manifest, write_manifest


def test_manifest_records_fallback(tmp_path: Path):
    items = MockSearchProvider().search("any", "all", "24h").items
    deduped = dedupe(items)
    manifest = build_manifest(
        provider="mock", llm_provider="claude", config_hash="abc",
        query_count=3, raw_items=items, deduped_items=deduped,
        top10_count=10, warnings=["Claude API key missing"],
        errors=[], fallback_used=["llm:claude->mock"],
    )
    p = tmp_path / "run_manifest.json"
    write_manifest(manifest, p)
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["provider"] == "mock"
    assert "llm:claude->mock" in payload["fallback_used"]
    assert payload["warnings"], "warnings must propagate"
    assert payload["raw_item_count"] == len(items)
    assert payload["deduped_item_count"] == len(deduped)
