"""Dedupe collected items by URL + normalized-text hash."""
from __future__ import annotations

import hashlib
import re

from src.core.schema import Post, StructuredPost


_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.strip()).lower()


def _content_hash(post: Post) -> str:
    return hashlib.sha1(_normalize(post.primary_text()).encode("utf-8")).hexdigest()


def dedupe(items: list[Post]) -> list[Post]:
    """Keep first occurrence; key on URL when present, content-hash otherwise."""
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    out: list[Post] = []
    for item in items:
        key_url = None
        if isinstance(item, StructuredPost) and item.url:
            key_url = item.url
        else:
            urls = item.citation_urls()
            if urls:
                key_url = urls[0]

        if key_url and key_url in seen_urls:
            continue

        ch = _content_hash(item)
        if ch in seen_hashes:
            continue

        if key_url:
            seen_urls.add(key_url)
        seen_hashes.add(ch)
        out.append(item)
    return out
