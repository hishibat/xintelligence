"""RunManifest writer."""
from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.core.schema import Post, RunManifest


def new_run_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"


def summarize_missing(items: list[Post]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for it in items:
        for f in it.missing_fields:
            counter[f] += 1
    return dict(counter)


def summarize_citationless(
    items: list[Post], *, high_ratio_threshold: float = 0.5
) -> tuple[int, float, list[str]]:
    """Count items whose citation_urls() is empty.

    Returns (count, ratio, high_ratio_topics).
    A topic appears in high_ratio_topics if it has ≥ 1 item AND > threshold
    of its items are citationless. Useful for catching whole-topic quality
    problems like the grok_xai self-referential failure mode.
    """
    if not items:
        return 0, 0.0, []
    citationless = [p for p in items if not p.citation_urls()]
    count = len(citationless)
    ratio = count / len(items)

    by_topic_total: Counter[str] = Counter()
    by_topic_zero: Counter[str] = Counter()
    for p in items:
        t = (p.topic or "uncategorized")
        by_topic_total[t] += 1
        if not p.citation_urls():
            by_topic_zero[t] += 1
    high_ratio: list[str] = [
        t for t, n in by_topic_zero.items()
        if by_topic_total[t] > 0 and (n / by_topic_total[t]) > high_ratio_threshold
    ]
    return count, round(ratio, 3), sorted(high_ratio)


def build_manifest(
    *,
    provider: str,
    llm_provider: str,
    config_hash: str,
    query_count: int,
    raw_items: list[Post],
    deduped_items: list[Post],
    top10_count: int,
    warnings: list[str],
    errors: list[str],
    fallback_used: list[str],
    fixture_hash: str = "",
) -> RunManifest:
    citationless_count, citationless_ratio, high_ratio_topics = summarize_citationless(deduped_items)
    return RunManifest(
        run_id=new_run_id(),
        executed_at=datetime.now(timezone.utc),
        provider=provider,
        llm_provider=llm_provider,
        config_hash=config_hash,
        query_count=query_count,
        raw_item_count=len(raw_items),
        deduped_item_count=len(deduped_items),
        top10_count=top10_count,
        fixture_hash=fixture_hash,
        warnings=warnings,
        errors=errors,
        missing_fields_summary=summarize_missing(deduped_items),
        fallback_used=fallback_used,
        citationless_items_count=citationless_count,
        citationless_ratio=citationless_ratio,
        topics_with_high_citationless_ratio=high_ratio_topics,
    )


def write_manifest(manifest: RunManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)
