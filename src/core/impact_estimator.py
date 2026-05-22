"""Rule-based impact estimator for content drafts.

Produces a 1-10 score and band labels (low/medium/high) without calling
any LLM, so the UI can surface a quick "what might this post do" hint
on each draft without extra API token cost.

IMPORTANT: This is **estimated** / **simulation only**. Do NOT present
the score as an actual impression prediction. Real impressions can only
come from post-publish analytics (future feature).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


HOOK_PATTERNS_JA = [
    "なぜ", "実は", "意外", "知ってる", "結論", "残念", "やばい", "ここで", "前提",
]
HOOK_PATTERNS_EN = [
    "why ", "what if", "the real reason", "ranked", "best ", "worst ",
    "you might", "stop ", "here's why", "the truth", "secret",
]
URL_PATTERN = re.compile(r"https?://\S+")


@dataclass
class ImpactEstimate:
    estimated_impact_score: float            # 1.0-10.0
    virality_potential: str                  # low | medium | high
    expected_impression_band: str            # low | medium | high
    confidence: str                          # low | medium | high
    reasoning: list[str] = field(default_factory=list)
    disclaimer: str = (
        "Estimated values only — not a guarantee of actual impressions. "
        "Refine with real post-publish analytics."
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _count_hooks(text: str) -> int:
    lower = text.lower()
    n = sum(1 for h in HOOK_PATTERNS_EN if h in lower)
    n += sum(1 for h in HOOK_PATTERNS_JA if h in text)
    return n


def estimate_impact(
    *,
    channel: str,
    draft_text: str,
    source_url_count: int = 0,
    has_official_source: bool = False,
    has_founder_source: bool = False,
    topic: str = "",
    citationless_ratio: float = 0.0,
) -> ImpactEstimate:
    """Compute a rule-based impact estimate. No LLM calls.

    Inputs are intentionally narrow: things we can derive from a single
    ContentDraft + the surrounding RunManifest signals.
    """
    score = 5.0  # neutral baseline
    reasoning: list[str] = []

    # ---- Source credibility ----------------------------------------
    if source_url_count >= 3:
        score += 1.0
        reasoning.append(f"Source credibility: {source_url_count} URLs (strong backing)")
    elif source_url_count >= 1:
        score += 0.3
        reasoning.append(f"Source credibility: {source_url_count} URL(s)")
    else:
        score -= 1.5
        reasoning.append("Source credibility: NO source URLs (claims unverifiable)")

    if has_official_source:
        score += 0.8
        reasoning.append("Official-source citation present")
    if has_founder_source:
        score += 0.5
        reasoning.append("Founder/executive citation present")

    # ---- Hook strength ---------------------------------------------
    opening = draft_text[:200]
    hooks = _count_hooks(opening)
    if hooks >= 2:
        score += 1.0
        reasoning.append(f"Hook: {hooks} attention pattern(s) in opening 200 chars")
    elif hooks == 1:
        score += 0.4
        reasoning.append("Hook: 1 attention pattern in opening")
    else:
        score -= 0.4
        reasoning.append("Hook: weak — no strong opening pattern")

    # ---- Length appropriateness per channel -------------------------
    chars = len(draft_text)
    if channel == "x_post":
        if 80 <= chars <= 180:
            score += 0.5
            reasoning.append(f"Length: ideal X post ({chars} chars)")
        elif chars > 220:
            score -= 0.5
            reasoning.append(f"Length: too long for X post ({chars} chars)")
        elif chars < 50:
            score -= 0.8
            reasoning.append(f"Length: too short for X post ({chars} chars)")
    elif channel == "x_thread":
        # threads benefit from substance
        if chars >= 600:
            score += 0.5
            reasoning.append(f"Length: substantive thread ({chars} chars)")
    elif channel == "linkedin":
        # rough word count via whitespace split
        words = len(re.findall(r"\S+", draft_text))
        if 600 <= words <= 900:
            score += 0.5
            reasoning.append(f"Length: standard LinkedIn essay ({words} words)")
        elif words > 1500:
            score -= 0.3
            reasoning.append(f"Length: long for LinkedIn ({words} words)")
    elif channel == "note_outline":
        # Outline drafts score for structural completeness
        if chars >= 500 and "## " in draft_text:
            score += 0.5
            reasoning.append("Structure: outline with headings present")

    # ---- Topic-level signals ---------------------------------------
    if topic == "frontier_models" and source_url_count == 0:
        score -= 1.0
        reasoning.append("Topic risk: frontier_models self-referential without sources")

    if citationless_ratio >= 0.5:
        score -= 0.8
        reasoning.append(
            f"Run quality: citationless_ratio={citationless_ratio*100:.0f}% (run-wide signal)"
        )

    # ---- Originality cues -------------------------------------------
    if any(marker in draft_text for marker in ("自分の解釈", "私の", "柴田", "タイ在住", "from where I sit")):
        score += 0.4
        reasoning.append("Originality: personal angle markers detected")

    # ---- URL leakage in body (low credibility for X posts) ----------
    body_urls = URL_PATTERN.findall(draft_text)
    if channel == "x_post" and len(body_urls) > 2:
        score -= 0.3
        reasoning.append("Format: many URLs inline (consider extracting to Sources)")

    # Clip to [1.0, 10.0]
    score = max(1.0, min(10.0, score))

    # ---- Bands ------------------------------------------------------
    if score >= 7.5:
        virality, band = "high", "high"
    elif score >= 5.0:
        virality, band = "medium", "medium"
    else:
        virality, band = "low", "low"

    # Confidence is always "low" for rule-based until we have post-publish
    # analytics calibration.
    confidence = "low"

    return ImpactEstimate(
        estimated_impact_score=round(score, 1),
        virality_potential=virality,
        expected_impression_band=band,
        confidence=confidence,
        reasoning=reasoning,
    )
