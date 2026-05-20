from src.adapters.llm_mock import MockLLMProvider
from src.core.content_generator import generate_drafts, _too_similar
from src.core.schema import ScoreBreakdown, ScoredItem, StructuredPost, VerificationTags
from src.utils.config_loader import load_config


def _scored(text: str):
    post = StructuredPost(
        post_id="x1", text=text, url="https://x.com/x/1", provider_name="mock",
        verification=VerificationTags(),
    )
    return ScoredItem(post=post, score=ScoreBreakdown(5, 5, 5, 5, 5, 5))


def test_drafts_have_required_originality_fields():
    cfg = load_config()
    drafts = generate_drafts(
        [_scored("Agents in production look more like SREs than geniuses.")],
        profile=cfg.profile,
        tones=["insightful"],
        channels=["x_post", "x_thread", "note_outline", "linkedin"],
        llm=MockLLMProvider(),
        per_channel=1,
    )
    assert drafts, "expected at least one draft per channel"
    for d in drafts:
        assert d.source_urls, "source_urls must be preserved"
        assert d.source_summary
        assert d.my_angle
        assert d.originality_note
        assert d.needs_review is True


def test_too_similar_detects_verbatim():
    src = "Agents in production look more like SREs than geniuses."
    near = "Agents in production look more like SREs than geniuses."
    far = "本番運用ではSRE的な振る舞いが効くという指摘。"
    assert _too_similar(src, near) is True
    assert _too_similar(src, far) is False
