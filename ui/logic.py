"""Pure logic for the X Intelligence Streamlit UI.

No streamlit imports — keeps everything unit-testable and lets the UI
layer (streamlit_app.py) stay thin. The UI shells out to run_daily.py
via subprocess; we expose a build_run_command() helper here so the
exact argv is checkable in tests.

This module intentionally has NO networking / posting capability.
File system operations are limited to read + move-within-outputs +
append-only feedback log.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


# --- Whitelisted choices (mirror scripts/run_daily.py argparse) ----------
TOPICS = [
    "claude_code",
    "ai_agents",
    "frontier_models",
    "multi_agent_systems",
    "ai_infrastructure",
    "data_platforms",
    "ai_governance",
    "enterprise_ai_adoption",
]
PROVIDERS = ["mock", "hermes"]
LLM_PROVIDERS = ["mock", "claude"]
SEARCH_FALLBACKS = ["none", "mock"]
TIME_RANGES = ["24h", "3d", "7d"]
REVIEW_BUCKETS = ["approved", "rejected", "needs_fact_check"]

# Topics whose keywords return very broad x_search result sets. Combined
# with 3d/7d time ranges, these can blow past HERMES_TIMEOUT_SECONDS=180s.
# Update this set whenever config/keywords.yaml gains a keyword that is
# obviously broad (e.g. "AI" alone).
BROAD_TOPICS = {
    "enterprise_ai_adoption",
    "frontier_models",
    "ai_agents",
    "multi_agent_systems",
}

# Reason tags exposed in Review Queue feedback UI.
REASON_TAGS = [
    "hook_weak",
    "not_buzzy",
    "too_generic",
    "needs_fact_check",
    "source_weak",
    "angle_good",
    "ready_to_post",
    "rewrite_needed",
    "too_long",
    "too_technical",
]

# --- Topic suggestion (Priority 2) ---------------------------------------
# Simple keyword → preset topic mapping. Suggestions are scored by overlap.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "claude_code": ["claude code", "anthropic", "claude api", "skills", "agent sdk", "claude opus"],
    "ai_agents": ["agent", "agentic", "autonomous", "coding agent", "workflow"],
    "frontier_models": ["gpt", "gemini", "claude opus", "grok", "xai", "deepmind", "frontier", "openai", "sota"],
    "multi_agent_systems": ["multi-agent", "orchestration", "hermes", "crewai", "langgraph", "nous", "multi-provider"],
    "ai_infrastructure": ["nvidia", "nim", "blackwell", "bedrock", "azure", "inference", "gpu"],
    "data_platforms": ["snowflake", "databricks", "lakehouse", "bigquery", "unity catalog", "cortex"],
    "ai_governance": ["governance", "ai act", "compliance", "responsible ai", "model risk", "policy"],
    "enterprise_ai_adoption": ["enterprise", "copilot adoption", "fortune 500", "ai roi", "production ai", "transformation", "deployment", "adoption"],
}


# --- Filesystem helpers ---------------------------------------------------


def outputs_dir(root: Path | None = None) -> Path:
    return (root or PROJECT_ROOT) / "outputs"


def list_run_dates(outputs_root: Path | None = None) -> list[str]:
    """Return sorted (newest first) `YYYY-MM-DD` dir names under daily_reports/."""
    daily = outputs_dir(outputs_root) / "daily_reports"
    if not daily.exists():
        return []
    dates = []
    for p in daily.iterdir():
        if p.is_dir() and len(p.name) == 10 and p.name[4] == "-" and p.name[7] == "-":
            dates.append(p.name)
    return sorted(dates, reverse=True)


def latest_run_date(outputs_root: Path | None = None) -> str | None:
    dates = list_run_dates(outputs_root)
    return dates[0] if dates else None


def load_manifest(date_str: str, outputs_root: Path | None = None) -> dict[str, Any] | None:
    p = outputs_dir(outputs_root) / "daily_reports" / date_str / "run_manifest.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_report_md(date_str: str, outputs_root: Path | None = None) -> str | None:
    p = outputs_dir(outputs_root) / "daily_reports" / date_str / "report.md"
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def list_drafts(date_str: str, outputs_root: Path | None = None) -> list[Path]:
    d = outputs_dir(outputs_root) / "content_drafts" / date_str
    if not d.exists():
        return []
    return sorted(d.glob("*.md"))


def list_video_prompts(date_str: str, outputs_root: Path | None = None) -> list[Path]:
    d = outputs_dir(outputs_root) / "video_prompts" / date_str
    if not d.exists():
        return []
    return sorted(d.glob("*.md"))


def review_queue_paths(date_str: str, outputs_root: Path | None = None) -> dict[str, Path]:
    base = outputs_dir(outputs_root) / "review_queue" / date_str
    return {
        "root": base,
        "drafts_to_review_md": base / "drafts_to_review.md",
        "approved": base / "approved",
        "rejected": base / "rejected",
        "needs_fact_check": base / "needs_fact_check",
    }


def move_draft_to_bucket(
    src: Path,
    *,
    date_str: str,
    bucket: str,
    outputs_root: Path | None = None,
) -> Path:
    """Move ``src`` into ``outputs/review_queue/<date>/<bucket>/<src.name>``.

    Pure local file move — no networking, no publishing.
    """
    if bucket not in REVIEW_BUCKETS:
        raise ValueError(f"bucket must be one of {REVIEW_BUCKETS}, got {bucket!r}")
    if not src.exists():
        raise FileNotFoundError(src)
    rq = review_queue_paths(date_str, outputs_root)
    target_dir = rq[bucket]
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / src.name
    shutil.move(str(src), str(dest))
    return dest


def list_bucket(
    date_str: str, bucket: str, outputs_root: Path | None = None
) -> list[Path]:
    rq = review_queue_paths(date_str, outputs_root)
    p = rq.get(bucket)
    if not p or not p.exists():
        return []
    return sorted(p.glob("*.md"))


# --- Run command construction --------------------------------------------


def build_run_command(
    *,
    provider: str,
    llm_provider: str,
    search_fallback: str,
    topic: str,
    date_str: str | None = None,
    time_range: str | None = None,
    python_exe: str | None = None,
) -> list[str]:
    """Build the argv for invoking ``scripts/run_daily.py`` as a subprocess.

    Validates choices against the same whitelists run_daily.py uses, so
    invalid UI input fails fast (with a ValueError) before subprocess spawn.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    if llm_provider not in LLM_PROVIDERS:
        raise ValueError(f"llm_provider must be one of {LLM_PROVIDERS}, got {llm_provider!r}")
    if search_fallback not in SEARCH_FALLBACKS:
        raise ValueError(f"search_fallback must be one of {SEARCH_FALLBACKS}, got {search_fallback!r}")
    if topic not in TOPICS:
        raise ValueError(f"topic must be one of {TOPICS}, got {topic!r}")
    if time_range is not None and time_range not in TIME_RANGES:
        raise ValueError(f"time_range must be one of {TIME_RANGES}, got {time_range!r}")

    py = python_exe or sys.executable or "python"
    script = str(PROJECT_ROOT / "scripts" / "run_daily.py")
    cmd = [
        py, script,
        "--provider", provider,
        "--llm-provider", llm_provider,
        "--search-fallback", search_fallback,
        "--topic", topic,
    ]
    if date_str:
        cmd += ["--date", date_str]
    if time_range:
        cmd += ["--time-range", time_range]
    return cmd


