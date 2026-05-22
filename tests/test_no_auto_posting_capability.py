"""Negative test: this MVP must NOT have auto-posting capability.

We grep the entire src/ + scripts/ tree for keywords that would indicate
a posting function (post / send / publish / tweet / create_post) being
called against external endpoints. The test fails if any code path:

1. defines a function whose name implies posting to X / SNS
2. imports a Twitter / X / Mastodon write SDK
3. references a write-API endpoint URL

This is intentional belt-and-suspenders — schema-level review can drift,
but the test is a hard line against regression.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
UI = ROOT / "ui"

# Function-name patterns that smell like "posting to a social network".
# Read tools (get_*, search_*) are explicitly excluded.
POSTING_FN_PATTERNS = [
    re.compile(r"def\s+(post_to_x|send_tweet|tweet|publish_post|create_tweet|create_post)\b"),
    re.compile(r"def\s+post_to_(linkedin|mastodon|threads|bluesky)\b"),
    re.compile(r"def\s+publish_to_(x|linkedin|note|mastodon)\b"),
]

# Write endpoint URLs we forbid.
# IMPORTANT: do NOT use "/2/tweets" alone — that prefix also covers READ
# paths like "/2/tweets/search/recent". We pair the path with the HTTP verb
# in CODE_LEVEL_WRITE_PATTERNS below; the strings here are URLs that exist
# only for writes.
WRITE_ENDPOINTS = [
    "api.twitter.com/2/tweets/manage",     # explicit write subpath
    "twitter.com/oauth/post",
    "linkedin.com/v2/posts",
    "api.linkedin.com/v2/ugcPosts",
]

# Code-level write patterns: HTTP verb + tweet-ish endpoint near each other.
CODE_LEVEL_WRITE_PATTERNS = [
    re.compile(r"\.post\s*\(\s*[\"'][^\"']*tweets[\"']", re.I),
    re.compile(r"requests\.post\s*\(\s*[\"'][^\"']*twitter\.com", re.I),
    re.compile(r"httpx\.post\s*\(\s*[\"'][^\"']*twitter\.com", re.I),
    re.compile(r"\.create_tweet\s*\(", re.I),
    re.compile(r"\.update_status\s*\(", re.I),
]

# SDKs / libraries that exist primarily to write to social networks.
FORBIDDEN_IMPORTS = [
    "import tweepy",
    "from tweepy",
    "import python_twitter",
    "from python_twitter",
    "import twython",
    "from twython",
    "import linkedin_api",
    "from linkedin_api",
]


def _all_python_files() -> list[Path]:
    files: list[Path] = []
    for base in (SRC, SCRIPTS, UI):
        if not base.exists():
            continue
        files.extend(base.rglob("*.py"))
    # exclude __pycache__
    return [f for f in files if "__pycache__" not in f.parts]


@pytest.mark.parametrize("py_file", _all_python_files())
def test_file_has_no_posting_capability(py_file: Path):
    text = py_file.read_text(encoding="utf-8")

    for pat in POSTING_FN_PATTERNS:
        m = pat.search(text)
        assert m is None, (
            f"{py_file.relative_to(ROOT)} defines a posting-style function "
            f"({m.group(0) if m else ''}). MVP is draft-generation only."
        )

    for url in WRITE_ENDPOINTS:
        assert url not in text, (
            f"{py_file.relative_to(ROOT)} references a write endpoint '{url}'. "
            "MVP must not perform auto-posting."
        )

    for pat in CODE_LEVEL_WRITE_PATTERNS:
        m = pat.search(text)
        assert m is None, (
            f"{py_file.relative_to(ROOT)} contains a write-style call "
            f"('{m.group(0) if m else ''}'). MVP must not auto-post."
        )

    for imp in FORBIDDEN_IMPORTS:
        assert imp not in text, (
            f"{py_file.relative_to(ROOT)} imports a posting SDK ('{imp}'). "
            "MVP must not perform auto-posting."
        )


def test_requirements_has_no_posting_sdk():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for forbidden in ("tweepy", "python-twitter", "twython", "linkedin-api"):
        assert forbidden not in req, (
            f"requirements.txt pins '{forbidden}', which is a posting SDK. "
            "MVP must not include auto-posting capability."
        )


def test_readme_states_draft_only():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Either Japanese or English phrasing acceptable
    markers = [
        "draft generation only",
        "draft-generation only",
        "投稿実行機能なし",
        "自動投稿は実装しない",
    ]
    assert any(m in readme for m in markers), (
        "README must state explicitly that MVP is draft generation only."
    )
