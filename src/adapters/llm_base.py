"""LLM adapter contract.

The LLM is used for: summarization, topic-level sentiment, content drafting,
video prompt generation, and per-post "why important" comments.

Implementations must be safe to instantiate without API keys (fall back to
deterministic mock output and record the fallback in RunManifest).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class LLMProvider(ABC):
    name: ClassVar[str] = "base"
    fallback_used: bool = False

    @abstractmethod
    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.4) -> str:
        ...