# --- Display helpers ------------------------------------------------------


def classify_citationless_ratio(ratio: float | None) -> str:
    """Return emoji + label for citationless_ratio band."""
    if ratio is None:
        return "—"
    if ratio < 0.20:
        return "🟢 healthy"
    if ratio < 0.50:
        return "🟡 watch"
    return "🔴 high — review needed"


def manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    """Pull the small set of fields the UI surfaces as cards."""
    return {
        "run_id": manifest.get("run_id", "—"),
        "provider": manifest.get("provider", "—"),
        "llm_provider": manifest.get("llm_provider", "—"),
        "fallback_used": manifest.get("fallback_used") or [],
        "warnings": manifest.get("warnings") or [],
        "citationless_ratio": manifest.get("citationless_ratio", 0.0),
        "citationless_items_count": manifest.get("citationless_items_count", 0),
        "topics_with_high_citationless_ratio":
            manifest.get("topics_with_high_citationless_ratio") or [],
        "is_clean": (
            not (manifest.get("fallback_used") or [])
            and not (manifest.get("warnings") or [])
            and not (manifest.get("topics_with_high_citationless_ratio") or [])
        ),
    }


# --- Draft markdown parsing ----------------------------------------------

_SECTION_HEADER = re.compile(r"^##\s+(\S+)\s*$")
_BULLET_URL = re.compile(r"^-\s+(https?://\S+)")
_HEADER_BULLET = re.compile(r"^-\s+(\w+):\s*\*?\*?(.+?)\*?\*?\s*$")


