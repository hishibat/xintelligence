"""Content draft generator with originality guard.

Each draft carries:
    source_urls / source_summary / my_angle / draft_text /
    originality_note / needs_review

Verbatim copy of source text is forbidden: if the model returns >= 80% of
the source's text intact, we re-attempt with a stricter rephrase prompt.
The orchestrator should drop drafts that still fail (rare with mock).
"""
from __future__ import annotations

import difflib
from typing import Any

from src.adapters.llm_base import LLMProvider
from src.core.schema import ContentDraft, Post, ScoredItem


CHANNEL_PROMPTS: dict[str, str] = {
    "x_post": (
        "次のX投稿について、{tone} なトーンで、自分の解釈を交えた X post draft を1本作ってください。"
        "180文字以内。本文の丸写し禁止。論点を抽出して自分の意見を一文添えてください。"
    ),
    "x_thread": (
        "次の話題について、{tone} なトーンで X thread を 4-6 ポストで構成してください。"
        "丸写し禁止。各ポスト 240 字以内。最後のポストに『自分の仕事・キャリアへの示唆』を1行入れてください。"
    ),
    "note_outline": (
        "次の話題について、{tone} なトーンで note 記事案を作ってください。"
        "・タイトル候補3つ\n・見出し構成（最大6見出し）\n・冒頭リード 80 字\n"
        "丸写し禁止。柴田さんの視点（タイ在住・enterprise AI / consulting 経験）からの切り口を必ず入れてください。"
    ),
    # linkedin prompt is built dynamically from length_bounds — see _build_linkedin_prompt
    "linkedin": "__BUILT_DYNAMICALLY__",
}

DEFAULT_LINKEDIN_BOUNDS = {
    "short":    {"min_words": 300,  "max_words": 500,  "guidance": "tight thought-piece"},
    "standard": {"min_words": 600,  "max_words": 900,  "guidance": "business essay"},
    "long":     {"min_words": 1200, "max_words": 1500, "guidance": "in-depth analysis"},
}


def _build_linkedin_prompt(tone: str, length_mode: str, length_bounds: dict[str, dict]) -> str:
    bounds = length_bounds.get(length_mode) or DEFAULT_LINKEDIN_BOUNDS.get(length_mode) or DEFAULT_LINKEDIN_BOUNDS["standard"]
    return (
        f"次の話題について、{tone} なトーンで LinkedIn 投稿案を 1 本作ってください。"
        f"英語で **{bounds['min_words']}〜{bounds['max_words']} words** ({bounds['guidance']})。"
        f"必ずこの語数レンジに収めること。ビジネス文脈で、断定を避けつつ自分の見解を述べてください。"
        f"本文以外のメタコメント（「Here's a draft...」「---」「注：」等）は禁止。投稿本文のみを返す。"
    )


def _too_similar(source_text: str, draft_text: str, threshold: float = 0.80) -> bool:
    if not source_text or not draft_text:
        return False
    ratio = difflib.SequenceMatcher(None, source_text.lower(), draft_text.lower()).ratio()
    return ratio >= threshold


def _build_my_angle(post: Post, profile: dict[str, Any]) -> str:
    focus_high = (profile.get("focus_areas", {}) or {}).get("high_priority", []) or []
    matched = [f for f in focus_high if f.lower() in post.primary_text().lower()]
    if matched:
        return (
            "柴田さんの注力領域 [" + ", ".join(matched) + "] と関連。"
            "consulting / GTM 視点で『現場で何が起きるか』を一段足したい。"
        )
    return (
        "直接的な注力領域ではないが、enterprise AI 文脈で 1 つ示唆を抜き出せる。"
        "1次情報の補足を1つ添える前提で扱う。"
    )


def generate_drafts(
    scored: list[ScoredItem],
    *,
    profile: dict[str, Any],
    tones: list[str],
    channels: list[str],
    llm: LLMProvider,
    per_channel: int = 1,
    max_tokens_by_channel: dict[str, int] | None = None,
    linkedin_length_mode: str = "standard",
    linkedin_length_bounds: dict[str, dict] | None = None,
) -> list[ContentDraft]:
    drafts: list[ContentDraft] = []
    sources = sorted(scored, key=lambda x: x.score.total, reverse=True)
    if not sources:
        return drafts

    mt = max_tokens_by_channel or {}
    bounds = linkedin_length_bounds or DEFAULT_LINKEDIN_BOUNDS

    tone = tones[0] if tones else "insightful"
    for ch in channels:
        for i in range(per_channel):
            if i >= len(sources):
                break
            src_item = sources[i]
            post = src_item.post
            source_text = post.primary_text()
            source_summary = source_text.split("\n")[0][:200]
            my_angle = _build_my_angle(post, profile)

            if ch == "linkedin":
                prompt_template = _build_linkedin_prompt(tone, linkedin_length_mode, bounds)
                prompt = (
                    prompt_template
                    + "\n\n[元投稿の要旨]\n" + source_summary
                    + "\n\n[私の切り口]\n" + my_angle
                )
            else:
                prompt_template = CHANNEL_PROMPTS.get(ch, CHANNEL_PROMPTS["x_post"])
                prompt = (
                    prompt_template.format(tone=tone)
                    + "\n\n[元投稿の要旨]\n" + source_summary
                    + "\n\n[私の切り口]\n" + my_angle
                )

            channel_max_tokens = mt.get(ch, 800)
            draft_text = llm.complete(prompt, max_tokens=channel_max_tokens, temperature=0.5).strip()
            originality_note = "LLM draft. 自分の切り口を1要素以上加えること前提。"
            needs_review = True

            if _too_similar(source_text, draft_text):
                retry_prompt = prompt + "\n\n注意: 上の元投稿の語尾だけ変えるのは禁止。論点を抽象化し、自分の意見と並べて書いてください。"
                draft_text = llm.complete(retry_prompt, max_tokens=channel_max_tokens, temperature=0.7).strip()
                originality_note = "1st draft was too close to source; regenerated with stricter rephrase prompt."

            note_titles: list[str] = []
            note_outline: list[str] = []
            if ch == "note_outline":
                note_titles = _extract_titles(draft_text)[:3]
                note_outline = _extract_outline(draft_text)

            drafts.append(
                ContentDraft(
                    channel=ch,  # type: ignore[arg-type]
                    tone=tone,
                    source_urls=post.citation_urls(),
                    source_summary=source_summary,
                    my_angle=my_angle,
                    draft_text=draft_text,
                    originality_note=originality_note,
                    needs_review=needs_review,
                    note_title_candidates=note_titles,
                    note_outline=note_outline,
                )
            )
    return drafts


def _extract_titles(text: str) -> list[str]:
    titles: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("タイトル") or s.startswith("Title") or s.startswith("# "):
            cleaned = s.lstrip("#").replace("タイトル", "").replace("Title", "").strip(" :：")
            if cleaned:
                titles.append(cleaned)
    return titles


def _extract_outline(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(("##", "1.", "2.", "3.", "4.", "5.", "6.", "-", "・")):
            out.append(s.lstrip("#-・").lstrip())
    return out
