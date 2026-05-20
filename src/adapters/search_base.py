"""Search Provider Contract.

All providers (mock / hermes / xai / x_api) must return a SearchResult with
explicit ``capabilities`` and ``missing_fields`` so downstream code can
handle granularity differences without surprise.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from src.core.schema import Capabilities, SearchResult


class SearchProvider(ABC):
    """Abstract base for X search providers."""

    name: ClassVar[str] = "base"
    capabilities: ClassVar[Capabilities]

    @abstractmethod
    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        """Run a single search and return a SearchResult.

        Implementations must populate ``capabilities`` and ``missing_fields``
        truthfully (never claim a field is supported when it can't be filled).
        """
        ...


# Default capability profiles per provider type. Concrete providers may
# override on a per-instance basis (e.g. when a user's Hermes config exposes
# extra tools).

CAPS_MOCK = Capabilities(
    supports_raw_post_text=True,
    supports_author=True,
    supports_created_at=True,
    supports_engagement_metrics=True,
    supports_thread_context=False,
    supports_citations=True,
    supports_time_range=True,
    supports_query_operators=True,
)

CAPS_HERMES = Capabilities(
    supports_raw_post_text=False,
    supports_author=False,
    supports_created_at=False,
    supports_engagement_metrics=False,
    supports_thread_context=False,
    supports_citations=True,
    supports_time_range=False,
    supports_query_operators=False,
)

CAPS_XAI = Capabilities(
    supports_raw_post_text=False,
    supports_author=False,
    supports_created_at=False,
    supports_engagement_metrics=False,
    supports_thread_context=False,
    supports_citations=True,
    supports_time_range=False,
    supports_query_operators=False,
)

CAPS_X_API = Capabilities(
    supports_raw_post_text=True,
    supports_author=True,
    supports_created_at=True,
    supports_engagement_metrics=True,
    supports_thread_context=True,
    supports_citations=False,
    supports_time_range=True,
    supports_query_operators=True,
)
