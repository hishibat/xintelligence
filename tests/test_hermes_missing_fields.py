"""SearchCitationResult from Hermes must always declare 6 missing_fields."""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.adapters.search_hermes import HermesSearchProvider


REQUIRED_MISSING = {
    "author",
    "author_handle",
    "created_at",
    "engagement_metrics",
    "thread_context",
    "raw_post_text",
}


class _Fake:
    def __init__(self, stdout=""):
        self.returncode = 0
        self.stdout = stdout
        self.stderr = ""


def test_missing_fields_populated(monkeypatch, tmp_path: Path):
    def fake_run(cmd, **kwargs):
        return _Fake(stdout="ok body. Sources: https://x.com/i/status/1\n")
    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = HermesSearchProvider(raw_response_dir=tmp_path)
    result = provider.search("any", topic="x", time_range="24h")
    item = result.items[0]
    assert REQUIRED_MISSING.issubset(set(item.missing_fields))
    # SearchResult.missing_fields should aggregate from items
    assert REQUIRED_MISSING.issubset(set(result.missing_fields))
