"""Secret redaction — promoted from scripts/_redact.py (Step 0 probe helper)
so adapters can import it.

Public API:
    redact(text: str) -> str        Apply all patterns, return masked text.
    redact_lines(lines) -> list     Apply per-line, useful for streaming.
    is_safe(text) -> bool           True if text contains no high-risk patterns.

Patterns covered (all case-insensitive where applicable):

    sk-<base64-ish>           Anthropic / OpenAI-style key             [REDACTED-SK-KEY]
    xai-<base64-ish>          xAI key                                   [REDACTED-XAI-KEY]
    eyJ<...>.<...>            JWT-style token                           [REDACTED-JWT]
    Authorization: Bearer X   Header form                               Bearer [REDACTED]
    Using API key: X          Hermes / generic log line                 Using API key: [REDACTED]
    api_key=X / api_key: X    config / env form                         api_key: [REDACTED]
    access_token=X / :X       OAuth flow                                access_token: [REDACTED]
    token=X / token: X        generic (in headers / URL query)          token: [REDACTED]
    key=X / key: X            generic — masked only when value is long alnum
    client_secret=X           OAuth client secret                       client_secret: [REDACTED]
    password=X / :X           login form                                password: [REDACTED]
    cookie: X                 cookie header                             cookie: [REDACTED]
    ?token=X (URL query)      URL-embedded credential                   ?token=[REDACTED]

Standalone long alnum runs (≥ 40 chars, mix of digits and letters) are
replaced with [REDACTED-LONG-ALNUM] as a belt-and-suspenders catch.
"""
from __future__ import annotations

import re
from typing import Iterable


# Order matters: more specific patterns first.
PATTERNS: list[tuple[re.Pattern[str], object]] = [
    # JWT-style tokens (eyJ + base64-ish, requires at least one dot)
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}(\.[A-Za-z0-9_\-]+)?"), "[REDACTED-JWT]"),
    # Anthropic / OpenAI style API keys (sk-...)
    (re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"), "[REDACTED-SK-KEY]"),
    # xAI style API keys (xai-...)
    (re.compile(r"\bxai-[A-Za-z0-9\-_]{20,}\b"), "[REDACTED-XAI-KEY]"),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_\.~+/=]{20,}"), "Bearer [REDACTED]"),
    # Header / env / config style: key/secret/token/cookie/password/oauth
    (re.compile(
        r"(?i)\b(authorization|api[_\- ]?key|api[_\- ]?token|access[_\- ]?token|"
        r"oauth[_\- ]?token|client[_\- ]?secret|secret|password|cookie|x-api-key)\s*[:=]\s*[\"']?\S+"
    ), lambda m: f"{m.group(1)}: [REDACTED]"),
    # "Using API key: <value>" / "Using token: <value>" — hermes-style log
    (re.compile(
        r"(?i)\b(using\s+(?:api[_\- ]?key|token|secret|oauth|cookie))\s*[:=]?\s*\S+"
    ), lambda m: f"{m.group(1)}: [REDACTED]"),
    # token=... / key=... — only when value looks high-entropy (>=20 alnum chars)
    (re.compile(r"(?i)\b(token|key)\s*[:=]\s*[\"']?([A-Za-z0-9\-_\.]{20,})"),
     lambda m: f"{m.group(1)}: [REDACTED]"),
    # URL query strings carrying credentials
    (re.compile(
        r"(?i)([?&](?:token|key|access_token|oauth_token|sig|signature|api_key)=)[^&\s\"']+"
    ), lambda m: f"{m.group(1)}[REDACTED]"),
]

# Belt-and-suspenders: long alnum runs that no specific pattern matched.
_LONG_ALNUM = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")

# High-risk patterns used by is_safe() to detect leakage.
# These match only actual high-entropy secret SHAPES, NOT header phrases —
# header phrases get a [REDACTED] placeholder after redact(), so we strip
# those placeholders out before running the high-risk scan.
_HIGH_RISK = [
    re.compile(r"\bsk-[A-Za-z0-9\-_]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9\-_]{20,}\b"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_\.~+/=]{20,}"),
]
_REDACTED_PLACEHOLDER = re.compile(r"\[REDACTED[^\]]*\]")


def redact(text: str) -> str:
    """Apply all redaction patterns and return masked text."""
    if not text:
        return text
    out = text
    for pat, repl in PATTERNS:
        if callable(repl):
            out = pat.sub(repl, out)
        else:
            out = pat.sub(repl, out)

    # Last resort: standalone long alnum mix-of-digit-and-letter runs.
    def _mark(m: re.Match[str]) -> str:
        v = m.group(0)
        has_digit = any(c.isdigit() for c in v)
        has_alpha = any(c.isalpha() for c in v)
        if has_digit and has_alpha and len(v) >= 40:
            return "[REDACTED-LONG-ALNUM]"
        return v
    out = _LONG_ALNUM.sub(_mark, out)
    return out


def redact_lines(lines: Iterable[str]) -> list[str]:
    """Apply redact() per line — useful when streaming subprocess output."""
    return [redact(line) for line in lines]


def is_safe(text: str) -> bool:
    """Return True if no high-risk credential pattern survives in ``text``.

    Known [REDACTED*] placeholders inserted by redact() are stripped before
    the scan so we don't get false positives on already-masked output.
    """
    if not text:
        return True
    # Strip our own redaction markers — they are safe by definition.
    stripped = _REDACTED_PLACEHOLDER.sub("X", text)
    for pat in _HIGH_RISK:
        if pat.search(stripped):
            return False
    return True
