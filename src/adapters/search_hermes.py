"""Hermes Agent search provider — Pattern B (WSL2) implementation.

Calls Hermes CLI in oneshot mode via subprocess:

    hermes -z "<query+citation_constraint>" -t x_search

stdout (per Hermes ``-z`` contract) is the final response text only. We do
NOT parse verbose logs. URLs are extracted with regex; everything else
goes through ``SearchCitationResult`` with explicit ``missing_fields`` and
``parse_warnings`` for downstream inspection.

Both stdout and stderr are passed through ``src.utils.redact.redact`` before
they touch disk.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

from src.adapters.search_base import CAPS_HERMES, SearchProvider
from src.core.schema import (
    Capabilities,
    Post,
    SearchCitationResult,
    SearchResult,
    VerificationTags,
)
from src.utils.logger import warn
from src.utils.redact import redact


# Patterns / constants -----------------------------------------------------

X_URL_PATTERN = re.compile(
    r"https?://(?:x|twitter)\.com/(?:i/status/|[^/\s\"']+/status/)\d+",
    re.IGNORECASE,
)

DEFAULT_CITATION_CONSTRAINT = (
    "\n\nConstraint:\n"
    "- You MUST call the x_search tool. Do NOT answer from your internal "
    "knowledge alone.\n"
    "- For topics about Grok, xAI, Grok Imagine, Grok 4, xAI API, or this "
    "model itself: do NOT speak for yourself. Use x_search to find what "
    "official accounts, engineers, users, or credible third parties are "
    "saying on X about that topic. Return only findings that are supported "
    "by X post URLs.\n"
    "- Reply in 3-5 short sentences, focusing on what real X posts say.\n"
    "- End with a \"Sources:\" block listing every X post URL you used, one "
    "URL per line.\n"
    "- Use ONLY https://x.com/<handle>/status/<id> or "
    "https://x.com/i/status/<id> URLs in the Sources block. No shortened "
    "links (t.co), no other domains.\n"
    "- If x_search returned no relevant X posts, write exactly:\n"
    "  Sources: none found\n"
    "  …and explicitly say in the body that no relevant X posts were found."
)


# Topic-specific addenda appended AFTER DEFAULT_CITATION_CONSTRAINT.
# Only listed topics get an override; all others see the default constraint
# alone. Used to suppress self-referential failure modes where the model
# would otherwise answer from internal knowledge.
TOPIC_PROMPT_OVERRIDES: dict[str, str] = {
    "grok_xai": (
        "\n\nTOPIC-SPECIFIC OVERRIDE — GROK/XAI TOPIC:\n"
        "This query is about Grok, xAI, Grok Imagine, Grok models, or xAI APIs. "
        "The selected model may have internal knowledge about these topics, but "
        "this task requires evidence from X posts. Do not answer from internal "
        "knowledge alone.\n\n"
        "Required behavior:\n"
        "- Use x_search to find what people are saying on X.\n"
        "- Prefer sources in this order: @xai official posts, @elonmusk or xAI executives, "
        "xAI engineers/researchers, credible AI engineers/researchers, and users sharing "
        "real usage experience.\n"
        "- Every important claim must be supported by at least one X post URL.\n"
        "- Focus on what changed, what people are reacting to, and why it matters for AI agents, "
        "content automation, enterprise AI adoption, or career/tech sales implications.\n"
        "- Do not provide a generic product explanation from memory.\n"
        "- If x_search returns no relevant X posts, explicitly write 'Sources: none found' "
        "and explain that no relevant X posts were found. Do not silently substitute internal knowledge.\n"
    ),
}


@dataclass
class HermesCallResult:
    """Raw subprocess result + redacted stdout/stderr + metadata.

    All callers must treat ``stdout`` / ``stderr`` as ALREADY redacted.
    """
    stdout: str
    stderr: str
    return_code: int
    elapsed_ms: int
    cmd: list[str]
    raw_response_path: Path | None
    parse_warnings: list[str]


class HermesError(Exception):
    """Raised when Hermes subprocess fails and no fallback is configured."""


class HermesSearchProvider(SearchProvider):
    name: ClassVar[str] = "hermes"
    capabilities: ClassVar[Capabilities] = CAPS_HERMES

    def __init__(
        self,
        *,
        cli_invocation: list[str] | None = None,
        toolsets: str = "x_search",
        timeout_seconds: int = 120,
        raw_response_dir: Path | None = None,
        fallback: SearchProvider | None = None,
        citation_constraint: str = DEFAULT_CITATION_CONSTRAINT,
    ) -> None:
        # cli_invocation defaults to invoking hermes via wsl bash login shell
        # (login shell needed so PATH picks up ~/.local/bin/hermes)
        self.cli_invocation = cli_invocation or ["wsl", "bash", "-lc"]
        self.toolsets = toolsets
        self.timeout_seconds = timeout_seconds
        self.raw_response_dir = Path(raw_response_dir) if raw_response_dir else None
        self.fallback = fallback
        self.citation_constraint = citation_constraint
        self.fallback_used = False
        self.last_warnings: list[str] = []

    # ---- public API ------------------------------------------------------

    def search(self, query: str, topic: str, time_range: str) -> SearchResult:
        full_query = (
            query.rstrip()
            + self.citation_constraint
            + TOPIC_PROMPT_OVERRIDES.get(topic, "")
        ).strip()
        try:
            call = self._invoke_hermes(full_query, topic=topic)
        except HermesError as e:
            return self._fallback_search(query, topic, time_range, reason=str(e))

        if call.return_code != 0 or not call.stdout.strip():
            reason = (
                f"hermes exit={call.return_code}, "
                f"stdout_len={len(call.stdout)}, stderr_excerpt={call.stderr[:200]!r}"
            )
            return self._fallback_search(query, topic, time_range, reason=reason)

        item = self._to_citation_result(
            stdout=call.stdout,
            stderr=call.stderr,
            topic=topic,
            raw_path=call.raw_response_path,
            extra_warnings=call.parse_warnings,
        )

        return SearchResult(
            provider_name=self.name,
            query=query,
            topic=topic,
            time_range=time_range,
            retrieved_at=datetime.now(timezone.utc),
            items=[item],
            source_urls=list(item.cited_urls),
            capabilities=self.capabilities,
            missing_fields=list(item.missing_fields),
            raw_response_path=str(call.raw_response_path) if call.raw_response_path else None,
        )

    # ---- internals -------------------------------------------------------

    def _build_shell_command(self, full_query: str) -> list[str]:
        """Construct the full subprocess argv.

        The first element is the launcher (``wsl bash -lc``) and the last
        element is a single shell-quoted Hermes command line.
        """
        hermes_cmd = (
            f"hermes -z {shlex.quote(full_query)} "
            f"-t {shlex.quote(self.toolsets)}"
        )
        return [*self.cli_invocation, hermes_cmd]

    def _invoke_hermes(self, full_query: str, *, topic: str) -> HermesCallResult:
        cmd = self._build_shell_command(full_query)
        parse_warnings: list[str] = []
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as e:
            raise HermesError(f"Hermes launcher not found: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise HermesError(
                f"Hermes timed out after {self.timeout_seconds}s "
                f"(query[:80]={full_query[:80]!r})"
            ) from e
        elapsed_ms = int((time.monotonic() - start) * 1000)

        stdout_redacted = redact(proc.stdout or "")
        stderr_redacted = redact(proc.stderr or "")

        raw_path = self._save_raw_response(
            stdout=stdout_redacted,
            stderr=stderr_redacted,
            topic=topic,
            query=full_query,
            cmd=cmd,
            return_code=proc.returncode,
            elapsed_ms=elapsed_ms,
        )

        return HermesCallResult(
            stdout=stdout_redacted,
            stderr=stderr_redacted,
            return_code=proc.returncode,
            elapsed_ms=elapsed_ms,
            cmd=cmd,
            raw_response_path=raw_path,
            parse_warnings=parse_warnings,
        )

    def _save_raw_response(
        self,
        *,
        stdout: str,
        stderr: str,
        topic: str,
        query: str,
        cmd: list[str],
        return_code: int,
        elapsed_ms: int,
    ) -> Path | None:
        if self.raw_response_dir is None:
            return None
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ts_str = datetime.now(timezone.utc).strftime("%H%M%S")
        target_dir = self.raw_response_dir / date_str
        target_dir.mkdir(parents=True, exist_ok=True)

        qhash = hashlib.sha1(query.encode("utf-8")).hexdigest()[:8]
        safe_topic = re.sub(r"[^a-zA-Z0-9_\-]", "_", topic)[:40] or "untopic"
        base = target_dir / f"{ts_str}_{safe_topic}_{qhash}"

        (base.with_suffix(".stdout")).write_text(stdout, encoding="utf-8")
        (base.with_suffix(".stderr")).write_text(stderr, encoding="utf-8")
        meta = {
            "topic": topic,
            "query_hash": qhash,
            "query_preview": query[:200],
            "cmd": cmd,
            "return_code": return_code,
            "elapsed_ms": elapsed_ms,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        (base.with_suffix(".meta.json")).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return base.with_suffix(".stdout")

    def _to_citation_result(
        self,
        *,
        stdout: str,
        stderr: str,
        topic: str,
        raw_path: Path | None,
        extra_warnings: list[str],
    ) -> SearchCitationResult:
        body = stdout.strip()
        parse_warnings: list[str] = list(extra_warnings)

        urls = X_URL_PATTERN.findall(body)
        cited_urls = _dedupe_preserve_order(urls)

        cited_posts = [
            {"url": u, "snippet": None, "title": None} for u in cited_urls
        ]

        if not cited_urls:
            parse_warnings.append("no x.com/twitter.com URLs found in response")
        if "sources:" not in body.lower():
            parse_warnings.append("expected 'Sources:' block not present")
        if stderr.strip():
            parse_warnings.append(f"non-empty stderr: {stderr[:200]!r}")

        missing_fields = [
            "author",
            "author_handle",
            "created_at",
            "engagement_metrics",
            "thread_context",
            "raw_post_text",
        ]

        return SearchCitationResult(
            summary=body,
            provider_response=body,
            cited_urls=cited_urls,
            cited_posts=cited_posts,
            provider_name=self.name,
            confidence=None,
            topic=topic,
            verification=VerificationTags(),
            missing_fields=missing_fields,
            parse_warnings=parse_warnings,
            raw_response_path=str(raw_path) if raw_path else None,
        )

    def _fallback_search(
        self, query: str, topic: str, time_range: str, *, reason: str
    ) -> SearchResult:
        warn(f"Hermes failed: {reason}")
        self.last_warnings.append(f"Hermes failed: {reason}")
        if self.fallback is None:
            raise HermesError(reason)
        self.fallback_used = True
        result = self.fallback.search(query, topic=topic, time_range=time_range)
        # Tag the substitute result so callers can tell what happened.
        return SearchResult(
            provider_name=f"{result.provider_name} (fallback from hermes)",
            query=result.query,
            topic=result.topic,
            time_range=result.time_range,
            retrieved_at=result.retrieved_at,
            items=result.items,
            source_urls=result.source_urls,
            capabilities=result.capabilities,
            missing_fields=result.missing_fields,
            raw_response_path=result.raw_response_path,
        )


def _dedupe_preserve_order(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out
