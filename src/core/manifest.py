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
) -> RunManifest:
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
        warnings=warnings,
        errors=errors,
        missing_fields_summary=summarize_missing(deduped_items),
        fallback_used=fallback_used,
    )


def write_manifest(manifest: RunManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)
