"""Grok Imagine video / image prompt generator.

Bilingual: ``grok_imagine_prompt_en`` for the model + ``jp_explanation``
for the user. MVP stops at prompt generation — no API submission.

Per-use-case templates are intentionally distinct:

- note_header        : still image (no motion fields)
- x_short            : short vertical motion clip
- linkedin_visual    : still image, corporate-clean
- youtube_shorts     : longer cinematic motion clip
"""
from __future__ import annotations

from typing import Any

from src.adapters.llm_base import LLMProvider
from src.core.schema import ScoredItem, TrendSummary, VideoPrompt


# Each template encodes the *use case identity*: what the format demands,
# what motion (if any) is allowed, what density of overlay text fits, and
# which artefacts to push away in the negative prompt.
USE_CASE_TEMPLATES: dict[str, dict[str, str]] = {
    "note_header": {
        "is_motion": False,
        "duration": "N/A (still image)",
        "aspect_ratio": "16:9",
        "camera_movement": "N/A (still image)",
        "text_overlay": "minimal — at most a 4-6 word headline; no body copy",
        "visual_density": "medium — a single focal motif, generous negative space",
        "style_hint": "editorial illustration, clean composition, soft lighting, magazine-feature feel",
        "color_palette": "muted blue + warm accent on neutral background",
        "mood": "focused, editorial, calm",
        "negative_prompt": (
            "low-res, distorted faces, watermark, oversaturated, "
            "stock-photo cliche, generic gradient backgrounds, "
            "tiny illegible text, dense UI mockups"
        ),
    },
    "x_short": {
        "is_motion": True,
        "duration": "6-10 seconds",
        "aspect_ratio": "9:16",
        "camera_movement": "fast cuts every 1.5-2s, occasional whip-pan, slight handheld energy",
        "text_overlay": "bold short captions (2-5 words) on each cut; high contrast",
        "visual_density": "high — quick visual variety, multiple angles, kinetic",
        "style_hint": "punchy social-video aesthetic, high contrast, slight grain",
        "color_palette": "saturated key color + dark anchor",
        "mood": "energetic, urgent, attention-grabbing",
        "negative_prompt": (
            "long static shots, low contrast, blurry text, "
            "letterboxed 16:9 framing, slow corporate intros"
        ),
    },
    "linkedin_visual": {
        "is_motion": False,
        "duration": "N/A (still image)",
        "aspect_ratio": "1.91:1",
        "camera_movement": "N/A (still image)",
        "text_overlay": "optional small caption, sans-serif; never more than one short line",
        "visual_density": "low — single clean diagram-like motif, executive friendly",
        "style_hint": "corporate clean, abstract data motif, white-space heavy",
        "color_palette": "blue/teal palette with one warm highlight, business-formal",
        "mood": "professional, trustworthy, sober",
        "negative_prompt": (
            "low-res, distorted faces, watermark, oversaturated, "
            "gaming aesthetics, anime style, party imagery, "
            "informal hand-drawn doodles"
        ),
    },
    "youtube_shorts": {
        "is_motion": True,
        "duration": "15-30 seconds",
        "aspect_ratio": "9:16",
        "camera_movement": "cinematic dolly-in for the first 3s, then slow parallax shifts, one camera reveal mid-clip",
        "text_overlay": "title card at 0-2s + 1-2 caption supers; mid-weight type",
        "visual_density": "medium-high — single subject with deliberate beat changes",
        "style_hint": "cinematic intro, restrained color grade, shallow depth of field",
        "color_palette": "muted teal + warm accent, filmic",
        "mood": "intriguing, narrative, lean-forward",
        "negative_prompt": (
            "loud meme aesthetic, jump-scare cuts, "
            "low-budget look, default mobile filter look, "
            "tiny text, watermark, low-res"
        ),
    },
}


