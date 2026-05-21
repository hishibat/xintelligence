"""Radar-like trend analysis per topic.

Aggregates scored items by topic, picks main points, derives emerging
keywords (light TF-style), and asks the LLM for a short JP summary plus
content angles.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from src.adapters.llm_base import LLMProvider
from src.core.schema import ScoredItem, TrendSummary


_STOP = set(
    "the a an of and or to is it in for on with at by from as that this be we "
    "you our your they i he she them this these those just very more most much "
    "が の に を は と も で て だ です ます ある いる する した して これ それ".split()
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9\-/]{2,}|[一-鿿]{2,}")


def _extract_keywords(items: list[ScoredItem], k: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    for it in items:
        for tok in _WORD.findall(it.post.primary_text()):
            t = tok.lower()
            if t in _STOP or len(t) <= 2:
                continue
            counter[t] += 1
    return [w for w, _ in counter.most_common(k)]


def _classify_sentiment(items: list[ScoredItem]) -> str:
    text = " ".join(it.post.primary_text().lower() for it in items)
    pos_hits = sum(text.count(w) for w in ["growth", "ship", "ga ", "wins", "expand", "improve", "成長", "拡大", "改善"])
    neg_hits = sum(text.count(w) for w in ["block", "fail", "delay", "decline", "blocker", "drop", "下落", "失敗", "遅延"])
    if pos_hits > neg_hits * 1.5:
        return "positive"
    if neg_hits > pos_hits * 1.5:
        return "negative"
    if pos_hits == 0 and neg_hits == 0:
        return "neutral"
    return "mixed"


def analyze_topic(
    topic_id: str,
    topic_label: str,
    items: list[ScoredItem],
    *,
    time_range: str,
    llm: LLMProvider,
    max_tokens_summary: int = 800,
    max_tokens_angles: int = 400,
) -> TrendSummary:
    if not items:
        return TrendSummary(
            topic_id=topic_id,
            topic_label=topic_label,
            time_range=time_range,
            item_count=0,
            main_points=[],
            sentiment="neutral",
            emerging_keywords=[],
            short_jp_explanation="該当する投稿が今回は検出されませんでした。",
            content_angles=[],
        )

    top3 = sorted(items, key=lambda x: x.score.total, reverse=True)[:3]
    main_points = [t.post.primary_text().split("\n")[0][:160] for t in top3]
    emerging = _extract_keywords(items, k=5)
    sentiment = _classify_sentiment(items)

    prompt = (
        f"以下は X 上のトピック『{topic_label}』に関する直近 {time_range} の主要投稿です。\n"
        f"trend summary として 2 文以内で日本語で短く説明してください。"
        f"必要に応じて末尾に [要事実確認] を付けてください。\n\n"
        + "\n".join(f"- {p}" for p in main_points)
    )
    short_jp = llm.complete(prompt, max_tokens=max_tokens_summary, temperature=0.3).strip()

    angles_prompt = (
        f"上の話題から、note記事 / X 投稿に使える切り口を 3〜5 個、"
        f"短い日本語で箇条書きしてください。煽り表現は避けてください。"
    )
    angles_raw = llm.complete(prompt + "\n\n" + angles_prompt, max_tokens=max_tokens_angles, temperature=0.5)
    content_angles = _parse_bullets(angles_raw)[:5]

    return TrendSummary(
        topic_id=topic_id,
        topic_label=topic_label,
        time_range=time_range,
        item_count=len(items),
        main_points=main_points,
        sentiment=sentiment,  # type: ignore[arg-type]
        emerging_keywords=emerging,
        short_jp_explanation=short_jp,
        content_angles=content_angles,
    )


def _parse_bullets(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        for prefix in ("- ", "* ", "・", "1.", "2.", "3.", "4.", "5."):
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
                break
        if s:
            out.append(s)
    return out


def analyze_all(
    items_by_topic: dict[str, list[ScoredItem]],
    *,
    topic_labels: dict[str, str],
    time_range: str,
    llm: LLMProvider,
    max_tokens_summary: int = 800,
    max_tokens_angles: int = 400,
) -> list[TrendSummary]:
    results: list[TrendSummary] = []
    for tid, items in items_by_topic.items():
        label = topic_labels.get(tid, tid)
        results.append(analyze_topic(
            tid, label, items, time_range=time_range, llm=llm,
            max_tokens_summary=max_tokens_summary,
            max_tokens_angles=max_tokens_angles,
        ))
    return results