def parse_draft_md(path: Path) -> dict[str, Any]:
    """Parse a ``content_drafts/<date>/NN_<channel>.md`` file into a dict.

    The on-disk format (written by scripts/export_results.py) is:

        # <channel> draft (<tone>)

        - needs_review: **True**
        - originality_note: <text>

        ## source_urls
        - https://...
        - https://...

        ## source_summary
        <text>

        ## my_angle
        <text>

        ## draft_text
        <body>
    """
    text = path.read_text(encoding="utf-8")
    sections: dict[str, list[str]] = {}
    header_meta: dict[str, str] = {}
    current: str | None = None
    body_lines: list[str] = []

    for line in text.splitlines():
        m = _SECTION_HEADER.match(line)
        if m:
            if current is not None:
                sections[current] = body_lines
            current = m.group(1)
            body_lines = []
            continue
        if current is None:
            # We are still in the header block (before any ## section).
            hm = _HEADER_BULLET.match(line)
            if hm:
                header_meta[hm.group(1).lower()] = hm.group(2).strip()
        else:
            body_lines.append(line)
    if current is not None:
        sections[current] = body_lines

    # Extract URLs from source_urls section
    url_lines = sections.get("source_urls", [])
    source_urls: list[str] = []
    for line in url_lines:
        m = _BULLET_URL.match(line.strip())
        if m:
            source_urls.append(m.group(1))

    def _section_text(name: str) -> str:
        return "\n".join(sections.get(name, [])).strip()

    needs_review_raw = header_meta.get("needs_review", "").strip().lower()
    needs_review = needs_review_raw in ("true", "**true**", "yes")

    return {
        "name": path.name,
        "stem": path.stem,
        "channel": path.stem.split("_", 1)[1] if "_" in path.stem else path.stem,
        "needs_review": needs_review,
        "originality_note": header_meta.get("originality_note", ""),
        "source_urls": source_urls,
        "source_summary": _section_text("source_summary"),
        "my_angle": _section_text("my_angle"),
        "draft_text": _section_text("draft_text"),
        "raw_text": text,
        "char_count": len(_section_text("draft_text")),
    }


# --- Feedback log --------------------------------------------------------


def feedback_log_path(date_str: str, outputs_root: Path | None = None) -> Path:
    return review_queue_paths(date_str, outputs_root)["root"] / "feedback_log.jsonl"


def save_review_action(
    *,
    date_str: str,
    draft_file: str,
    review_status: str,
    feedback_text: str = "",
    reason_tags: list[str] | None = None,
    outputs_root: Path | None = None,
) -> dict[str, Any]:
    """Append-only JSONL log of every review action and feedback save.

    ``review_status`` ∈ {approved, rejected, needs_fact_check, feedback_only}.
    Returns the entry dict that was appended.
    """
    allowed_status = set(REVIEW_BUCKETS) | {"feedback_only"}
    if review_status not in allowed_status:
        raise ValueError(
            f"review_status must be one of {sorted(allowed_status)}, "
            f"got {review_status!r}"
        )
    reason_tags = list(reason_tags or [])
    for tag in reason_tags:
        if tag not in REASON_TAGS:
            raise ValueError(f"unknown reason_tag {tag!r}; allowed: {REASON_TAGS}")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "draft_file": draft_file,
        "review_status": review_status,
        "feedback_text": feedback_text.strip(),
        "reason_tags": reason_tags,
    }
    log = feedback_log_path(date_str, outputs_root)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_review_log(
    date_str: str, outputs_root: Path | None = None
) -> list[dict[str, Any]]:
    """Read all feedback log entries for a date (oldest first)."""
    log = feedback_log_path(date_str, outputs_root)
    if not log.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            # skip malformed lines rather than crashing the UI
            continue
    return entries