def generate_video_prompts(
    *,
    scored: list[ScoredItem],
    trends: list[TrendSummary],
    use_cases: list[str],
    llm: LLMProvider,
    max_tokens_concept: int = 200,
    max_tokens_scene: int = 400,
) -> list[VideoPrompt]:
    if not scored:
        return []
    top = scored[0].post
    headline = top.primary_text().split("\n")[0][:140]

    prompts: list[VideoPrompt] = []
    for uc in use_cases:
        tmpl = USE_CASE_TEMPLATES.get(uc, USE_CASE_TEMPLATES["note_header"])
        is_motion = bool(tmpl.get("is_motion"))

        concept_q = (
            f"You are designing the visual for a `{uc}` deliverable. "
            f"Required format: aspect ratio {tmpl['aspect_ratio']}, "
            f"duration {tmpl['duration']}, "
            f"{'motion-driven' if is_motion else 'still image (no motion)'}.\n\n"
            f"Source headline: {headline}\n\n"
            f"Write ONE line (≤ 90 chars) describing the visual concept in Japanese. "
            f"Be concrete — name the focal object or scene. No quote marks. "
            f"Do not echo the headline; abstract one image-able idea from it."
        )
        concept = llm.complete(concept_q, max_tokens=max_tokens_concept, temperature=0.6).strip()
        if not concept:
            concept = headline[:90]

        if is_motion:
            scene_q = (
                f"Translate the above concept into a 3-5 sentence English scene description "
                f"for the Grok Imagine model. Cover: opening shot, the main motion/event, "
                f"how it ends. Aspect {tmpl['aspect_ratio']}, duration {tmpl['duration']}, "
                f"camera plan: {tmpl['camera_movement']}. Do NOT include parameter labels; "
                f"write it as continuous prose."
            )
        else:
            scene_q = (
                f"Translate the above concept into a 2-3 sentence English scene description "
                f"for a Grok Imagine STILL image. Describe composition, focal element, "
                f"lighting, and any minimal text overlay. Aspect {tmpl['aspect_ratio']}. "
                f"Do NOT include parameter labels; write as continuous prose. "
                f"Do not describe motion — this is a still."
            )
        scene = llm.complete(
            f"Concept: {concept}\n\n{scene_q}", max_tokens=max_tokens_scene, temperature=0.6
        ).strip()

        # Compose final bilingual payload
        grok_en_lines = [
            f"Concept: {concept}",
            f"Scene: {scene}",
            f"Visual style: {tmpl['style_hint']}",
            f"Visual density: {tmpl['visual_density']}",
            f"Text overlay: {tmpl['text_overlay']}",
            f"Color palette: {tmpl['color_palette']}",
            f"Mood: {tmpl['mood']}",
            f"Aspect ratio: {tmpl['aspect_ratio']}",
            f"Duration: {tmpl['duration']}",
        ]
        if is_motion:
            grok_en_lines.append(f"Camera movement: {tmpl['camera_movement']}")
        grok_en_lines.append(f"Negative prompt: {tmpl['negative_prompt']}")
        grok_en = "\n".join(grok_en_lines)

        jp_lines = [
            f"用途: {uc}",
            f"フォーマット: " + (
                f"動画 / {tmpl['duration']} / {tmpl['aspect_ratio']}"
                if is_motion else f"静止画 / {tmpl['aspect_ratio']}"
            ),
            f"コンセプト: {concept}",
        ]
        if not is_motion:
            jp_lines.append("(静止画のため duration / camera movement は N/A)")
        jp = "\n".join(jp_lines)

        prompts.append(
            VideoPrompt(
                use_case=uc,  # type: ignore[arg-type]
                concept=concept,
                scene=scene,
                visual_style=tmpl["style_hint"],
                camera_movement=tmpl["camera_movement"],
                text_overlay=tmpl["text_overlay"],
                color_palette=tmpl["color_palette"],
                mood=tmpl["mood"],
                duration=tmpl["duration"],
                aspect_ratio=tmpl["aspect_ratio"],
                negative_prompt=tmpl["negative_prompt"],
                grok_imagine_prompt_en=grok_en,
                jp_explanation=jp,
            )
        )
    return prompts
