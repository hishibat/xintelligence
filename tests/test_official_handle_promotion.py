"""verification.tag_items() — source_type promotion from handle registry.

When a post's URL handle matches `config/official_handles.yaml`, the
source_type should be upgraded to the strongest tier that matches.
"""
from __future__ import annotations

from src.core.schema import (
    SearchCitationResult,
    StructuredPost,
    VerificationTags,
)
from src.core.verification import (
    _build_handle_index,
    _resolve_source_type,
    tag_items,
)


HANDLES_CFG = {
    "official": ["NousResearch", "xai", "AnthropicAI"],
    "founder_executive": ["elonmusk", "sama"],
    "engineer_dev": ["simonw"],
    "media": ["gartner_inc"],
    "influencer": ["linusekenstam"],
}


def test_build_handle_index_lowercases_and_strips_at():
    idx = _build_handle_index({"official": ["@xai", "NousResearch"]})
    assert idx == {"xai": "official", "nousresearch": "official"}


def test_higher_tier_wins_on_duplicate_listing():
    cfg = {
        "official": ["dualhandle"],
        "founder_executive": ["dualhandle"],
    }
    idx = _build_handle_index(cfg)
    assert idx["dualhandle"] == "official"


def test_resolve_for_structured_post_with_author_handle():
    p = StructuredPost(
        post_id="1", text="x", url="https://x.com/NousResearch/status/123",
        author_handle="@NousResearch", provider_name="mock",
        verification=VerificationTags(),
    )
    idx = _build_handle_index(HANDLES_CFG)
    assert _resolve_source_type(p, idx) == "official"


def test_resolve_for_citation_result_with_multiple_urls():
    cr = SearchCitationResult(
        summary="x", provider_name="hermes",
        cited_urls=[
            "https://x.com/elonmusk/status/1",       # founder_executive
            "https://x.com/NousResearch/status/2",   # official ← wins
            "https://x.com/simonw/status/3",         # engineer_dev
        ],
        verification=VerificationTags(),
    )
    idx = _build_handle_index(HANDLES_CFG)
    assert _resolve_source_type(cr, idx) == "official"


def test_tag_items_promotes_source_type_for_official_handle():
    cr = SearchCitationResult(
        summary="x", provider_name="hermes",
        cited_urls=["https://x.com/NousResearch/status/123"],
        verification=VerificationTags(source_type="unknown"),
    )
    tag_items([cr], official_handles=HANDLES_CFG)
    assert cr.verification.source_type == "official"
    assert cr.verification.verification_status == "official_source_confirmed"


def test_tag_items_no_change_when_handle_not_listed():
    cr = SearchCitationResult(
        summary="x", provider_name="hermes",
        cited_urls=["https://x.com/some_random_user/status/9"],
        verification=VerificationTags(source_type="unknown"),
    )
    tag_items([cr], official_handles=HANDLES_CFG)
    assert cr.verification.source_type == "unknown"
    # multi_source_confirmed もしないはず (cited_urls=1 件のため)
    assert cr.verification.verification_status in ("unverified",)


def test_tag_items_works_without_handles_config():
    cr = SearchCitationResult(
        summary="x", provider_name="hermes",
        cited_urls=["https://x.com/NousResearch/status/123"],
        verification=VerificationTags(source_type="unknown"),
    )
    # No handles config — should not promote
    tag_items([cr], official_handles=None)
    assert cr.verification.source_type == "unknown"
