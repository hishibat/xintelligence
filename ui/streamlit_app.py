"""Streamlit UI for X Intelligence — view, review, and feedback. NO posting.

Launch:
    python -m streamlit run ui/streamlit_app.py

Design philosophy:
- Thin shell over ui.logic. Everything testable goes in ui/logic.py.
- NO posting endpoints. The only network call is the subprocess that
  runs scripts/run_daily.py (which itself does not post).
- All "Move to bucket" buttons perform pure local shutil.move() inside
  outputs/review_queue/<date>/. No external sends.
- Feedback is logged to outputs/review_queue/<date>/feedback_log.jsonl
  (append-only) so we can later analyse why drafts were rejected.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# Make project root importable when launched via `streamlit run ui/...`
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.impact_estimator import estimate_impact  # noqa: E402
from ui.logic import (  # noqa: E402
    LLM_PROVIDERS,
    PROVIDERS,
    REASON_TAGS,
    REVIEW_BUCKETS,
    SEARCH_FALLBACKS,
    TIME_RANGES,
    TOPICS,
    aggregate_high_ratio_topics,
    aggregate_reason_tags,
    aggregate_review_status,
    aggregate_run_history,
    build_run_command,
    build_run_command_custom,
    classify_citationless_ratio,
    latest_review_for_draft,
    list_bucket,
    list_drafts,
    list_run_dates,
    list_video_prompts,
    load_manifest,
    load_report_md,
    manifest_summary,
    move_draft_to_bucket,
    parse_draft_md,
    review_queue_paths,
    save_review_action,
    suggest_topics,
)


# ---------------------------------------------------------------- page setup

st.set_page_config(page_title="X Intelligence", page_icon="🦊", layout="wide")
st.title("🦊 X Intelligence — Review Console")
st.caption(
    "View daily reports, drafts, impact estimates, and classify them with "
    "feedback. **This UI does NOT post anything.** Publishing on X / Note / "
    "LinkedIn is always done manually by you after review."
)

# Session state defaults
if "selected_view_date" not in st.session_state:
    dates_initial = list_run_dates()
    st.session_state.selected_view_date = dates_initial[0] if dates_initial else None
if "last_pipeline_date" not in st.session_state:
    st.session_state.last_pipeline_date = None


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Run a pipeline")

    topic_mode = st.radio(
        "Topic mode",
        ["Preset", "Custom"],
        index=0,
        help=(
            "Preset = pick one of 8 curated topics defined in "
            "config/keywords.yaml. Custom = free-form query passed to the "
            "provider via the --custom-query path."
        ),
    )

    if topic_mode == "Preset":
        topic = st.selectbox("Topic", TOPICS, index=0)
        custom_query = None
    else:
        custom_query = st.text_input(
            "Custom query",
            value="",
            placeholder="e.g. AI agents for enterprise sales",
        )
        suggested = suggest_topics(custom_query) if custom_query else []
        if suggested:
            st.caption("💡 Similar preset topics: " + ", ".join(f"`{t}`" for t in suggested))
        topic = "custom"

    provider = st.selectbox("Provider", PROVIDERS, index=PROVIDERS.index("hermes"))
    llm_provider = st.selectbox(
        "LLM provider", LLM_PROVIDERS, index=LLM_PROVIDERS.index("claude")
    )
    search_fallback = st.selectbox(
        "Search fallback", SEARCH_FALLBACKS, index=SEARCH_FALLBACKS.index("none")
    )
    time_range = st.selectbox(
        "Time range",
        TIME_RANGES,
        index=TIME_RANGES.index("24h"),
        help=(
            "How far back to search. 24h = daily run (default). "
            "3d / 7d = weekly catch-up or topic deep dive. "
            "Passed to the provider via --time-range."
        ),
    )
    run_date_input = st.date_input(
        "Output date label",
        value=datetime.now(timezone.utc).date(),
        help=(
            "The date used to organise outputs under outputs/.../<date>/. "
            "Does NOT affect search recency — that is controlled by Time range above."
        ),
    )
    run_btn = st.button("▶ Run pipeline", type="primary", use_container_width=True)

    st.divider()
    st.header("View")
    existing_dates = list_run_dates()
    if not existing_dates:
        st.caption("⚠️ No run outputs yet. Run a pipeline first.")
    else:
        # Prefer the just-completed pipeline date if any; else latest existing
        default_view = (
            st.session_state.last_pipeline_date
            if st.session_state.last_pipeline_date in existing_dates
            else (st.session_state.selected_view_date or existing_dates[0])
        )
        if default_view not in existing_dates:
            default_view = existing_dates[0]
        st.session_state.selected_view_date = st.selectbox(
            "Run date to view",
            existing_dates,
            index=existing_dates.index(default_view),
        )


# ---------------------------------------------------------------- subprocess

if run_btn:
    try:
        if topic_mode == "Custom":
            if not custom_query or not custom_query.strip():
                st.error("Custom query is empty. Type something in the sidebar text input.")
                st.stop()
            cmd = build_run_command_custom(
                provider=provider,
                llm_provider=llm_provider,
                search_fallback=search_fallback,
                custom_query=custom_query,
                custom_topic_id="custom",
                date_str=str(run_date_input),
                time_range=time_range,
            )
        else:
            cmd = build_run_command(
                provider=provider,
                llm_provider=llm_provider,
                search_fallback=search_fallback,
                topic=topic,
                date_str=str(run_date_input),
                time_range=time_range,
            )
    except ValueError as e:
        st.error(f"Invalid input: {e}")
        st.stop()

    st.info(
        f"Running: mode={topic_mode}, provider={provider}, llm={llm_provider}, "
        f"fallback={search_fallback}, time_range={time_range}, "
        f"{'topic=' + topic if topic_mode == 'Preset' else 'custom_query=' + (custom_query or '')[:80]}, "
        f"date={run_date_input}"
    )
    with st.spinner("Running pipeline (1-5 min for hermes runs)..."):
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    if result.returncode == 0:
        st.success(f"✅ Pipeline completed (exit 0). Auto-switching view to `{run_date_input}`.")
        st.session_state.last_pipeline_date = str(run_date_input)
        st.session_state.selected_view_date = str(run_date_input)
    else:
        st.error(f"❌ Pipeline failed (exit {result.returncode}). See stderr below.")

    with st.expander("stdout"):
        st.code(result.stdout or "(empty)", language="text")
    with st.expander("stderr", expanded=(result.returncode != 0)):
        st.code(result.stderr or "(empty)", language="text")


# ---------------------------------------------------------------- tabs (always visible)

tab_report, tab_drafts, tab_video, tab_review, tab_analytics, tab_files = st.tabs(
    ["📊 Daily Report", "✍️ Drafts", "🎬 Video Prompts", "🗂️ Review Queue",
     "📈 Analytics", "📁 Files"]
)

selected_date = st.session_state.selected_view_date


def _empty_state(tab_name: str) -> None:
    st.info(
        f"No run outputs to show in **{tab_name}** yet. "
        "Pick a topic in the sidebar and click **▶ Run pipeline**."
    )


# ---------------------------------------------------------------- Daily Report

with tab_report:
    if not selected_date:
        _empty_state("Daily Report")
    else:
        manifest = load_manifest(selected_date)
        report_md = load_report_md(selected_date)

        if manifest is None:
            st.warning(f"No manifest for `{selected_date}`. Run a pipeline first.")
        else:
            summary = manifest_summary(manifest)
            c1, c2, c3 = st.columns(3)
            c1.metric("Provider", summary["provider"])
            c2.metric("LLM Provider", summary["llm_provider"])
            c3.metric(
                "Citationless ratio",
                f"{summary['citationless_ratio']*100:.1f}%",
                classify_citationless_ratio(summary["citationless_ratio"]),
            )
            c4, c5, c6 = st.columns(3)
            c4.metric(
                "Fallback used",
                "—" if not summary["fallback_used"] else f"{len(summary['fallback_used'])}",
                (", ".join(summary["fallback_used"]) if summary["fallback_used"] else "clean"),
            )
            c5.metric(
                "Warnings",
                "—" if not summary["warnings"] else str(len(summary["warnings"])),
                ("see manifest" if summary["warnings"] else "clean"),
            )
            c6.metric(
                "High-citationless topics",
                "—" if not summary["topics_with_high_citationless_ratio"] else str(
                    len(summary["topics_with_high_citationless_ratio"])
                ),
                (", ".join(summary["topics_with_high_citationless_ratio"])
                 if summary["topics_with_high_citationless_ratio"] else "clean"),
            )

            if summary["is_clean"]:
                st.success("✅ Clean run — no fallback, no warnings, no high-ratio topics.")
            else:
                issues = []
                if summary["fallback_used"]:
                    issues.append("fallback was used")
                if summary["warnings"]:
                    issues.append(f"{len(summary['warnings'])} warning(s)")
                if summary["topics_with_high_citationless_ratio"]:
                    issues.append("high-citationless topic(s) flagged")
                st.warning(f"⚠️ Issues: {', '.join(issues)} — review carefully.")

            with st.expander("Full run_manifest.json"):
                st.json(manifest)

        if report_md:
            st.markdown("---")
            st.markdown(report_md)
        elif manifest is not None:
            st.info(f"No `report.md` for `{selected_date}`.")


# ---------------------------------------------------------------- Drafts

with tab_drafts:
    if not selected_date:
        _empty_state("Drafts")
    else:
        drafts = list_drafts(selected_date)
        if not drafts:
            st.info(f"No content drafts for `{selected_date}`.")
        else:
            sub_tabs = st.tabs([d.stem for d in drafts])
            for sub_tab, d in zip(sub_tabs, drafts):
                with sub_tab:
                    st.markdown(d.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Video Prompts

with tab_video:
    if not selected_date:
        _empty_state("Video Prompts")
    else:
        vps = list_video_prompts(selected_date)
        if not vps:
            st.info(f"No video prompts for `{selected_date}`.")
        else:
            sub_tabs = st.tabs([v.stem for v in vps])
            for sub_tab, v in zip(sub_tabs, vps):
                with sub_tab:
                    st.markdown(v.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Review Queue

with tab_review:
    st.caption(
        "🛡️ Move buttons and feedback save only touch local files under "
        "`outputs/review_queue/<date>/`. Nothing is posted or sent externally."
    )
    if not selected_date:
        _empty_state("Review Queue")
    else:
        rq = review_queue_paths(selected_date)
        if not rq["root"].exists():
            st.info(f"No review queue for `{selected_date}`. Run a pipeline first.")
        else:
            manifest_for_impact = load_manifest(selected_date) or {}
            citationless_ratio = float(manifest_for_impact.get("citationless_ratio", 0.0))

            with st.expander("📋 drafts_to_review.md", expanded=False):
                if rq["drafts_to_review_md"].exists():
                    st.markdown(rq["drafts_to_review_md"].read_text(encoding="utf-8"))
                else:
                    st.caption("(file not present yet)")

            st.markdown("### Pending drafts")
            drafts_for_review = list_drafts(selected_date)
            if not drafts_for_review:
                st.info("No pending drafts (already moved or never generated).")
            for draft_path in drafts_for_review:
                parsed = parse_draft_md(draft_path)

                # Determine source quality signals for impact estimator
                topic_for_impact = ""
                # Best effort: try to infer topic from manifest's existing data
                # (not strictly needed for current rule-based estimator)
                impact = estimate_impact(
                    channel=parsed["channel"],
                    draft_text=parsed["draft_text"],
                    source_url_count=len(parsed["source_urls"]),
                    has_official_source=any(
                        "anthropicai" in u.lower() or "openai" in u.lower()
                        or "nousresearch" in u.lower() or "xai" in u.lower()
                        or "databricks" in u.lower() or "snowflake" in u.lower()
                        or "nvidia" in u.lower() or "awscloud" in u.lower()
                        for u in parsed["source_urls"]
                    ),
                    has_founder_source=any(
                        "elonmusk" in u.lower() or "sama" in u.lower()
                        or "satyanadella" in u.lower() or "demishassabis" in u.lower()
                        or "karpathy" in u.lower()
                        for u in parsed["source_urls"]
                    ),
                    topic=topic_for_impact,
                    citationless_ratio=citationless_ratio,
                )

                # Show prior review status if logged
                prior = latest_review_for_draft(selected_date, parsed["name"])
                status_badge = f" — last action: `{prior['review_status']}`" if prior else ""

                expander_title = (
                    f"📄 **{parsed['stem']}** — "
                    f"sources: {len(parsed['source_urls'])}, "
                    f"impact: {impact.estimated_impact_score}/10 "
                    f"({impact.virality_potential}){status_badge}"
                )

                with st.expander(expander_title, expanded=False):
                    # Impact estimate panel
                    ic1, ic2, ic3 = st.columns(3)
                    ic1.metric("Impact score", f"{impact.estimated_impact_score}/10")
                    ic2.metric("Virality potential", impact.virality_potential)
                    ic3.metric("Confidence", impact.confidence)
                    with st.expander("Reasoning (rule-based, no LLM call)"):
                        for r in impact.reasoning:
                            st.write(f"- {r}")
                        st.caption(impact.disclaimer)

                    st.markdown("---")

                    # Draft body
                    st.markdown(f"**Source summary:** {parsed['source_summary']}")
                    st.markdown(f"**My angle:** {parsed['my_angle']}")
                    if parsed["source_urls"]:
                        st.markdown("**Source URLs:**")
                        for u in parsed["source_urls"]:
                            st.markdown(f"- [{u}]({u})")
                    else:
                        st.warning("⚠️ No source URLs in this draft.")
                    st.markdown(f"**originality_note:** {parsed['originality_note']}")
                    st.markdown(f"**needs_review:** `{parsed['needs_review']}`")
                    st.markdown("**Draft text:**")
                    st.markdown(parsed["draft_text"] or "_(empty)_")

                    st.markdown("---")
                    # Feedback inputs
                    fb_text = st.text_area(
                        "💬 Feedback (your reason / what to fix / what's good)",
                        value="",
                        height=100,
                        key=f"fb-text-{parsed['stem']}",
                        placeholder=(
                            "e.g. 'Hook is generic — needs a sharper opening tied to "
                            "the actual X discourse this morning. Source #2 is weak.'"
                        ),
                    )
                    tags = st.multiselect(
                        "🏷️ Reason tags",
                        options=REASON_TAGS,
                        default=[],
                        key=f"fb-tags-{parsed['stem']}",
                    )

                    # Action buttons
                    cols = st.columns([1, 1, 1.4, 1, 2])
                    cols[0].markdown("**Action:**")
                    if cols[1].button("✅ approved", key=f"act-app-{parsed['stem']}"):
                        try:
                            save_review_action(
                                date_str=selected_date,
                                draft_file=parsed["name"],
                                review_status="approved",
                                feedback_text=fb_text, reason_tags=tags,
                            )
                            moved = move_draft_to_bucket(
                                draft_path, date_str=selected_date, bucket="approved"
                            )
                            st.success(
                                f"Moved → `{moved.relative_to(ROOT)}` + logged feedback"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Action failed: {type(e).__name__}: {e}")
                    if cols[2].button("❌ rejected", key=f"act-rej-{parsed['stem']}"):
                        try:
                            save_review_action(
                                date_str=selected_date,
                                draft_file=parsed["name"],
                                review_status="rejected",
                                feedback_text=fb_text, reason_tags=tags,
                            )
                            moved = move_draft_to_bucket(
                                draft_path, date_str=selected_date, bucket="rejected"
                            )
                            st.success(
                                f"Moved → `{moved.relative_to(ROOT)}` + logged feedback"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Action failed: {type(e).__name__}: {e}")
                    if cols[3].button("🔍 fact_check", key=f"act-fc-{parsed['stem']}"):
                        try:
                            save_review_action(
                                date_str=selected_date,
                                draft_file=parsed["name"],
                                review_status="needs_fact_check",
                                feedback_text=fb_text, reason_tags=tags,
                            )
                            moved = move_draft_to_bucket(
                                draft_path, date_str=selected_date,
                                bucket="needs_fact_check"
                            )
                            st.success(
                                f"Moved → `{moved.relative_to(ROOT)}` + logged feedback"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Action failed: {type(e).__name__}: {e}")
                    if cols[4].button(
                        "💾 Save feedback only (no move)",
                        key=f"act-fb-{parsed['stem']}",
                    ):
                        try:
                            save_review_action(
                                date_str=selected_date,
                                draft_file=parsed["name"],
                                review_status="feedback_only",
                                feedback_text=fb_text, reason_tags=tags,
                            )
                            st.success("Feedback logged (draft stays in pending).")
                        except Exception as e:
                            st.error(f"Save failed: {type(e).__name__}: {e}")

            # Bucket contents summary
            st.markdown("---")
            st.markdown("### Bucket contents")
            bucket_cols = st.columns(len(REVIEW_BUCKETS))
            for col, bucket in zip(bucket_cols, REVIEW_BUCKETS):
                with col:
                    st.subheader(bucket.replace("_", " "))
                    files = list_bucket(selected_date, bucket)
                    if not files:
                        st.caption("(empty)")
                    for f in files:
                        st.caption(f"• {f.name}")

            # Feedback log
            from ui.logic import read_review_log
            entries = read_review_log(selected_date)
            if entries:
                st.markdown("---")
                st.markdown(f"### Feedback log ({len(entries)} entries)")
                with st.expander("Show feedback_log.jsonl"):
                    for e in entries[-20:]:  # show last 20
                        st.markdown(
                            f"- `{e['timestamp']}` · **{e['draft_file']}** → "
                            f"`{e['review_status']}`"
                            + (f" · tags: {', '.join(e.get('reason_tags', []))}"
                               if e.get('reason_tags') else "")
                        )
                        if e.get("feedback_text"):
                            st.caption(f"  💬 {e['feedback_text']}")


# ---------------------------------------------------------------- Analytics

with tab_analytics:
    st.caption(
        "📊 **Mockup** — local aggregates across all run dates. Reads only "
        "`outputs/.../run_manifest.json` and `outputs/review_queue/<date>/"
        "feedback_log.jsonl`. No external calls."
    )

    all_dates = list_run_dates()
    if not all_dates:
        _empty_state("Analytics")
    else:
        st.write(f"**Aggregated over {len(all_dates)} run date(s).**")

        # --- Row 1: review-status & reason-tag distributions ----------
        col_status, col_tags = st.columns(2)

        with col_status:
            st.subheader("Review status distribution")
            status_counts = aggregate_review_status()
            if not status_counts:
                st.caption("(no feedback logged yet)")
            else:
                st.bar_chart(status_counts)
                st.caption(
                    "Counts the LAST status per draft per date. "
                    "Approval rate = approved / (approved + rejected + needs_fact_check)."
                )
                total_decisive = sum(
                    status_counts.get(s, 0)
                    for s in ("approved", "rejected", "needs_fact_check")
                )
                if total_decisive > 0:
                    rate = status_counts.get("approved", 0) / total_decisive
                    st.metric("Approval rate", f"{rate*100:.1f}%")

        with col_tags:
            st.subheader("Reason tag frequency")
            tag_counts = aggregate_reason_tags()
            if not tag_counts:
                st.caption("(no reason tags applied yet)")
            else:
                sorted_tags = dict(
                    sorted(tag_counts.items(), key=lambda x: -x[1])
                )
                st.bar_chart(sorted_tags)
                st.caption(
                    "All tag attachments (not deduped per draft). "
                    "Top tags suggest where prompt / pipeline tuning could pay off."
                )

        st.divider()

        # --- Row 2: run history (citationless ratio over time) --------
        st.subheader("Citationless ratio over time")
        history = aggregate_run_history()
        if not history:
            st.caption("(no run manifests found)")
        else:
            ratio_series = {row["date"]: row["citationless_ratio"] for row in history}
            st.line_chart(ratio_series)
            st.caption(
                "🟢 < 20%  /  🟡 20–50%  /  🔴 ≥ 50% — see `docs/operations.md` "
                "for the per-band response."
            )

            with st.expander("Full run history table"):
                st.dataframe(
                    history,
                    column_config={
                        "date": "Date",
                        "citationless_ratio": st.column_config.NumberColumn(
                            "Citationless", format="%.2f",
                        ),
                        "citationless_items_count": "Citationless #",
                        "provider": "Provider",
                        "llm_provider": "LLM",
                        "fallback_count": "Fallbacks",
                        "warning_count": "Warnings",
                        "high_ratio_topics": "High-ratio topics",
                    },
                    hide_index=True,
                )

        st.divider()

        # --- Row 3: topic-level signals -------------------------------
        st.subheader("Topics flagged as high-citationless")
        topic_flags = aggregate_high_ratio_topics()
        if not topic_flags:
            st.caption("No topic has crossed the high-citationless threshold yet.")
        else:
            sorted_topics = dict(
                sorted(topic_flags.items(), key=lambda x: -x[1])
            )
            st.bar_chart(sorted_topics)
            st.caption(
                "How often each topic appeared in "
                "`topics_with_high_citationless_ratio` across runs. "
                "Consistent offenders → adjust per-topic prompt overrides "
                "in `src/adapters/search_hermes.py::TOPIC_PROMPT_OVERRIDES`."
            )


# ---------------------------------------------------------------- Files

with tab_files:
    if not selected_date:
        _empty_state("Files")
    else:
        base = ROOT / "outputs"
        st.write(f"**Output paths for run date `{selected_date}`:**")
        for sub in (
            "daily_reports", "content_drafts", "video_prompts", "review_queue",
        ):
            p = base / sub / selected_date
            if p.exists():
                st.write(f"- `{p.relative_to(ROOT)}`")
                for f in sorted(p.iterdir()):
                    if f.is_file():
                        st.caption(f"  • {f.name} ({f.stat().st_size} bytes)")
                    elif f.is_dir():
                        inner = sorted(f.iterdir())
                        st.caption(f"  • {f.name}/  ({len(inner)} files)")

        flat_files = [
            base / "csv" / f"{selected_date}.csv",
            base / "excel" / f"{selected_date}_x_intelligence_report.xlsx",
        ]
        for fp in flat_files:
            if fp.exists():
                st.write(f"- `{fp.relative_to(ROOT)}` ({fp.stat().st_size} bytes)")

        raw_hermes = base / "raw_responses" / "hermes" / selected_date
        if raw_hermes.exists():
            nf = sum(1 for _ in raw_hermes.iterdir() if _.is_file())
            st.write(f"- `{raw_hermes.relative_to(ROOT)}/`  ({nf} files, gitignored)")


st.divider()
st.caption(
    "🛡️ **No auto-posting** — this UI views, classifies, logs feedback, "
    "and moves local files only. Verify every draft and source URL before "
    "publishing manually."
)
