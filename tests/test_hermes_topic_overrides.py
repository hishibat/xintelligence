"""TOPIC_PROMPT_OVERRIDES — appended per-topic addenda.

Verifies that:
- frontier_models gets the self-referential override appended after the
  default constraint (covers Grok/xAI subtopics + GPT/Gemini/Claude)
- The override contains the documented sentinel phrases (so future edits
  cannot silently remove the core guardrails)
- Other topics (claude_code, ai_agents, multi_agent_systems, ...) are
  unchanged
- DEFAULT_CITATION_CONSTRAINT is always present regardless of topic
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.adapters.search_hermes import (
    DEFAULT_CITATION_CONSTRAINT,
    TOPIC_PROMPT_OVERRIDES,
    HermesSearchProvider,
)


# --- direct dict introspection (cheap sanity) -----------------------------

def test_frontier_models_override_present():
    assert "frontier_models" in TOPIC_PROMPT_OVERRIDES
    override = TOPIC_PROMPT_OVERRIDES["frontier_models"]
    assert "TOPIC-SPECIFIC OVERRIDE" in override
    assert "Do not answer from internal knowledge alone" in override.replace(
        "do NOT answer from internal knowledge", "Do not answer from internal knowledge"
    ) or "do NOT answer from internal knowledge alone" in override
    assert "Sources: none found" in override


def test_only_frontier_models_has_override_for_now():
    # If we add more topics later, update this assertion deliberately.
    assert set(TOPIC_PROMPT_OVERRIDES.keys()) == {"frontier_models"}


# --- behaviour via mocked subprocess --------------------------------------

class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _capture(monkeypatch, captured: dict):
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompletedProcess(
            returncode=0,
            stdout="ok body\nSources: https://x.com/i/status/1\n",
            stderr="",
        )
    monkeypatch.setattr(subprocess, "run", fake_run)


def test_frontier_models_gets_self_referential_override(monkeypatch, tmp_path: Path):
    captured: dict = {}
    _capture(monkeypatch, captured)
    provider = HermesSearchProvider(raw_response_dir=tmp_path)
    provider.search("Grok 4 features", topic="frontier_models", time_range="24h")

    # cmd is [wsl, bash, -lc, "hermes -z <quoted query> -t x_search"]
    sent = captured["cmd"][-1]
    assert "TOPIC-SPECIFIC OVERRIDE" in sent
    assert "Sources: none found" in sent
    # Default constraint must still be there
    assert "You MUST call the x_search tool" in sent


@pytest.mark.parametrize("topic", ["claude_code", "ai_agents", "multi_agent_systems",
                                    "ai_infrastructure", "data_platforms",
                                    "ai_governance", "enterprise_ai_adoption"])
def test_other_topics_unchanged(monkeypatch, tmp_path: Path, topic: str):
    captured: dict = {}
    _capture(monkeypatch, captured)
    provider = HermesSearchProvider(raw_response_dir=tmp_path)
    provider.search(f"sample query for {topic}", topic=topic, time_range="24h")

    sent = captured["cmd"][-1]
    # Default constraint is always present
    assert "You MUST call the x_search tool" in sent
    # But topic-specific override is NOT present for other topics
    assert "TOPIC-SPECIFIC OVERRIDE" not in sent


def test_default_constraint_always_present_in_default_provider():
    # Ensure the symbol we inject is real and not empty.
    assert "You MUST call the x_search tool" in DEFAULT_CITATION_CONSTRAINT
