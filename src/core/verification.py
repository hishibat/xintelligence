"""Heuristic verification / risk tagging.

Sources are tagged conservatively: anything we can't confirm stays
``unverified`` or ``needs_manual_check``. Risk flags are additive — a
single post can carry multiple (rumor + hype + product_claim etc.).

source_type promotion: if a post / citation references an X handle that
appears in ``config/official_handles.yaml``, the source_type is upgraded
to the strongest category that matches (official > founder_executive >
engineer_dev > media > influencer). This catches the common Hermes case
where SearchCitationResult is returned with source_type="unknown" but the
cited_urls contain well-known org / founder handles.
"""
from __future__ import annotations

import re

from src.core.schema import (
    Post,
    RiskFlag,
    SearchCitationResult,
    SourceType,
    StructuredPost,
    VerificationStatus,
)


_HANDLE_FROM_URL = re.compile(
    r"https?://(?:x|twitter)\.com/([^/\s\"']+)/status/", re.IGNORECASE
)

_SOURCE_TYPE_PRIORITY: list[str] = [
    "official", "founder_executive", "engineer_dev", "media", "influencer",
]


def _build_handle_index(handles_cfg: dict | None) -> dict[str, str]:
    """Return {lowercased_handle: source_type_label} from config dict."""
    if not handles_cfg:
        return {}
    index: dict[str, str] = {}
    # Iterate in priority order so higher tier wins on duplicate listings
    for tier in _SOURCE_TYPE_PRIORITY:
        for h in (handles_cfg.get(tier) or []):
            key = str(h).lower().lstrip("@")
            if key not in index:  # higher-tier assignment wins
                index[key] = tier
    return index


def _extract_handles(item: Post) -> list[str]:
    """Pull X handles from all URLs / author fields attached to the item."""
    handles: list[str] = []
    if isinstance(item, StructuredPost):
        if item.author_handle:
            handles.append(item.author_handle.lstrip("@").lower())
        if item.url:
            m = _HANDLE_FROM_URL.search(item.url)
            if m:
                handles.append(m.group(1).lower())
    elif isinstance(item, SearchCitationResult):
        for u in item.cited_urls:
            m = _HANDLE_FROM_URL.search(u)
            if m:
                handles.append(m.group(1).lower())
    return handles


def _resolve_source_type(item: Post, handle_index: dict[str, str]) -> str | None:
    """Best (highest-priority) source_type among handles referenced by item."""
    if not handle_index:
        return None
    handles = _extract_handles(item)
    if not handles:
        return None
    matches = [handle_index[h] for h in handles if h in handle_index]
    if not matches:
        return None
    for tier in _SOURCE_TYPE_PRIORITY:
        if tier in matches:
            return tier
    return None


_PRICING = re.compile(r"\$\s?\d|¥\s?\d|円|per\s+(?:1?k|million|month)|/hour|/月|無料枠|free tier", re.I)
_INVEST = re.compile(r"valuation|series\s+[a-d]|raised|資金調達|ipo|m&a|買収", re.I)
_LEGAL = re.compile(r"ai\s+act|gdpr|compliance|article\s+\d+|policy|regulation|法案|規制", re.I)
_SECURITY = re.compile(r"cve-|exploit|breach|脆弱性|侵害|leak", re.I)
_RUMOR = re.compile(r"heard|sources say|rumor|噂|聞いた|may launch|reportedly", re.I)
_HYPE = re.compile(r"unbelievable|game[- ]?changer|revolutionary|圧倒的|爆速|神アプデ", re.I)
_PRODUCT = re.compile(r"launch|release|ships|ga\b|preview|アップデート|公開|提供開始", re.I)


def _detect_risk_flags(text: str) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    if _RUMOR.search(text):
        flags.append("rumor")
    if _HYPE.search(text):
        flags.append("hype")
    if _INVEST.search(text):
        flags.append("investment_claim")
    if _PRODUCT.search(text):
        flags.append("product_claim")
    if _PRICING.search(text):
        flags.append("pricing_claim")
    if _LEGAL.search(text):
        flags.append("legal_or_policy_claim")
    if _SECURITY.search(text):
        flags.append("security_claim")
    return flags


def _classify_status(
    source_type: SourceType,
    citation_count: int,
    risk_flags: list[RiskFlag],
) -> VerificationStatus:
    if "rumor" in risk_flags and source_type in ("unknown", "influencer"):
        return "needs_manual_check"
    if source_type == "official":
        return "official_source_confirmed"
    if citation_count >= 2:
        return "multi_source_confirmed"
    if source_type in ("founder_executive", "engineer_dev", "media"):
        return "single_source"
    return "unverified"


def tag_items(items: list[Post], *, official_handles: dict | None = None) -> list[Post]:
    """Mutate verification tags in place and return the same list.

    If ``official_handles`` (the parsed ``config/official_handles.yaml``)
    is provided, source_type for each item is promoted when its cited
    handles appear in the registry.
    """
    handle_index = _build_handle_index(official_handles)

    for item in items:
        # Promote source_type from handle registry first so downstream
        # _classify_status uses the upgraded value.
        promoted = _resolve_source_type(item, handle_index)
        if promoted:
            item.verification.source_type = promoted  # type: ignore[assignment]

        text = item.primary_text()
        risk_flags = _detect_risk_flags(text)
        if isinstance(item, SearchCitationResult):
            citation_count = len(item.cited_urls)
        elif isinstance(item, StructuredPost):
            citation_count = 1 if item.url else 0
        else:
            citation_count = 0
        status = _classify_status(item.verification.source_type, citation_count, risk_flags)
        item.verification.risk_flags = risk_flags
        item.verification.verification_status = status
    return items
