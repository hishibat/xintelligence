"""ui.logic — pure logic tests (no Streamlit import)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.logic import (
    BROAD_TOPICS,
    LLM_PROVIDERS,
    PROVIDERS,
    REVIEW_BUCKETS,
    SEARCH_FALLBACKS,
    TIME_RANGES,
    TOPICS,
    build_run_command,
    build_run_command_custom,
    classify_citationless_ratio,
    compute_run_warnings,
    is_hermes_timeout_failure,
    latest_run_date,
    list_bucket,
    list_drafts,
    list_run_dates,
    list_video_prompts,
    load_manifest,
    load_report_md,
    manifest_summary,
    move_draft_to_bucket,
    review_queue_paths,
)


# ---------------------------------------------------------------- fixtures


def _make_outputs(tmp_path: Path, date: str = "2026-05-22") -> Path:
    """Build a realistic outputs/ tree under tmp_path."""
    outputs = tmp_path / "outputs"
    daily = outputs / "daily_reports" / date
    daily.mkdir(parents=True)
    drafts = outputs / "content_drafts" / date
    drafts.mkdir(parents=True)
    video = outputs / "video_prompts" / date
    video.mkdir(parents=True)
    rq = outputs / "review_queue" / date
    rq.mkdir(parents=True)

    (daily / "report.md").write_text("# Report\nhello", encoding="utf-8")
    (daily / "run_manifest.json").write_text(
        json.dumps({
            "run_id": "test_run",
            "provider": "hermes",
            "llm_provider": "claude",
            "citationless_ratio": 0.0,
            "citationless_items_count": 0,
            "fallback_used": [],
            "warnings": [],
            "topics_with_high_citationless_ratio": [],
        }),
        encoding="utf-8",
    )
    (drafts / "01_x_post.md").write_text("x post draft", encoding="utf-8")
    (drafts / "02_x_thread.md").write_text("x thread draft", encoding="utf-8")
    (video / "01_note_header.md").write_text("video prompt", encoding="utf-8")
    (rq / "drafts_to_review.md").write_text("review list", encoding="utf-8")
    return outputs


# ---------------------------------------------------------------- list dates


def test_list_run_dates_returns_newest_first(tmp_path):
    out = tmp_path / "outputs" / "daily_reports"
    for d in ("2026-05-20", "2026-05-22", "2026-05-21"):
        (out / d).mkdir(parents=True)
    assert list_run_dates(tmp_path) == ["2026-05-22", "2026-05-21", "2026-05-20"]


def test_list_run_dates_empty_when_no_outputs(tmp_path):
    assert list_run_dates(tmp_path) == []


def test_list_run_dates_ignores_non_date_dirs(tmp_path):
    out = tmp_path / "outputs" / "daily_reports"
    for d in ("2026-05-22", "examples", "scratch", "x-y-z"):
        (out / d).mkdir(parents=True)
    assert list_run_dates(tmp_path) == ["2026-05-22"]


def test_latest_run_date(tmp_path):
    out = tmp_path / "outputs" / "daily_reports"
    (out / "2026-05-22").mkdir(parents=True)
    (out / "2026-05-21").mkdir(parents=True)
    assert latest_run_date(tmp_path) == "2026-05-22"


def test_latest_run_date_none_when_empty(tmp_path):
    assert latest_run_date(tmp_path) is None


# ---------------------------------------------------------------- load


def test_load_manifest_and_report(tmp_path):
    _make_outputs(tmp_path)
    m = load_manifest("2026-05-22", outputs_root=tmp_path)
    assert m["provider"] == "hermes"
    r = load_report_md("2026-05-22", outputs_root=tmp_path)
    assert r.startswith("# Report")


def test_load_manifest_missing_returns_none(tmp_path):
    assert load_manifest("nope", outputs_root=tmp_path) is None
    assert load_report_md("nope", outputs_root=tmp_path) is None


# ---------------------------------------------------------------- listings


def test_list_drafts(tmp_path):
    _make_outputs(tmp_path)
    ds = list_drafts("2026-05-22", outputs_root=tmp_path)
    assert [d.name for d in ds] == ["01_x_post.md", "02_x_thread.md"]


def test_list_drafts_empty(tmp_path):
    assert list_drafts("nope", outputs_root=tmp_path) == []


def test_list_video_prompts(tmp_path):
    _make_outputs(tmp_path)
    vs = list_video_prompts("2026-05-22", outputs_root=tmp_path)
    assert [v.name for v in vs] == ["01_note_header.md"]


# ---------------------------------------------------------------- move


def test_move_draft_to_bucket_moves_file(tmp_path):
    _make_outputs(tmp_path)
    src = tmp_path / "outputs" / "content_drafts" / "2026-05-22" / "01_x_post.md"
    dest = move_draft_to_bucket(
        src, date_str="2026-05-22", bucket="approved", outputs_root=tmp_path
    )
    assert dest.exists()
    assert dest.name == "01_x_post.md"
    assert dest.parent.name == "approved"
    assert not src.exists()  # original moved


@pytest.mark.parametrize("bucket", REVIEW_BUCKETS)
def test_move_to_each_valid_bucket(tmp_path, bucket):
    _make_outputs(tmp_path)
    src = tmp_path / "outputs" / "content_drafts" / "2026-05-22" / "01_x_post.md"
    dest = move_draft_to_bucket(src, date_str="2026-05-22", bucket=bucket, outputs_root=tmp_path)
    assert dest.parent.name == bucket


def test_move_draft_invalid_bucket_raises(tmp_path):
    _make_outputs(tmp_path)
    src = tmp_path / "outputs" / "content_drafts" / "2026-05-22" / "01_x_post.md"
    with pytest.raises(ValueError):
        move_draft_to_bucket(
            src, date_str="2026-05-22", bucket="not_a_bucket", outputs_root=tmp_path
        )


def test_move_missing_source_raises(tmp_path):
    _make_outputs(tmp_path)
    with pytest.raises(FileNotFoundError):
        move_draft_to_bucket(
            tmp_path / "nonexistent.md",
            date_str="2026-05-22", bucket="approved", outputs_root=tmp_path,
        )


def test_list_bucket_after_move(tmp_path):
    _make_outputs(tmp_path)
    src = tmp_path / "outputs" / "content_drafts" / "2026-05-22" / "01_x_post.md"
    move_draft_to_bucket(src, date_str="2026-05-22", bucket="approved", outputs_root=tmp_path)
    files = list_bucket("2026-05-22", "approved", outputs_root=tmp_path)
    assert [f.name for f in files] == ["01_x_post.md"]


# ---------------------------------------------------------------- run cmd


def test_build_run_command_includes_all_flags():
    cmd = build_run_command(
        provider="mock",
        llm_provider="mock",
        search_fallback="none",
        topic="claude_code",
        date_str="2026-05-22",
    )
    assert "--provider" in cmd and "mock" in cmd
    assert "--llm-provider" in cmd
    assert "--search-fallback" in cmd and "none" in cmd
    assert "--topic" in cmd and "claude_code" in cmd
    assert "--date" in cmd and "2026-05-22" in cmd


def test_build_run_command_optional_date():
    cmd = build_run_command(
        provider="mock", llm_provider="mock",
        search_fallback="none", topic="ai_agents",
    )
    assert "--date" not in cmd


@pytest.mark.parametrize("bad", [
    {"provider": "bad", "llm_provider": "mock", "search_fallback": "none", "topic": "claude_code"},
    {"provider": "mock", "llm_provider": "bad", "search_fallback": "none", "topic": "claude_code"},
    {"provider": "mock", "llm_provider": "mock", "search_fallback": "bad", "topic": "claude_code"},
    {"provider": "mock", "llm_provider": "mock", "search_fallback": "none", "topic": "bad_topic"},
])
def test_build_run_command_validates_choices(bad):
    with pytest.raises(ValueError):
        build_run_command(**bad)


def test_build_run_command_does_NOT_include_posting_flags():
    """Belt-and-suspenders: ensure no posting flag can slip in."""
    cmd = build_run_command(
        provider="mock", llm_provider="mock",
        search_fallback="none", topic="claude_code",
    )
    forbidden = ["--post", "--publish", "--send", "--tweet", "--share"]
    for f in forbidden:
        assert f not in cmd


# ---------------------------------------------------------------- time_range


@pytest.mark.parametrize("tr", TIME_RANGES)
def test_build_run_command_accepts_each_time_range(tr):
    cmd = build_run_command(
        provider="mock", llm_provider="mock",
        search_fallback="none", topic="claude_code",
        time_range=tr,
    )
    assert "--time-range" in cmd
    assert tr in cmd


def test_build_run_command_omits_time_range_when_none():
    cmd = build_run_command(
        provider="mock", llm_provider="mock",
        search_fallback="none", topic="claude_code",
        time_range=None,
    )
    assert "--time-range" not in cmd


def test_build_run_command_rejects_invalid_time_range():
    with pytest.raises(ValueError, match="time_range"):
        build_run_command(
            provider="mock", llm_provider="mock",
            search_fallback="none", topic="claude_code",
            time_range="14d",
        )


@pytest.mark.parametrize("tr", TIME_RANGES)
def test_build_run_command_custom_accepts_each_time_range(tr):
    cmd = build_run_command_custom(
        provider="mock", llm_provider="mock",
        search_fallback="none",
        custom_query="enterprise AI rollout patterns",
        time_range=tr,
    )
    assert "--time-range" in cmd
    assert tr in cmd


def test_time_ranges_constant():
    assert TIME_RANGES == ["24h", "3d", "7d"]


# ---------------------------------------------------------------- pre-run warnings


def test_compute_run_warnings_24h_returns_nothing():
    ws = compute_run_warnings(
        provider="hermes", search_fallback="none",
        topic="claude_code", time_range="24h",
    )
    assert ws == []


def test_compute_run_warnings_24h_with_broad_topic_still_silent():
    # 24h is fast regardless of topic breadth → no warning expected
    ws = compute_run_warnings(
        provider="hermes", search_fallback="none",
        topic="enterprise_ai_adoption", time_range="24h",
    )
    assert ws == []


def test_compute_run_warnings_3d_emits_info_only():
    ws = compute_run_warnings(
        provider="hermes", search_fallback="none",
        topic="claude_code", time_range="3d",
    )
    severities = [w["severity"] for w in ws]
    assert "info" in severities
    assert "warning" not in severities
    assert any("3d" in w["message"] for w in ws)
    assert any("mock" in w["message"] for w in ws)


def test_compute_run_warnings_7d_emits_warning():
    ws = compute_run_warnings(
        provider="hermes", search_fallback="mock",
        topic="claude_code", time_range="7d",
    )
    severities = [w["severity"] for w in ws]
    assert "warning" in severities
    assert any("HERMES_TIMEOUT_SECONDS" in w["message"] for w in ws)


def test_compute_run_warnings_7d_fail_loud_hermes_critical_near_run_button():
    ws = compute_run_warnings(
        provider="hermes", search_fallback="none",
        topic="claude_code", time_range="7d",
    )
    run_btn_warnings = [w for w in ws if w["location"] == "run_button"]
    assert len(run_btn_warnings) == 1
    msg = run_btn_warnings[0]["message"]
    assert "Fail-loud" in msg or "fail-loud" in msg
    assert "mock" in msg
    assert run_btn_warnings[0]["severity"] == "warning"


def test_compute_run_warnings_7d_fail_loud_mock_provider_omits_critical():
    # mock provider has no Hermes timeout risk → critical warning is suppressed
    ws = compute_run_warnings(
        provider="mock", search_fallback="none",
        topic="claude_code", time_range="7d",
    )
    run_btn_warnings = [w for w in ws if w["location"] == "run_button"]
    assert run_btn_warnings == []
    # but the generic 7d sidebar warning is still there
    assert any(w["location"] == "sidebar" for w in ws)


def test_compute_run_warnings_7d_fallback_mock_omits_critical():
    ws = compute_run_warnings(
        provider="hermes", search_fallback="mock",
        topic="claude_code", time_range="7d",
    )
    run_btn_warnings = [w for w in ws if w["location"] == "run_button"]
    assert run_btn_warnings == []


@pytest.mark.parametrize("topic", sorted(BROAD_TOPICS))
def test_compute_run_warnings_broad_topic_7d_adds_extra(topic: str):
    ws = compute_run_warnings(
        provider="hermes", search_fallback="mock",
        topic=topic, time_range="7d",
    )
    msgs = [w["message"] for w in ws]
    assert any(topic in m and "broad" in m.lower() for m in msgs)


def test_compute_run_warnings_narrow_topic_7d_no_broad_extra():
    # claude_code is NOT in BROAD_TOPICS — broad-topic addendum must not fire.
    # (The generic 7d warning mentions "broad topics" in passing; the
    # addendum is the one that mentions the topic NAME and "broad keywords".)
    ws = compute_run_warnings(
        provider="hermes", search_fallback="mock",
        topic="claude_code", time_range="7d",
    )
    assert not any("claude_code" in w["message"] for w in ws)
    assert not any("broad keywords" in w["message"] for w in ws)


def test_compute_run_warnings_custom_topic_none_no_broad_check():
    # Custom mode passes topic=None — broad check must not fire
    ws = compute_run_warnings(
        provider="hermes", search_fallback="mock",
        topic=None, time_range="7d",
    )
    # generic 7d sidebar warning still appears
    assert any(w["location"] == "sidebar" for w in ws)
    # but the broad-topic addendum (signature phrase "broad keywords") does not
    assert not any("broad keywords" in w["message"] for w in ws)


# ---------------------------------------------------------------- timeout detector


def test_is_hermes_timeout_failure_detects_realistic_stderr():
    stderr = (
        "[INFO] x-intelligence: provider=hermes llm=claude topic=enterprise_ai_adoption\n"
        "[WARNING] x-intelligence: Hermes failed: Hermes timed out after 180s\n"
        "[ERROR] x-intelligence: search provider failed (fail-loud mode)"
    )
    assert is_hermes_timeout_failure(stderr) is True


def test_is_hermes_timeout_failure_false_for_other_errors():
    assert is_hermes_timeout_failure("Some unrelated SDK error") is False
    assert is_hermes_timeout_failure("") is False
    assert is_hermes_timeout_failure(None or "") is False


def test_is_hermes_timeout_failure_false_when_only_hermes_or_only_timeout():
    # mentioning Hermes alone (no timeout) → not the timeout case
    assert is_hermes_timeout_failure("Hermes returned 0 items") is False
    # timeout in some other tool, not Hermes → not the timeout case
    assert is_hermes_timeout_failure("requests.exceptions.Timeout: read timed out") is False


# ---------------------------------------------------------------- display


def test_classify_citationless_ratio_thresholds():
    assert "🟢" in classify_citationless_ratio(0.0)
    assert "🟢" in classify_citationless_ratio(0.19)
    assert "🟡" in classify_citationless_ratio(0.20)
    assert "🟡" in classify_citationless_ratio(0.49)
    assert "🔴" in classify_citationless_ratio(0.50)
    assert "🔴" in classify_citationless_ratio(1.0)
    assert classify_citationless_ratio(None) == "—"


def test_manifest_summary_is_clean():
    m = {
        "run_id": "x",
        "provider": "hermes",
        "llm_provider": "claude",
        "citationless_ratio": 0.0,
        "fallback_used": [],
        "warnings": [],
        "topics_with_high_citationless_ratio": [],
    }
    s = manifest_summary(m)
    assert s["is_clean"] is True


def test_manifest_summary_dirty_on_any_issue():
    base = {
        "run_id": "x", "provider": "p", "llm_provider": "l",
        "citationless_ratio": 0.0,
        "fallback_used": [], "warnings": [], "topics_with_high_citationless_ratio": [],
    }
    for dirty in [
        {**base, "fallback_used": ["search:hermes->mock"]},
        {**base, "warnings": ["something"]},
        {**base, "topics_with_high_citationless_ratio": ["frontier_models"]},
    ]:
        assert manifest_summary(dirty)["is_clean"] is False


# ---------------------------------------------------------------- constants


def test_constants_match_runtime_choices():
    """Sanity check: UI's whitelist must match run_daily.py argparse choices."""
    # Mirror the CLI argparse choices defined in scripts/run_daily.py
    assert PROVIDERS == ["mock", "hermes"]
    assert LLM_PROVIDERS == ["mock", "claude"]
    assert SEARCH_FALLBACKS == ["none", "mock"]
    assert REVIEW_BUCKETS == ["approved", "rejected", "needs_fact_check"]
    assert "claude_code" in TOPICS
    assert "multi_agent_systems" in TOPICS
    assert "frontier_models" in TOPICS
    assert "ai_agents" in TOPICS
    assert "ai_infrastructure" in TOPICS
    assert "data_platforms" in TOPICS
    assert "ai_governance" in TOPICS
    assert "enterprise_ai_adoption" in TOPICS
    assert len(TOPICS) == 8
