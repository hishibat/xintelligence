"""X API v2 provider — stub for Phase 3+.

Real impl: search /2/tweets/search/recent or /all with bearer token.
Returns StructuredPost items with full metadata.
"""
from __future__ import annotations

from typing import ClassVar

from src.adapters.search_base import CAPS_X_API, SearchProvider
from src.core.schema import Capabilities, SearchResult


class XAPISearchProvider(SearchProvider):
    name: ClassVar[str] = "x_api"
    capabilities: ClassVar[Capabilities] = CAPS_X_API

    def __init__(self, **_: object) -> None: ...

    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        raise NotImplementedError(
            "X API provider is a Phase 3+ stub. Use mock for MVP."
        )
