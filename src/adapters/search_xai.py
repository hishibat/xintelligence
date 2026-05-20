"""xAI Grok Responses + x_search provider — stub for Phase 3.

Real impl calls xAI Responses API with the x_search tool enabled. Returns
mostly SearchCitationResult items.
"""
from __future__ import annotations

from typing import ClassVar

from src.adapters.search_base import CAPS_XAI, SearchProvider
from src.core.schema import Capabilities, SearchResult


class XAISearchProvider(SearchProvider):
    name: ClassVar[str] = "xai"
    capabilities: ClassVar[Capabilities] = CAPS_XAI

    def __init__(self, **_: object) -> None: ...

    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        raise NotImplementedError(
            "xAI provider is a Phase 3 stub. Set X_SEARCH_PROVIDER=mock for MVP."
        )
