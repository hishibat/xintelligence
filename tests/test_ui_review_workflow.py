"""ui.logic — review workflow (draft parse / feedback log / topic suggest /
custom query / latest-run helpers)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.logic import (
    REASON_TAGS,
    build_run_command_custom,
    feedback_log_path,
    latest_review_for_draft,
    parse_draft_md,
    read_review_log,
    save_review_action,
    suggest_topics,
)


# ---------------------------------------------------------------- helpers

DRAFT_MD = """# x_post draft (insightful)

- needs_review: **True**
- originality_note: LLM draft. 自分の切り口を1要素以上加えること前提。

## source_urls
- https://x.com/NousResearch/status/123
- https://x.com/elonmusk/status/456
- https://x.com/anthropicai/status/789

## source_summary
Hermes Agent v2.1 was released, with multi-provider OAuth.

## my_angle
柴田さんの注力領域 [Hermes Agent] と関連。consulting / GTM 視点で押したい。

## draft_text
Hermes Agent v2.1の本質は「マルチプロバイダを同一セッションで束ねる」点。
"""


def _write_draft(tmp_path: Path, date: str = "2026-05-22") -> Path:
    d = tmp_path / "outputs" / "content_drafts" / date
    d.mkdir(parents=True)
    p = d / "01_x_post.md"
    p.write_text(DRAFT_MD, encoding="utf-8")
    return p


# ---------------------------------------------------------------- parse_draft_md


def test_parse_draft_md_extracts_all_sections(tmp_path):
    p = _write_draft(tmp_path)
    parsed = parse_draft_md(p)
    assert parsed["name"] == "01_x_post.md"
    assert parsed["stem"] == "01_x_post"
    assert parsed["channel"] == "x_post"
    assert parsed["needs_review"] is True
    assert "丸写し禁止" in parsed["originality_note"] or "自分の切り口" in parsed["originality_note"]
    assert len(parsed["source_urls"]) == 3
    assert all(u.startswith("https://x.com/") for u in parsed["source_urls"])
    assert "multi-provider OAuth" in parsed["source_summary"]
    assert "柴田" in parsed["my_angle"]
    assert "マルチプロバイダ" in parsed["draft_text"]
    assert parsed["char_count"] > 0


def test_parse_draft_md_char_count_matches_draft_text(tmp_path):
    p = _write_draft(tmp_path)
    parsed = parse_draft_md(p)
    assert parsed["char_count"] == len(parsed["draft_text"])


def test_parse_draft_md_handles_missing_sections(tmp_path):
    # Draft with only draft_text section
    p = tmp_path / "minimal.md"
    p.write_text(
        "# x_post draft\n\n- needs_review: **True**\n\n## draft_text\nbody",
        encoding="utf-8",
    )
    parsed = parse_draft_md(p)
    assert parsed["draft_text"] == "body"
    assert parsed["source_urls"] == []
    assert parsed["source_summary"] == ""


# ---------------------------------------------------------------- feedback log


def test_save_review_action_appends_jsonl(tmp_path):
    _write_draft(tmp_path)
    entry = save_review_action(
        date_str="2026-05-22",
        draft_file="01_x_post.md",
        review_status="approved",
        feedback_text="Great hook, ship it.",
        reason_tags=["angle_good", "ready_to_post"],
        outputs_root=tmp_path,
    )
    assert entry["review_status"] == "approved"
    assert entry["reason_tags"] == ["angle_good", "ready_to_post"]
    log = feedback_log_path("2026-05-22", outputs_root=tmp_path)
    assert log.exists()
    content = log.read_text(encoding="utf-8")
    assert "01_x_post.md" in content
    # Each entry is a JSON line
    line = content.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["draft_file"] == "01_x_post.md"


def test_save_multiple_actions_appends_in_order(tmp_path):
    for status in ("feedback_only", "needs_fact_check", "approved"):
        save_review_action(
            date_str="2026-05-22",
            draft_file="01_x_post.md",
            review_status=status,
            feedback_text=f"note for {status}",
            reason_tags=[],
            outputs_root=tmp_path,
        )
    entries = read_review_log("2026-05-22", outputs_root=tmp_path)
    assert [e["review_status"] for e in entries] == ["feedback_only", "needs_fact_check", "approved"]


def test_save_review_action_validates_status(tmp_path):
    with pytest.raises(ValueError):
        save_review_action(
            date_str="2026-05-22", draft_file="x.md",
            review_status="published",  # not allowed — never publish
            outputs_root=tmp_path,
        )


def test_save_review_action_validates_reason_tags(tmp_path):
    with pytest.raises(ValueError):
        save_review_action(
            date_str="2026-05-22", draft_file="x.md",
            review_status="approved",
            reason_tags=["made_up_tag"],
            outputs_root=tmp_path,
        )


def test_latest_review_for_draft_returns_most_recent(tmp_path):
    for status in ("feedback_only", "rejected", "approved"):
        save_review_action(
            date_str="2026-05-22", draft_file="01_x_post.md",
            review_status=status, outputs_root=tmp_path,
        )
    latest = latest_review_for_draft("2026-05-22", "01_x_post.md", outputs_root=tmp_path)
    assert latest is not None
    assert latest["review_status"] == "approved"


def test_latest_review_returns_none_for_unknown(tmp_path):
    save_review_action(
        date_str="2026-05-22", draft_file="other.md",
        review_status="approved", outputs_root=tmp_path,
    )
    assert latest_review_for_draft("2026-05-22", "absent.md", outputs_root=tmp_path) is None


def test_reason_tags_constant_complete():
    for must_have in (
        "hook_weak", "not_buzzy", "needs_fact_check", "angle_good",
        "ready_to_post", "rewrite_needed",
    ):
        assert must_have in REASON_TAGS


# ---------------------------------------------------------------- topic suggest


def test_suggest_topics_keyword_overlap():
    suggestions = suggest_topics("AI agents for enterprise sales")
    assert "ai_agent" in suggestions


def test_suggest_topics_grok_mentions():
    suggestions = suggest_topics("Grok agent automation")
    assert "grok_xai" in suggestions
    assert "ai_agent" in suggestions


def test_suggest_topics_databricks_governance():
    suggestions = suggest_topics("Databricks governance and lineage")
    # Should suggest at least one of these two
    assert any(t in suggestions for t in ("ai_governance_data", "ai_infra_vendors"))


def test_suggest_topics_empty_input():
    assert suggest_topics("") == []
    assert suggest_topics(None or "") == []


def test_suggest_topics_no_overlap():
    assert suggest_topics("xxxxx unrelated zzzzz") == []


def test_suggest_topics_limits_to_k():
    # 7+ keyword overlap → still capped at k
    suggestions = suggest_topics(
        "claude hermes grok agent nvidia copilot databricks", k=3
    )
    assert len(suggestions) <= 3


# ---------------------------------------------------------------- custom query cmd


def test_build_run_command_custom_includes_flags():
    cmd = build_run_command_custom(
        provider="mock", llm_provider="mock", search_fallback="none",
        custom_query="AI agents in Japan", date_str="2026-05-22",
    )
    assert "--custom-query" in cmd
    assert "AI agents in Japan" in cmd
    assert "--custom-topic-id" in cmd
    assert "--provider" in cmd and "mock" in cmd
    assert "--date" in cmd and "2026-05-22" in cmd
    # Must NOT include --topic (that's mutually exclusive with --custom-query)
    assert "--topic" not in cmd


def test_build_run_command_custom_rejects_empty_query():
    with pytest.raises(ValueError):
        build_run_command_custom(
            provider="mock", llm_provider="mock", search_fallback="none",
            custom_query="",
        )
    with pytest.raises(ValueError):
        build_run_command_custom(
            provider="mock", llm_provider="mock", search_fallback="none",
            custom_query="   ",
        )


def test_build_run_command_custom_validates_provider():
    with pytest.raises(ValueError):
        build_run_command_custom(
            provider="bad", llm_provider="mock", search_fallback="none",
            custom_query="x",
        )


def test_build_run_command_custom_NEVER_contains_posting_flags():
    cmd = build_run_command_custom(
        provider="mock", llm_provider="mock", search_fallback="none",
        custom_query="anything",
    )
    for f in ("--post", "--publish", "--send", "--tweet", "--share"):
        assert f not in cmd
