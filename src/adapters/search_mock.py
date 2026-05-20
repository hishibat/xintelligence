"""Mock search provider — reads from fixtures/sample_posts.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from src.adapters.search_base import CAPS_MOCK, SearchProvider
from src.core.schema import (
    Capabilities,
    Post,
    SearchCitationResult,
    SearchResult,
    StructuredPost,
    VerificationTags,
)


DEFAULT_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "sample_posts.json"


class MockSearchProvider(SearchProvider):
    name: ClassVar[str] = "mock"
    capabilities: ClassVar[Capabilities] = CAPS_MOCK

    def __init__(self, fixtures_path: Path | None = None) -> None:
        self.fixtures_path = Path(fixtures_path) if fixtures_path else DEFAULT_FIXTURES
        self._cache: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._cache is None:
            with self.fixtures_path.open(encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data.get("items", [])
        return self._cache

    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        items_raw = self._load()
        matched: list[Post] = []
        source_urls: list[str] = []

        for raw in items_raw:
            if topic != "all" and raw.get("topic") != topic:
                continue
            post = _to_post(raw, provider_name=self.name)
            matched.append(post)
            source_urls.extend(post.citation_urls())

        # capabilities is per-class but we surface it on the result too
        missing_fields = self._compute_missing(matched)
        return SearchResult(
            provider_name=self.name,
            query=query,
            topic=topic,
            time_range=time_range,
            retrieved_at=datetime.now(timezone.utc),
            items=matched,
            source_urls=_dedupe_preserve_order(source_urls),
            capabilities=self.capabilities,
            missing_fields=missing_fields,
            raw_response_path=str(self.fixtures_path),
        )

    @staticmethod
    def _compute_missing(items: list[Post]) -> list[str]:
        fields: set[str] = set()
        for it in items:
            fields.update(it.missing_fields)
        return sorted(fields)


def _to_post(raw: dict[str, Any], provider_name: str) -> Post:
    kind = raw.get("kind", "structured_post")
    verification = VerificationTags(
        verification_status="unverified",
        source_type=raw.get("source_type_hint", "unknown"),
        risk_flags=[],
    )

    if kind == "search_citation_result":
        missing = [
            f for f in ("author", "created_at", "engagement_metrics", "thread_context")
            if True  # all of these are not present in citation results by definition
        ]
        return SearchCitationResult(
            summary=raw["summary"],
            provider_name=provider_name,
            cited_urls=list(raw.get("cited_urls", [])),
            cited_posts=list(raw.get("cited_posts", [])),
            provider_response=raw.get("provider_response", ""),
            confidence=raw.get("confidence"),
            topic=raw.get("topic"),
            verification=verification,
            missing_fields=missing,
        )

    # structured_post
    created_raw = raw.get("created_at")
    created_at = None
    if created_raw:
        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        except ValueError:
            created_at = None

    missing: list[str] = []
    if not raw.get("metrics"):
        missing.append("engagement_metrics")
    if not raw.get("author"):
        missing.append("author")
    if not created_at:
        missing.append("created_at")
    if not raw.get("thread_context"):
        missing.append("thread_context")

    return StructuredPost(
        post_id=raw["post_id"],
        text=raw["text"],
        url=raw["url"],
        provider_name=provider_name,
        author=raw.get("author"),
        author_handle=raw.get("author_handle"),
        created_at=created_at,
        metrics=raw.get("metrics"),
        thread_context=raw.get("thread_context"),
        topic=raw.get("topic"),
        verification=verification,
        missing_fields=missing,
    )


def _dedupe_preserve_order(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out
