"""Orchestrator — run the full pipeline end-to-end.

Usage:
    python scripts/run_daily.py --provider mock
    python scripts/run_daily.py --provider mock --llm-provider claude --topic ai_agent_market
    python scripts/run_daily.py --provider mock --no-llm --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.llm_base import LLMProvider  # noqa: E402
from src.adapters.llm_claude import ClaudeLLMProvider  # noqa: E402
from src.adapters.llm_mock import MockLLMProvider  # noqa: E402
from src.adapters.search_base import SearchProvider  # noqa: E402
from src.adapters.search_hermes import HermesSearchProvider  # noqa: E402
from src.adapters.search_mock import MockSearchProvider  # noqa: E402
from src.adapters.search_x_api import XAPISearchProvider  # noqa: E402
from src.adapters.search_xai import XAISearchProvider  # noqa: E402
from src.core.content_generator import generate_drafts  # noqa: E402
from src.core.dedupe import dedupe  # noqa: E402
from src.core.manifest import build_manifest, write_manifest  # noqa: E402
from src.core.schema import ScoredItem  # noqa: E402
from src.core.scoring import score_all, top_n  # noqa: E402
from src.core.trend_analyzer import analyze_all  # noqa: E402
from src.core.verification import tag_items  # noqa: E402
from src.core.video_prompt_generator import generate_video_prompts  # noqa: E402
from src.utils.config_loader import load_config  # noqa: E402
from src.utils.logger import drain_warnings, get_logger, warn  # noqa: E402
from scripts.export_results import (  # noqa: E402
    write_csv,
    write_daily_report_md,
    write_drafts_md,
    write_review_queue,
    write_video_prompts_md,
    write_xlsx,
)


LOG = get_logger()


def _make_search_provider(name: str) -> SearchProvider:
    if name == "mock":
        return MockSearchProvider()
    if name == "hermes":
        return HermesSearchProvider()
    if name == "xai":
        return XAISearchProvider()
    if name == "x_api":
        return XAPISearchProvider()
    raise SystemExit(f"unknown provider: {name}")


def _make_llm_provider(name: str, *, disabled: bool) -> LLMProvider:
    if disabled or name == "mock":
        return MockLLMProvider()
    if name == "claude":
        provider = ClaudeLLMProvider()
        if provider.fallback_used:
            warn("Claude API key missing or SDK unavailable → falling back to MockLLMProvider.")
        return provider
    if name == "grok":
        warn("Grok LLM adapter not yet implemented → falling back to MockLLMProvider.")
        return MockLLMProvider(marked_as_fallback=True)
    raise SystemExit(f"unknown llm provider: {name}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_daily")
    p.add_argument("--provider", default="mock", choices=["mock", "hermes", "xai", "x_api"])
    p.add_argument("--llm-provider", default=None, choices=["mock", "claude", "grok"])
    p.add_argument("--date", default=None, help="YYYY-MM-DD")
    p.add_argument("--time-range", default=None, choices=["24h", "3d", "7d"])
    p.add_argument("--topic", default="all", help="topic id or 'all'")
    p.add_argument("--output-dir", default=None)
    p.add_argument("--dry-run", action="store_true", help="run pipeline but do not write outputs")
    p.add_argument("--no-llm", action="store_true", help="force LLM provider to mock")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()

    provider_name = args.provider or os.environ.get("X_SEARCH_PROVIDER", "mock")
    llm_name = args.llm_provider or os.environ.get("LLM_PROVIDER", "mock")
    time_range = args.time_range or os.environ.get("DEFAULT_TIME_RANGE", "24h")
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base_out = Path(args.output_dir) if args.output_dir else ROOT / "outputs"

    LOG.info("provider=%s llm=%s topic=%s time_range=%s", provider_name, llm_name, args.topic, time_range)

    search = _make_search_provider(provider_name)
    llm = _make_llm_provider(llm_name, disabled=args.no_llm)

    # --- search -------------------------------------------------------------
    themes = (cfg.keywords or {}).get("themes", {}) or {}
    queries: list[tuple[str, str]] = []
    if args.topic == "all":
        for tid, body in themes.items():
            for kw in body.get("keywords", []) or []:
                queries.append((tid, kw))
    else:
        body = themes.get(args.topic)
        if not body:
            LOG.error("topic '%s' not found in keywords.yaml", args.topic)
            return 2
        for kw in body.get("keywords", []) or []:
            queries.append((args.topic, kw))

    raw_items = []
    raw_seen_query_count = 0
    for topic_id, kw in queries:
        try:
            result = search.search(kw, topic=topic_id, time_range=time_range)
        except NotImplementedError as e:
            LOG.error("provider raised NotImplementedError: %s", e)
            return 3
        raw_items.extend(result.items)
        raw_seen_query_count += 1

    if not raw_items and provider_name == "mock":
        # Mock returns the whole fixture filtered by topic; with multiple queries
        # per topic, dedupe later handles duplicates. If empty, surface a warning.
        warn("Search returned 0 items. Check fixtures or topic filter.")

    # --- normalize / dedupe / verification ----------------------------------
    deduped = dedupe(raw_items)
    tagged = tag_items(deduped)

    # --- score --------------------------------------------------------------
    weights = ((cfg.output or {}).get("scoring", {}) or {}).get("weights", {}) or {}
    top_count = int(((cfg.output or {}).get("scoring", {}) or {}).get("top_n", 10))
    scored = score_all(tagged, profile=cfg.profile or {}, weights=weights)
    top = top_n(scored, n=top_count)

    # attach a short "why important" comment
    for item in top:
        text = item.post.primary_text()[:200]
        item.why_important = llm.complete(
            "Why is this important for a tech-sales/consulting professional pivoting "
            f"to a hyperscaler/AI vendor in Japan? Answer in 1-2 short JP sentences.\n\n{text}",
            max_tokens=180,
            temperature=0.3,
        ).strip()

    # --- trends -------------------------------------------------------------
    topic_labels = {t["id"]: t.get("label", t["id"]) for t in (cfg.topics or {}).get("topics", []) or []}
    items_by_topic: dict[str, list[ScoredItem]] = {}
    for s in scored:
        tid = s.post.topic or "uncategorized"
        items_by_topic.setdefault(tid, []).append(s)
    trends = analyze_all(items_by_topic, topic_labels=topic_labels, time_range=time_range, llm=llm)

    # --- content drafts -----------------------------------------------------
    content_cfg = (cfg.output or {}).get("content", {}) or {}
    drafts = generate_drafts(
        top,
        profile=cfg.profile or {},
        tones=[content_cfg.get("default_tone", "insightful")],
        channels=content_cfg.get("channels", ["x_post", "x_thread", "note_outline", "linkedin"]),
        llm=llm,
        per_channel=int(content_cfg.get("drafts_per_channel", 1)),
    )

    # --- video prompts ------------------------------------------------------
    video_cfg = (cfg.output or {}).get("video", {}) or {}
    video_prompts = generate_video_prompts(
        scored=top,
        trends=trends,
        use_cases=video_cfg.get("use_cases", ["note_header", "x_short", "linkedin_visual", "youtube_shorts"]),
        llm=llm,
    )

    # --- outputs ------------------------------------------------------------
    fallback_used: list[str] = []
    if getattr(llm, "fallback_used", False):
        fallback_used.append(f"llm:{llm_name}->mock")

    warnings_buf = drain_warnings()
    manifest = build_manifest(
        provider=provider_name,
        llm_provider=llm_name,
        config_hash=cfg.config_hash(),
        query_count=raw_seen_query_count,
        raw_items=raw_items,
        deduped_items=deduped,
        top10_count=len(top),
        warnings=warnings_buf,
        errors=[],
        fallback_used=fallback_used,
    )

    if args.dry_run:
        LOG.info("dry-run: skipping file writes. manifest summary=%s", json.dumps(manifest.to_dict())[:400])
        return 0

    daily_dir = base_out / "daily_reports" / date_str
    write_daily_report_md(
        out_path=daily_dir / "report.md",
        date_str=date_str,
        provider=provider_name,
        llm_provider=llm_name,
        top10=top,
        trends=trends,
        fallback_used=fallback_used,
        warnings=warnings_buf,
    )
    write_manifest(manifest, daily_dir / "run_manifest.json")
    write_csv(base_out / "csv" / f"{date_str}.csv", scored)
    write_xlsx(
        base_out / "excel" / f"{date_str}_x_intelligence_report.xlsx",
        top10=top, all_items=scored, trends=trends, drafts=drafts, video_prompts=video_prompts,
    )
    write_drafts_md(base_out / "content_drafts" / date_str, drafts)
    write_video_prompts_md(base_out / "video_prompts" / date_str, video_prompts)
    write_review_queue(base_out / "review_queue" / date_str, drafts)

    LOG.info("done. outputs under %s", base_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