def latest_review_for_draft(
    date_str: str, draft_file: str, outputs_root: Path | None = None
) -> dict[str, Any] | None:
    """Return the most recent log entry for a specific draft, or None."""
    for entry in reversed(read_review_log(date_str, outputs_root)):
        if entry.get("draft_file") == draft_file:
            return entry
    return None


# --- Analytics aggregation -----------------------------------------------


def aggregate_review_status(
    outputs_root: Path | None = None,
    *,
    dates: list[str] | None = None,
) -> dict[str, int]:
    """Count review_status occurrences across feedback logs.

    For a draft that has multiple log entries, only the LAST entry is counted
    — that reflects the current bucket placement, not the history of changes.
    If ``dates`` is None, all run dates are aggregated.
    """
    if dates is None:
        dates = list_run_dates(outputs_root)
    counts: dict[str, int] = {}
    for d in dates:
        last_by_draft: dict[str, str] = {}
        for entry in read_review_log(d, outputs_root):
            df = entry.get("draft_file", "")
            status = entry.get("review_status", "")
            if df and status:
                last_by_draft[df] = status
        for status in last_by_draft.values():
            counts[status] = counts.get(status, 0) + 1
    return counts


def aggregate_reason_tags(
    outputs_root: Path | None = None,
    *,
    dates: list[str] | None = None,
) -> dict[str, int]:
    """Count reason_tag occurrences across feedback logs.

    All tags from all entries are counted (a single feedback can attach
    multiple tags, and revising feedback adds new tag counts).
    """
    if dates is None:
        dates = list_run_dates(outputs_root)
    counts: dict[str, int] = {}
    for d in dates:
        for entry in read_review_log(d, outputs_root):
            for tag in entry.get("reason_tags", []) or []:
                counts[tag] = counts.get(tag, 0) + 1
    return counts


