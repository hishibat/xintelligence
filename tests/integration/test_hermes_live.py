"""Live integration test against real Hermes CLI in WSL2.

Skipped unless env HERMES_LIVE_TESTS=1 is set OR `pytest -m hermes_live` is
explicitly passed. This costs Hermes/Grok API tokens and takes ~30-90s.
"""
from __future__ import annotations

import os
import shutil

import pytest

from src.adapters.search_hermes import HermesSearchProvider


pytestmark = pytest.mark.hermes_live


def _wsl_present() -> bool:
    return shutil.which("wsl") is not None


@pytest.mark.skipif(
    os.environ.get("HERMES_LIVE_TESTS") != "1",
    reason="set HERMES_LIVE_TESTS=1 to run live Hermes integration",
)
@pytest.mark.skipif(not _wsl_present(), reason="wsl not present on host")
def test_hermes_live_x_search_smoke(tmp_path):
    provider = HermesSearchProvider(
        raw_response_dir=tmp_path / "raw_responses" / "hermes",
        timeout_seconds=120,
    )
    result = provider.search(
        "Find one recent X post about AI agent in production.",
        topic="ai_agents",
        time_range="24h",
    )
    assert len(result.items) >= 1
    item = result.items[0]
    # We expect at least one citation; if none, surface as parse_warning
    if not item.cited_urls:
        pytest.xfail(f"Hermes returned no x.com URLs. parse_warnings={item.parse_warnings}")
    assert item.summary
    assert item.raw_response_path
