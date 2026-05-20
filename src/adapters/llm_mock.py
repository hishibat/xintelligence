"""Mock LLM — deterministic short responses keyed on prompt content.

Used both as the MVP default and as automatic fallback when the real LLM
provider has no API key configured.
"""
from __future__ import annotations

from typing import ClassVar

from src.adapters.llm_base import LLMProvider


class MockLLMProvider(LLMProvider):
    name: ClassVar[str] = "mock"

    def __init__(self, *, marked_as_fallback: bool = False) -> None:
        self.fallback_used = marked_as_fallback

    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.4) -> str:
        lower = prompt.lower()
        if "why is this important" in lower or "重要" in prompt:
            return "エンタープライズAI採用とコンテンツ運用の両面で参考になる動向。[要事実確認]"
        if "trend summary" in lower or "トレンド要約" in prompt:
            return (
                "全体として AI agent / coding agent の実運用知見と、"
                "主要ベンダーの製品アップデートが並列に流れている1日。"
                "新興論点はエージェント認証 (agent identity) とガバナンス。[要事実確認]"
            )
        if "x post draft" in lower or "x投稿案" in prompt:
            return (
                "AIエージェントの『運用規律』が次の論点。"
                "ツール故障時に誰がログを読み、誰が rollback するか — "
                "本番運用で生き残るのはSRE的振る舞いをする agent。\n\n— 自分の解釈"
            )
        if "note outline" in lower or "note記事" in prompt:
            return (
                "# AIエージェント運用の現実\n\n"
                "1. 何が起きているか\n"
                "2. 運用上の3つの落とし穴\n"
                "3. 私が現場で見た失敗パターン\n"
                "4. 明日からのアクション3つ\n"
            )
        if "linkedin" in lower:
            return (
                "Operational discipline is becoming the real differentiator for "
                "AI agents in enterprise. Capability ceilings matter less than "
                "who owns failure modes."
            )
        if "video prompt" in lower or "imagine prompt" in prompt.lower():
            return (
                "A calm, blue-toned data center hallway slowly revealing glowing "
                "agent nodes communicating; cinematic, slow dolly-in."
            )
        return "[mock] " + prompt[:120].replace("\n", " ")
