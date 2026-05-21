"""Standard data schemas shared across adapters, core, and scripts.

Two post shapes are supported to absorb provider granularity differences:

    StructuredPost          — X API / mock: full per-post fields
    SearchCitationResult    — Hermes / xAI x_search: summary + citations

ScoreBreakdown carries the per-axis scores and total. ContentDraft and
VideoPrompt carry their own originality guard / bilingual fields.

RunManifest captures a single orchestrator run for reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Literal


VerificationStatus = Literal[
    "unverified",
    "single_source",
    "multi_source_confirmed",
    "official_source_confirmed",
    "needs_manual_check",
]

SourceType = Literal[
    "official",
    "founder_executive",
    "engineer_dev",
    "media",
    "influencer",
    "unknown",
]

RiskFlag = Literal[
    "rumor",
    "hype",
    "investment_claim",
    "product_claim",
    "pricing_claim",
    "legal_or_policy_claim",
    "security_claim",
]


@dataclass
class VerificationTags:
    verification_status: VerificationStatus = "unverified"
    source_type: SourceType = "unknown"
    risk_flags: list[RiskFlag] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_status": self.verification_status,
            "source_type": self.source_type,
            "risk_flags": list(self.risk_flags),
        }


@dataclass
class StructuredPost:
    post_id: str
    text: str
    url: str
    provider_name: str
    author: str | None = None
    author_handle: str | None = None
    created_at: datetime | None = None
    metrics: dict[str, int] | None = None
    thread_context: list[str] | None = None
    topic: str | None = None
    verification: VerificationTags = field(default_factory=VerificationTags)
    missing_fields: list[str] = field(default_factory=list)
    kind: Literal["structured_post"] = "structured_post"

    def primary_text(self) -> str:
        return self.text

    def citation_urls(self) -> list[str]:
        return [self.url] if self.url else []

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.created_at is not None:
            d["created_at"] = self.created_at.isoformat()
        d["verification"] = self.verification.to_dict()
        return d


@dataclass
class SearchCitationResult:
    summary: str
    provider_name: str
    cited_urls: list[str] = field(default_factory=list)
    cited_posts: list[dict[str, Any]] = field(default_factory=list)
    provider_response: str = ""
    confidence: float | None = None
    topic: str | None = None
    verification: VerificationTags = field(default_factory=VerificationTags)
    missing_fields: list[str] = field(default_factory=list)
    # v0.3 additions (Hermes adapter): per-item parse signals and a path to
    # the (redacted) raw subprocess output that produced this result.
    parse_warnings: list[str] = field(default_factory=list)
    raw_response_path: str | None = None
    kind: Literal["search_citation_result"] = "search_citation_result"

    def primary_text(self) -> str:
        return self.summary

    def citation_urls(self) -> list[str]:
        return list(self.cited_urls)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verification"] = self.verification.to_dict()
        return d


Post = StructuredPost | SearchCitationResult


@dataclass
class Capabilities:
    supports_raw_post_text: bool
    supports_author: bool
    supports_created_at: bool
    supports_engagement_metrics: bool
    supports_thread_context: bool
    supports_citations: bool
    supports_time_range: bool
    supports_query_operators: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass
class SearchResult:
    provider_name: str
    query: str
    topic: str
    time_range: str
    retrieved_at: datetime
    items: list[Post]
    source_urls: list[str]
    capabilities: Capabilities
    missing_fields: list[str]
    raw_response_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "query": self.query,
            "topic": self.topic,
            "time_range": self.time_range,
            "retrieved_at": self.retrieved_at.isoformat(),
            "items": [item.to_dict() for item in self.items],
            "source_urls": list(self.source_urls),
            "capabilities": self.capabilities.to_dict(),
            "missing_fields": list(self.missing_fields),
            "raw_response_path": self.raw_response_path,
        }


@dataclass
class ScoreBreakdown:
    importance: float
    novelty: float
    career_relevance: float
    note_fit: float
    x_fit: float
    total: float
    method: Literal["full", "engagement_fallback", "citation_fallback", "llm_only"] = "full"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredItem:
    post: Post
    score: ScoreBreakdown
    why_important: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "post": self.post.to_dict(),
            "score": self.score.to_dict(),
            "why_important": self.why_important,
        }


@dataclass
class TrendSummary:
    topic_id: str
    topic_label: str
    time_range: str
    item_count: int
    main_points: list[str]
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    emerging_keywords: list[str]
    short_jp_explanation: str
    content_angles: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContentDraft:
    channel: Literal["x_post", "x_thread", "note_outline", "linkedin"]
    tone: str
    source_urls: list[str]
    source_summary: str
    my_angle: str
    draft_text: str
    originality_note: str
    needs_review: bool = True
    note_title_candidates: list[str] = field(default_factory=list)
    note_outline: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VideoPrompt:
    use_case: Literal["note_header", "x_short", "linkedin_visual", "youtube_shorts"]
    concept: str
    scene: str
    visual_style: str
    camera_movement: str
    text_overlay: str
    color_palette: str
    mood: str
    duration: str
    aspect_ratio: str
    negative_prompt: str
    grok_imagine_prompt_en: str
    jp_explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunManifest:
    run_id: str
    executed_at: datetime
    provider: str
    llm_provider: str
    config_hash: str
    query_count: int
    raw_item_count: int
    deduped_item_count: int
    top10_count: int
    fixture_hash: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missing_fields_summary: dict[str, int] = field(default_factory=dict)
    fallback_used: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["executed_at"] = self.executed_at.isoformat()
        return d
