"""Grok Imagine video / image prompt generator.

Bilingual: ``grok_imagine_prompt_en`` for the model + ``jp_explanation``
for the user. MVP stops at prompt generation — no API submission.
"""
from __future__ import annotations

from typing import Any

from src.adapters.llm_base import LLMProvider
from src.core.schema import ScoredItem, TrendSummary, VideoPrompt


USE_CASE_TEMPLATES: dict[str, dict[str, str]] = {
    "note_header": {
        "duration": "still image",
        "aspect_ratio": "16:9",
        "style_hint": "editorial illustration, clean composition, soft lighting",
    },
    "x_short": {
        "duration": "6-10s",
        "aspect_ratio": "9:16",
        "style_hint": "fast cut, bold text overlay, energetic",
    },
    "linkedin_visual": {
        "duration": "still image",
        "aspect_ratio": "1.91:1",
        "style_hint": "corporate clean, blue/teal palette, abstract data motif",
    },
    "youtube_shorts": {
        "duration": "15-30s",
        "aspect_ratio": "9:16",
        "style_hint": "cinematic intro, slow dolly-in, restrained color grade",
    },
}


def generate_video_prompts(
    *,
    scored: list[ScoredItem],
    trends: list[TrendSummary],
    use_cases: list[str],
    llm: LLMProvider,
) -> list[VideoPrompt]:
    if not scored:
        return []
    top = scored[0].post
    headline = top.primary_text().split("\n")[0][:140]

    prompts: list[VideoPrompt] = []
    for uc in use_cases:
        tmpl = USE_CASE_TEMPLATES.get(uc, USE_CASE_TEMPLATES["note_header"])
        concept_q = (
            f"次の話題から、{uc} 用途のビジュアルコンセプトを 1 行で示してください: \n{headline}"
        )
        concept = llm.complete(concept_q, max_tokens=120, temperature=0.6).strip() or headline

        scene_q = (
            f"上のコンセプトを、Grok Imagine が解釈できる 2-3 文の英語 scene description にしてください。"
        )
        scene = llm.complete(concept_q + "\n\n" + scene_q, max_tokens=200, temperature=0.6).strip()

        # Compose the bilingual prompt payloads
        grok_en = (
            f"Concept: {concept}\n"
            f"Scene: {scene}\n"
            f"Visual style: {tmpl['style_hint']}\n"
            f"Camera movement: slow dolly-in / subtle parallax\n"
            f"Text overlay: minimal\n"
            f"Color palette: muted blue + warm accent\n"
            f"Mood: focused, editorial\n"
            f"Duration: {tmpl['duration']}\n"
            f"Aspect ratio: {tmpl['aspect_ratio']}\n"
            f"Negative prompt: low-res, distorted faces, watermark, oversaturated"
        )
        jp = (
            f"用途: {uc}\nコンセプト: {concept}\n"
            f"狙い: 元投稿『{headline}』のニュアンスをエディトリアルに視覚化。"
        )

        prompts.append(
            VideoPrompt(
                use_case=uc,  # type: ignore[arg-type]
                concept=concept,
                scene=scene,
                visual_style=tmpl["style_hint"],
                camera_movement="slow dolly-in / subtle parallax",
                text_overlay="minimal",
                color_palette="muted blue + warm accent",
                mood="focused, editorial",
                duration=tmpl["duration"],
                aspect_ratio=tmpl["aspect_ratio"],
                negative_prompt="low-res, distorted faces, watermark, oversaturated",
                grok_imagine_prompt_en=grok_en,
                jp_explanation=jp,
            )
        )
    return prompts
