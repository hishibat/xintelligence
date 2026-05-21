"""Claude LLM adapter — calls Anthropic API when ANTHROPIC_API_KEY is set.

If the key or SDK is missing we fall back to MockLLMProvider and set
fallback_used = True so the orchestrator can record it in RunManifest.
"""
from __future__ import annotations

import os
from typing import ClassVar

from src.adapters.llm_base import LLMProvider
from src.adapters.llm_mock import MockLLMProvider


class ClaudeLLMProvider(LLMProvider):
    name: ClassVar[str] = "claude"

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("CLAUDE_MODEL", "claude-opus-4-7")
        self._impl: object | None = None
        self._fallback: MockLLMProvider | None = None
        # Detected at first call. Newer Claude models (Opus 4.x+) reject
        # ``temperature``; once we see that error we stop sending it.
        self._omit_temperature: bool = False

        if not self.api_key:
            self._fallback = MockLLMProvider(marked_as_fallback=True)
            self.fallback_used = True
            return

        try:
            import anthropic  # type: ignore
        except ImportError:
            self._fallback = MockLLMProvider(marked_as_fallback=True)
            self.fallback_used = True
            return

        self._anthropic_mod = anthropic
        self._impl = anthropic.Anthropic(api_key=self.api_key)

    def _make_kwargs(self, prompt: str, max_tokens: int, temperature: float) -> dict:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if not self._omit_temperature:
            kwargs["temperature"] = temperature
        return kwargs

    def complete(self, prompt: str, *, max_tokens: int = 800, temperature: float = 0.4) -> str:
        if self._fallback is not None:
            return self._fallback.complete(prompt, max_tokens=max_tokens, temperature=temperature)

        # Try once; on `temperature is deprecated`, flip the flag and retry.
        for attempt in (1, 2):
            try:
                kwargs = self._make_kwargs(prompt, max_tokens, temperature)
                response = self._impl.messages.create(**kwargs)  # type: ignore[attr-defined]
                blocks = response.content or []
                for b in blocks:
                    if getattr(b, "type", None) == "text":
                        return b.text  # type: ignore[attr-defined]
                return ""
            except Exception as e:
                msg = str(e).lower()
                if attempt == 1 and "temperature" in msg and not self._omit_temperature:
                    self._omit_temperature = True
                    continue
                if self._fallback is None:
                    self._fallback = MockLLMProvider(marked_as_fallback=True)
                    self.fallback_used = True
                return self._fallback.complete(prompt, max_tokens=max_tokens, temperature=temperature)
        return ""
