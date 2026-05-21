"""HermesSearchProvider capability flags must match the spec."""
from __future__ import annotations

from src.adapters.search_base import CAPS_HERMES
from src.adapters.search_hermes import HermesSearchProvider
from src.core.schema import Capabilities


def test_caps_hermes_is_capabilities_instance():
    assert isinstance(CAPS_HERMES, Capabilities)


def test_caps_hermes_flags_match_spec():
    # Per docs/hermes_cli_spec.md §3: Hermes -z does NOT yield per-post
    # metadata but DOES yield citations.
    assert CAPS_HERMES.supports_raw_post_text is False
    assert CAPS_HERMES.supports_author is False
    assert CAPS_HERMES.supports_created_at is False
    assert CAPS_HERMES.supports_engagement_metrics is False
    assert CAPS_HERMES.supports_thread_context is False
    assert CAPS_HERMES.supports_citations is True


def test_provider_exposes_capabilities():
    p = HermesSearchProvider()
    assert p.capabilities is CAPS_HERMES
    assert p.name == "hermes"
