"""Heuristic verification / risk tagging.

Sources are tagged conservatively: anything we can't confirm stays
``unverified`` or ``needs_manual_check``. Risk flags are additive — a
single post can carry multiple (rumor + hype + product_claim etc.).
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


def tag_items(items: list[Post]) -> list[Post]:
    """Mutate verification tags in place and return the same list."""
    for item in items:
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
