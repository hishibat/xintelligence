"""--search-fallback {none,mock} CLI behaviour for run_daily."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.run_daily import main as run_daily_main


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _force_hermes_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=1, stdout="", stderr="forced failure for test")
    monkeypatch.setattr(subprocess, "run", fake_run)


def test_fallback_none_fails_loudly(monkeypatch, tmp_path: Path):
    """When --search-fallback none and Hermes fails, run_daily must exit non-zero."""
    _force_hermes_failure(monkeypatch)
    rc = run_daily_main([
        "--provider", "hermes",
        "--llm-provider", "mock",
        "--search-fallback", "none",
        "--output-dir", str(tmp_path / "outputs"),
        "--date", "2026-05-20",
        "--topic", "ai_agent",
    ])
    assert rc != 0, "expected non-zero exit when Hermes fails with --search-fallback none"


def test_fallback_mock_recovers_and_records(monkeypatch, tmp_path: Path):
    """When --search-fallback mock and Hermes fails, run_daily must exit 0,
    record fallback_used and warnings in manifest, and produce artifacts."""
    _force_hermes_failure(monkeypatch)
    out = tmp_path / "outputs"
    rc = run_daily_main([
        "--provider", "hermes",
        "--llm-provider", "mock",
        "--search-fallback", "mock",
        "--output-dir", str(out),
        "--date", "2026-05-20",
        "--topic", "ai_agent",
    ])
    assert rc == 0

    manifest_path = out / "daily_reports" / "2026-05-20" / "run_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "search:hermes->mock" in manifest["fallback_used"]
    assert any("Hermes failed" in w for w in manifest["warnings"])
    # report.md exists
    assert (out / "daily_reports" / "2026-05-20" / "report.md").exists()
