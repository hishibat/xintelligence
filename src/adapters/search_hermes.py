"""Hermes Agent search provider — stub for Phase 2.

Hermes' x_search returns a Grok-synthesized summary plus citations rather
than raw posts. When implemented, this provider should return mainly
SearchCitationResult items and surface explicit missing_fields.

See README "Pattern B: Hermes integration" and docs/design-lite.md.
"""
from __future__ import annotations

from typing import ClassVar

from src.adapters.search_base import CAPS_HERMES, SearchProvider
from src.core.schema import Capabilities, SearchResult


class HermesSearchProvider(SearchProvider):
    name: ClassVar[str] = "hermes"
    capabilities: ClassVar[Capabilities] = CAPS_HERMES

    def __init__(self, **_: object) -> None:
        # Real impl will load oauth token / endpoint here.
        ...

    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        raise NotImplementedError(
            "Hermes provider is a Phase 2 stub. Use --provider mock for MVP."
        )
