"""Scoring engine.

Tolerates missing fields. When engagement metrics are absent (Hermes / xAI
x_search), falls back to citation_count + LLM judgement + source confidence.
career_relevance reads from profile.yaml.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from src.core.schema import (
    Post,
    ScoreBreakdown,
    ScoredItem,
    SearchCitationResult,
    StructuredPost,
)


def _engagement_score(metrics: dict[str, int] | None) -> float:
    if not metrics:
        return 0.0
    likes = metrics.get("likes", 0)
    reposts = metrics.get("reposts", 0)
    replies = metrics.get("replies", 0)
    views = metrics.get("views", 0)
    raw = likes + 3 * reposts + 2 * replies + views / 50
    # log compression so a 1M-like post does not dwarf a 1k niche one
    return min(10.0, math.log10(max(raw, 1)) * 1.8)


def _novelty_score(post: Post, now: datetime) -> float:
    if isinstance(post, StructuredPost) and post.created_at:
        delta_h = (now - post.created_at).total_seconds() / 3600
        if delta_h <= 6:
            return 10.0
        if delta_h <= 24:
            return 8.0
        if delta_h <= 72:
            return 6.0
        if delta_h <= 24 * 7:
            return 4.0
        return 2.0
    # citation results have no timestamp → assume mid-recency
    return 6.0


def _focus_match(text: str, focus_list: list[str]) -> float:
    """Split slash/comma-delimited focus terms into atoms; any atom hit counts."""
    text_lc = text.lower()
    if not focus_list:
        return 0.0
    atoms: list[str] = []
    for term in focus_list:
        for chunk in term.replace(",", "/").split("/"):
            atom = chunk.strip().lower()
            if atom and len(atom) >= 3:
                atoms.append(atom)
    if not atoms:
        return 0.0
    hits = sum(1 for atom in atoms if atom in text_lc)
    return min(1.0, hits / max(1, len(atoms) // 3))


def _atom_match(text_lc: str, atoms: list[str]) -> float:
    """Direct atom substring match (atom list is already pre-lowercased)."""
    if not atoms:
        return 0.0
    hits = sum(1 for a in atoms if a in text_lc)
    # roughly: 3 atoms hit ⇒ ~1.0
    return min(1.0, hits / 3.0)


def _career_relevance(post: Post, profile: dict[str, Any]) -> tuple[float, str]:
    text = post.primary_text()
    text_lc = text.lower()
    focus = profile.get("focus_areas", {}) or {}
    weights = profile.get("relevance_weights", {}) or {}
    targets = profile.get("target_companies", {}) or {}

    # Legacy human-readable focus areas (still used for slash-split fallback)
    high = focus.get("high_priority", []) or []
    med = focus.get("medium_priority", []) or []
    low = focus.get("low_priority", []) or []

    # New atom-level vocabulary — preferred path
    atoms_high = [a.lower() for a in (profile.get("focus_atoms_high") or [])]
    atoms_med = [a.lower() for a in (profile.get("focus_atoms_medium") or [])]
    atoms_low = [a.lower() for a in (profile.get("focus_atoms_low") or [])]

    w_high = float(weights.get("high_priority", 1.0))
    w_med = float(weights.get("medium_priority", 0.6))
    w_low = float(weights.get("low_priority", 0.2))
    w_target = float(weights.get("target_company_mention", 1.2))

    # Atoms get full credit; legacy phrases get half (avoid double-counting)
    score = (
        (_atom_match(text_lc, atoms_high) + 0.5 * _focus_match(text, high))
        * 10.0 * w_high
        + (_atom_match(text_lc, atoms_med) + 0.5 * _focus_match(text, med))
        * 8.0 * w_med
        + (_atom_match(text_lc, atoms_low) + 0.5 * _focus_match(text, low))
        * 5.0 * w_low
    )

    company_hits: list[str] = []
    for _, names in targets.items():
        for name in names or []:
            if name.lower() in text.lower():
                company_hits.append(name)
                score *= w_target
                break

    rationale = "focus_match"
    if company_hits:
        rationale = f"target_company_hit:{','.join(sorted(set(company_hits)))}"
    return min(10.0, score), rationale


def _note_fit(post: Post) -> float:
    text = post.primary_text()
    length_bonus = min(1.0, len(text) / 240.0)
    insight_terms = ["why", "framework", "lesson", "pattern", "観点", "示唆", "なぜ", "構造"]
    insight_hits = sum(1 for t in insight_terms if t in text.lower())
    return min(10.0, 4.0 + 3.0 * length_bonus + 1.2 * insight_hits)


def _x_fit(post: Post) -> float:
    text = post.primary_text()
    short_bonus = max(0.0, 1.0 - abs(len(text) - 140) / 200.0)
    punch_terms = ["!", "?", "→", "▶", "今日", "新", "release", "ship"]
    punch_hits = sum(1 for t in punch_terms if t in text.lower())
    return min(10.0, 4.0 + 4.0 * short_bonus + 0.8 * punch_hits)


def _importance_with_fallback(
    post: Post,
    metrics_available: bool,
) -> tuple[float, str]:
    if metrics_available and isinstance(post, StructuredPost):
        return _engagement_score(post.metrics), "full"

    # No engagement metrics — combine citation count + provider confidence
    if isinstance(post, SearchCitationResult):
        citation = min(10.0, len(post.cited_urls) * 2.5)
        confidence = (post.confidence or 0.5) * 10.0
        return (citation * 0.6 + confidence * 0.4), "citation_fallback"

    return 5.0, "engagement_fallback"


def score_post(
    post: Post,
    *,
    profile: dict[str, Any],
    weights: dict[str, float],
    now: datetime | None = None,
) -> ScoreBreakdown:
    now = now or datetime.now(timezone.utc)
    metrics_available = (
        isinstance(post, StructuredPost) and post.metrics is not None and bool(post.metrics)
    )

    importance, method = _importance_with_fallback(post, metrics_available)
    novelty = _novelty_score(post, now)
    career, career_rationale = _career_relevance(post, profile)
    note = _note_fit(post)
    x = _x_fit(post)

    total = (
        importance * weights.get("importance", 0.3)
        + novelty * weights.get("novelty", 0.2)
        + career * weights.get("career_relevance", 0.2)
        + note * weights.get("note_fit", 0.15)
        + x * weights.get("x_fit", 0.15)
    )

    return ScoreBreakdown(
        importance=round(importance, 2),
        novelty=round(novelty, 2),
        career_relevance=round(career, 2),
        note_fit=round(note, 2),
        x_fit=round(x, 2),
        total=round(total, 2),
        method=method,  # type: ignore[arg-type]
        rationale=career_rationale,
    )


def score_all(
    posts: list[Post],
    *,
    profile: dict[str, Any],
    weights: dict[str, float],
    now: datetime | None = None,
) -> list[ScoredItem]:
    return [
        ScoredItem(post=p, score=score_post(p, profile=profile, weights=weights, now=now))
        for p in posts
    ]


def top_n(items: list[ScoredItem], n: int = 10) -> list[ScoredItem]:
    return sorted(items, key=lambda x: x.score.total, reverse=True)[:n]
