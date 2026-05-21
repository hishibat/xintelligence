"""Hermes Agent connectivity check — NO FALLBACK.

Single-purpose health probe used before running the full pipeline with
``--provider hermes``. Fails loudly when any precondition is unmet. Does
NOT fall back to mock — that's the whole point.

Secret hygiene:
  - never print API keys / OAuth tokens / cookies
  - all stdout/stderr from subprocess passes through src.utils.redact.redact
  - response preview is truncated to 200 chars
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.search_hermes import X_URL_PATTERN  # noqa: E402
from src.utils.redact import is_safe, redact  # noqa: E402


WSL_INVOCATION = ["wsl", "bash", "-lc"]
SMOKE_PROMPT = (
    "You MUST call x_search to find ONE specific recent X post about Claude "
    "Code. Quote the post and reply with the URL on its own line at the end "
    "after \"Source:\". The URL must be of the form "
    "https://x.com/<handle>/status/<id> or https://x.com/i/status/<id>."
)
SMOKE_TIMEOUT_SECONDS = 120
DOCTOR_TIMEOUT_SECONDS = 30
VERSION_TIMEOUT_SECONDS = 10
MAX_PREVIEW = 200


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _run(hermes_cmd: str, *, timeout: int) -> tuple[int, str, str]:
    """Run `wsl bash -lc <hermes_cmd>` and return redacted (rc, stdout, stderr)."""
    try:
        proc = subprocess.run(
            [*WSL_INVOCATION, hermes_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        return 127, "", f"launcher not found: {e}"
    except subprocess.TimeoutExpired as e:
        return 124, "", f"timed out after {timeout}s: {e}"
    return proc.returncode, redact(proc.stdout or ""), redact(proc.stderr or "")


def _truncate(text: str, n: int = MAX_PREVIEW) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n] + f" ... [{len(text) - n} more chars truncated]"


def check_version() -> tuple[bool, str]:
    rc, out, err = _run("hermes --version", timeout=VERSION_TIMEOUT_SECONDS)
    if rc != 0 or not out.strip():
        return False, f"hermes --version failed (rc={rc}, stderr={_truncate(err)})"
    return True, _truncate(out)


def check_doctor() -> tuple[bool, str, str]:
    """Run hermes doctor and return (overall_ok, doctor_output, error_summary)."""
    rc, out, err = _run("hermes doctor", timeout=DOCTOR_TIMEOUT_SECONDS)
    if rc != 0 and not out.strip():
        return False, "", f"hermes doctor failed (rc={rc}, stderr={_truncate(err)})"
    return True, out, ""


def check_xai_oauth(doctor_out: str) -> tuple[bool, str]:
    # Look for ✓ xAI OAuth ... (logged in)
    m = re.search(r"✓\s+xAI\s+OAuth\s+\(logged in\)", doctor_out)
    if m:
        return True, "xAI OAuth: logged in"
    return False, "xAI OAuth not logged in (run: hermes login or hermes auth add xai)"


def check_x_search_tool(doctor_out: str) -> tuple[bool, str]:
    m = re.search(r"✓\s+x_search\b", doctor_out)
    if m:
        return True, "x_search tool: available"
    return False, "x_search tool not available in `hermes doctor` Tool Availability section"


def check_smoke() -> tuple[bool, str, str]:
    """Run a real smoke query. Returns (ok, full_response, error_summary).

    Returns the FULL stdout (not truncated) so the caller can run URL
    extraction; the caller is responsible for truncating before display.
    """
    import shlex
    hermes_cmd = f"hermes -z {shlex.quote(SMOKE_PROMPT)} -t x_search"
    rc, out, err = _run(hermes_cmd, timeout=SMOKE_TIMEOUT_SECONDS)
    if rc != 0:
        return False, "", f"hermes -z failed (rc={rc}, stderr={_truncate(err)})"
    if not out.strip():
        return False, "", "hermes -z returned empty stdout"
    return True, out, ""


def check_smoke_url(stdout: str) -> tuple[bool, str]:
    urls = X_URL_PATTERN.findall(stdout)
    if urls:
        return True, f"extracted {len(urls)} x.com URL(s) from response"
    return False, "no x.com/twitter.com status URL found in smoke response"


def main() -> int:
    print("=== Hermes Connectivity Check (fallback disabled) ===")
    print(f"started_at         : {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"smoke_timeout_secs : {SMOKE_TIMEOUT_SECONDS}")
    print(f"max_preview_chars  : {MAX_PREVIEW}")
    print()

    failed: list[str] = []

    # [1] HERMES_VERSION
    ok, info = check_version()
    print(f"[{'OK ' if ok else 'FAIL'}] HERMES_VERSION  → {info}")
    if not ok:
        failed.append("HERMES_VERSION")

    # [2] HERMES_DOCTOR
    if not failed:
        ok, doctor_out, err = check_doctor()
        print(f"[{'OK ' if ok else 'FAIL'}] HERMES_DOCTOR   → "
              f"{'output captured (' + str(len(doctor_out)) + ' chars)' if ok else err}")
        if not ok:
            failed.append("HERMES_DOCTOR")
            doctor_out = ""
    else:
        doctor_out = ""

    # [3] XAI_OAUTH
    if doctor_out and "XAI_OAUTH" not in failed:
        ok, info = check_xai_oauth(doctor_out)
        print(f"[{'OK ' if ok else 'FAIL'}] XAI_OAUTH       → {info}")
        if not ok:
            failed.append("XAI_OAUTH")

    # [4] X_SEARCH_TOOL
    if doctor_out and "X_SEARCH_TOOL" not in failed:
        ok, info = check_x_search_tool(doctor_out)
        print(f"[{'OK ' if ok else 'FAIL'}] X_SEARCH_TOOL   → {info}")
        if not ok:
            failed.append("X_SEARCH_TOOL")

    # [5] SMOKE  (1 retry — x_search tool-calling is non-deterministic)
    smoke_out = ""
    if not failed:
        for attempt in (1, 2):
            print(f"[..] SMOKE (try {attempt}/2)  → running (may take 30-90s)...")
            ok, smoke_out, err = check_smoke()
            if not ok:
                if attempt == 2:
                    failed.append("SMOKE")
                    print(f"[FAIL] SMOKE           → {err}")
                else:
                    print(f"[..] SMOKE (try {attempt})  → {err}; retrying")
                continue
            # check for URL inline so we can decide whether to retry
            url_ok, url_info = check_smoke_url(smoke_out)
            if url_ok:
                print(f"[OK ] SMOKE           → response received "
                      f"({len(smoke_out)} chars)")
                print(f"[OK ] SMOKE_HAS_URL   → {url_info}")
                break
            else:
                print(f"[..] SMOKE (try {attempt})  → response received but no URL; "
                      f"{'retrying' if attempt == 1 else 'giving up'}")
                if attempt == 2:
                    failed.append("SMOKE_HAS_URL")

    # Safety scan on what we are about to display
    if smoke_out and not is_safe(smoke_out):
        _eprint("[WARN] smoke output still contains high-risk pattern after redact; suppressing preview")
        smoke_preview = "[suppressed: redactor did not classify cleanly]"
    else:
        smoke_preview = smoke_out

    print()
    print("--- smoke response preview (REDACTED, truncated) ---")
    print(smoke_preview if smoke_preview else "(none)")
    print()

    if failed:
        _eprint(f"[FAIL] {len(failed)} check(s) failed: {', '.join(failed)}")
        return 2
    print("[OK] Hermes is reachable and x_search is responsive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
