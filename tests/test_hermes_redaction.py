"""Verify that the redactor masks all secret-like patterns documented in
docs/hermes_cli_spec.md §6. This is a hard line — if a pattern leaks
through, real Hermes output could hit disk with a live token in it.
"""
from __future__ import annotations

import pytest

from src.utils.redact import is_safe, redact


HIGH_RISK_CASES = [
    # (label, input_text)
    ("anthropic_sk_key",  "Using API key: sk-ant-abc123def456ghi789jkl012mno345pqr"),
    ("openai_sk_key",     "OPENAI_API_KEY=sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
    ("xai_key",           "XAI_API_KEY=xai-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEf"),
    ("jwt_token",         "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"),
    ("bearer_long",       "x-auth: Bearer abcdef0123456789abcdef0123456789abcdef0123456789"),
    ("using_api_key_log", "[debug] Using API key: somehermesopaquetokenvalue1234567890"),
    ("access_token",      "access_token=ya29.A0AfH6SMDXyZAbCdEfGhIj1234567890KlMnOpQrStUvWxYz"),
    ("api_key_kv",        "api_key=secret-config-token-deadbeef-cafebabe-0001"),
    ("token_kv",          "token=opaque0123456789abcdefopaque0123456789abcdef"),
    ("client_secret_kv",  "client_secret=topsecretvalue1234567890abcdef0123456789"),
    ("password_kv",       "  password=correct-horse-battery-staple-with-numbers-123456"),
    ("url_query_token",   "GET https://api.example.com/v1?token=abcdef0123456789abcdef0123456789&user=alice"),
    ("cookie_header",     "cookie: session=abcdef0123456789abcdef0123456789abcdef; path=/"),
]


@pytest.mark.parametrize("label,raw", HIGH_RISK_CASES)
def test_redact_replaces_high_risk_patterns(label: str, raw: str):
    out = redact(raw)
    assert out != raw, f"[{label}] redactor did not change input"
    assert is_safe(out), f"[{label}] is_safe() still reports leak after redact: {out!r}"
    # Generic sanity: long opaque suffixes should not survive.
    assert "abcdef0123456789abcdef0123456789" not in out, f"[{label}] long alnum survived"


def test_redact_keeps_normal_text():
    sample = (
        "Hermes Agent v0.14.0 is running. "
        "We ran hermes chat -q 'find recent posts' --toolsets x_search. "
        "The token system in transformers is fascinating."
    )
    out = redact(sample)
    # 'token' as an ordinary word should remain (no key=/value= context)
    assert "fascinating" in out
    assert "hermes chat" in out


def test_is_safe_detects_leaks_directly():
    assert is_safe("just a normal sentence about agents") is True
    assert is_safe("Using API key: sk-real-key-1234567890abcdef0") is False
    assert is_safe("Bearer eyJsomethingthatlookslikeajwt.something.somethingelse") is False


def test_redact_handles_empty_input():
    assert redact("") == ""
    assert redact(None) is None
    assert is_safe("") is True