def aggregate_run_history(outputs_root: Path | None = None) -> list[dict[str, Any]]:
    """Return per-run summary rows for time-series charts.

    Each row carries the run date, citationless_ratio, provider, llm_provider,
    fallback count, and warning count. Sorted oldest-first for line charts.
    """
    rows: list[dict[str, Any]] = []
    for d in list_run_dates(outputs_root):
        m = load_manifest(d, outputs_root)
        if not m:
            continue
        rows.append({
            "date": d,
            "citationless_ratio": float(m.get("citationless_ratio") or 0.0),
            "citationless_items_count": int(m.get("citationless_items_count") or 0),
            "provider": m.get("provider", "—"),
            "llm_provider": m.get("llm_provider", "—"),
            "fallback_count": len(m.get("fallback_used") or []),
            "warning_count": len(m.get("warnings") or []),
            "high_ratio_topics": list(m.get("topics_with_high_citationless_ratio") or []),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def aggregate_high_ratio_topics(outputs_root: Path | None = None) -> dict[str, int]:
    """Count how often each topic appeared in topics_with_high_citationless_ratio."""
    counts: dict[str, int] = {}
    for row in aggregate_run_history(outputs_root):
        for t in row["high_ratio_topics"]:
            counts[t] = counts.get(t, 0) + 1
    return counts


# --- Pre-run warnings (Sidebar UX) ---------------------------------------


def compute_run_warnings(
    *,
    provider: str,
    search_fallback: str,
    topic: str | None,
    time_range: str | None,
) -> list[dict[str, str]]:
    """Return per-combination warnings the UI should render BEFORE Run.

    Each entry is a dict with:
        severity  ∈ {"info", "warning"}
        location  ∈ {"sidebar", "run_button"}
        message   — human-readable string (Markdown OK)

    Pure function, no Streamlit imports — testable in isolation.
    """
    warnings: list[dict[str, str]] = []

    # 3d range — informational
    if time_range == "3d":
        warnings.append({
            "severity": "info",
            "location": "sidebar",
            "message": (
                "**3d range** may take longer and consume more tokens. "
                "For UI testing, `search_fallback=mock` is recommended."
            ),
        })

    # 7d range — stronger warning
    if time_range == "7d":
        warnings.append({
            "severity": "warning",
            "location": "sidebar",
            "message": (
                "**7d range** can timeout with broad topics. Use "
                "`search_fallback=mock` for daily use, or increase "
                "`HERMES_TIMEOUT_SECONDS=300` for fail-loud validation."
            ),
        })

    # 7d + fail-loud + hermes — critical, surfaced next to the Run button
    if (
        time_range == "7d"
        and search_fallback == "none"
        and provider == "hermes"
    ):
        warnings.append({
            "severity": "warning",
            "location": "run_button",
            "message": (
                "⚠️ **Fail-loud mode with 7d Hermes search may timeout.** "
                "Recommended: switch **Search fallback** to `mock` for "
                "hands-on testing."
            ),
        })

    # Broad topic + 7d — extra heads-up
    if time_range == "7d" and topic in BROAD_TOPICS:
        warnings.append({
            "severity": "warning",
            "location": "sidebar",
            "message": (
                f"Topic `{topic}` has **broad keywords**. With 7d range, "
                "`x_search` may return very large result sets and increase "
                "timeout risk."
            ),
        })

    return warnings


def is_hermes_timeout_failure(stderr: str) -> bool:
    """Heuristic: detect Hermes timeout in subprocess stderr.

    Used by the UI to swap raw stderr for a friendly remediation message
    when the failure mode is the well-known 180s timeout.
    """
    if not stderr:
        return False
    s = stderr.lower()
    return "hermes" in s and ("timed out" in s or "timeout" in s)


HERMES_TIMEOUT_FRIENDLY_MESSAGE = (
    "🕒 **Hermes timed out.** This is common for **broad topics with "
    "3d/7d ranges**. Try **`time_range=24h`**, or set **`Search "
    "fallback=mock`** so the pipeline degrades to mock data and still "
    "produces artifacts. For fail-loud 7d validation, raise "
    "`HERMES_TIMEOUT_SECONDS=300` in your `.env` before launching "
    "Streamlit."
)


# --- Topic suggestion (Priority 2) ---------------------------------------


def suggest_topics(input_text: str, *, k: int = 3) -> list[str]:
    """Return up to k preset topic_ids ranked by keyword overlap.

    Pure substring match on lowercased text. Returns [] if no overlap.
    """
    if not input_text:
        return []
    text = input_text.lower()
    scores: dict[str, int] = {}
    for topic, kws in TOPIC_KEYWORDS.items():
        n = sum(1 for kw in kws if kw in text)
        if n > 0:
            scores[topic] = n
    return [t for t, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))][:k]


# --- Custom query path (Priority 2) --------------------------------------


def build_run_command_custom(
    *,
    provider: str,
    llm_provider: str,
    search_fallback: str,
    custom_query: str,
    custom_topic_id: str = "custom",
    date_str: str | None = None,
    time_range: str | None = None,
    python_exe: str | None = None,
) -> list[str]:
    """Build argv for a custom-query run (bypasses preset topic keyword list).

    Uses --custom-query flag added to scripts/run_daily.py. The custom_topic_id
    is used purely as a label for organising outputs by topic name.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}, got {provider!r}")
    if llm_provider not in LLM_PROVIDERS:
        raise ValueError(f"llm_provider must be one of {LLM_PROVIDERS}, got {llm_provider!r}")
    if search_fallback not in SEARCH_FALLBACKS:
        raise ValueError(f"search_fallback must be one of {SEARCH_FALLBACKS}, got {search_fallback!r}")
    if not custom_query or not custom_query.strip():
        raise ValueError("custom_query must be a non-empty string")
    if time_range is not None and time_range not in TIME_RANGES:
        raise ValueError(f"time_range must be one of {TIME_RANGES}, got {time_range!r}")

    py = python_exe or sys.executable or "python"
    script = str(PROJECT_ROOT / "scripts" / "run_daily.py")
    cmd = [
        py, script,
        "--provider", provider,
        "--llm-provider", llm_provider,
        "--search-fallback", search_fallback,
        "--custom-query", custom_query.strip(),
        "--custom-topic-id", custom_topic_id,
    ]
    if date_str:
        cmd += ["--date", date_str]
    if time_range:
        cmd += ["--time-range", time_range]
    return cmd
