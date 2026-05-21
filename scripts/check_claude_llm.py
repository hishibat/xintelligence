"""Connectivity check for Claude LLM only — NO FALLBACK.

This is a single-purpose health check used before running the full pipeline
with --llm-provider claude. It fails loudly if the key is missing or the
API call cannot complete — that is intentional. Do NOT add fallback to mock
here; the pipeline already has that path. The point of this script is to
confirm the real path works.

Strict secret hygiene:
  - never print the API key
  - never print os.environ
  - print only: model name, timestamps, response length, success bool,
    and (optionally) a short prefix of the assistant's reply (200 chars max).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.config_loader import load_config  # noqa: E402


PROMPT = (
    "Reply with exactly one short Japanese sentence summarising why operational "
    "discipline matters more than raw capability for production AI agents. "
    "End with '[要事実確認]'."
)
MAX_REPLY_PREVIEW = 200
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_TOKENS = 300
DEFAULT_TEMPERATURE = 0.3


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    # Load .env without printing values.
    _ = load_config()

    api_key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    model = os.environ.get("CLAUDE_MODEL", "claude-opus-4-7")

    print("=== Claude LLM Connectivity Check ===")
    print(f"started_at         : {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"model              : {model}")
    print(f"max_tokens         : {DEFAULT_MAX_TOKENS}")
    print(f"temperature        : {DEFAULT_TEMPERATURE}")
    print(f"timeout_seconds    : {DEFAULT_TIMEOUT_SECONDS}")
    print(f"api_key_present    : {api_key_present}")

    if not api_key_present:
        _eprint("[FAIL] ANTHROPIC_API_KEY is not set in environment or .env.")
        _eprint("       Add it to .env (never commit) and rerun.")
        return 2

    try:
        import anthropic  # type: ignore
    except ImportError:
        _eprint("[FAIL] anthropic SDK not installed. Run: pip install anthropic")
        return 3

    client = anthropic.Anthropic(timeout=DEFAULT_TIMEOUT_SECONDS)
    started = time.monotonic()

    # Newer Claude models (opus 4.x onward) deprecated the ``temperature``
    # parameter. We try with it first for older models, then retry without
    # if Anthropic rejects it.
    def _call(include_temperature: bool):
        kwargs = {
            "model": model,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "messages": [{"role": "user", "content": PROMPT}],
        }
        if include_temperature:
            kwargs["temperature"] = DEFAULT_TEMPERATURE
        return client.messages.create(**kwargs)

    try:
        try:
            response = _call(include_temperature=True)
        except anthropic.BadRequestError as e:
            if "temperature" in str(e).lower():
                print("(note: model rejects `temperature`; retrying without it)")
                response = _call(include_temperature=False)
            else:
                raise
    except Exception as e:  # narrow exceptions intentionally broad here
        _eprint(f"[FAIL] Claude API call raised: {type(e).__name__}: {str(e)[:200]}")
        return 4
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text_blocks = [b.text for b in (response.content or []) if getattr(b, "type", None) == "text"]
    reply = "".join(text_blocks)
    reply_len = len(reply)

    print(f"elapsed_ms         : {elapsed_ms}")
    print(f"response_length    : {reply_len} chars")
    print(f"stop_reason        : {getattr(response, 'stop_reason', 'unknown')}")
    print(f"usage              : input={getattr(response.usage, 'input_tokens', '?')}, "
          f"output={getattr(response.usage, 'output_tokens', '?')}")
    print()
    preview = reply[:MAX_REPLY_PREVIEW]
    print("--- response preview (truncated) ---")
    print(preview)
    if reply_len > MAX_REPLY_PREVIEW:
        print(f"... [{reply_len - MAX_REPLY_PREVIEW} more chars truncated]")
    print()

    if reply_len == 0:
        _eprint("[FAIL] Empty response from Claude.")
        return 5

    print("[OK] Claude LLM is reachable and responsive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
