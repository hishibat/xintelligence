"""Hermes adapter — error handling and fallback wiring with mock subprocess."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.adapters.search_hermes import HermesError, HermesSearchProvider
from src.adapters.search_mock import MockSearchProvider


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_subprocess(monkeypatch, behaviour):
    """behaviour(cmd, **kwargs) -> _FakeCompletedProcess or raises."""
    def fake_run(cmd, **kwargs):
        return behaviour(cmd, **kwargs)
    monkeypatch.setattr(subprocess, "run", fake_run)


def test_success_returns_citation_result(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(
            returncode=0,
            stdout=("A recent X post says X happened.\n"
                    "Sources: https://x.com/i/status/111\n"),
            stderr="",
        )
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path)
    result = provider.search("test", topic="x", time_range="24h")
    assert result.provider_name == "hermes"
    assert len(result.items) == 1
    assert result.items[0].cited_urls == ["https://x.com/i/status/111"]
    assert result.items[0].raw_response_path is not None
    # raw response artifacts must exist on disk
    raw_path = Path(result.items[0].raw_response_path)
    assert raw_path.exists()
    assert raw_path.with_suffix(".stderr").exists()
    assert raw_path.with_suffix(".meta.json").exists()


def test_failure_without_fallback_raises_hermes_error(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=1, stdout="", stderr="boom")
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path, fallback=None)
    with pytest.raises(HermesError) as exc:
        provider.search("test", topic="x", time_range="24h")
    assert "hermes exit=1" in str(exc.value) or "boom" in str(exc.value)


def test_failure_with_fallback_uses_mock(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=1, stdout="", stderr="boom")
    _patch_subprocess(monkeypatch, behaviour)
    mock_fb = MockSearchProvider()
    provider = HermesSearchProvider(raw_response_dir=tmp_path, fallback=mock_fb)
    result = provider.search("any", topic="all", time_range="24h")
    assert provider.fallback_used is True
    assert "fallback from hermes" in result.provider_name
    # mock returns the full fixture for topic=all
    assert len(result.items) > 0


def test_timeout_raises_hermes_error_no_fallback(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 120))
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path, fallback=None)
    with pytest.raises(HermesError) as exc:
        provider.search("test", topic="x", time_range="24h")
    assert "timed out" in str(exc.value)


def test_launcher_missing_raises_hermes_error(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        raise FileNotFoundError("wsl not found")
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path, fallback=None)
    with pytest.raises(HermesError):
        provider.search("test", topic="x", time_range="24h")


def test_empty_stdout_is_treated_as_failure(monkeypatch, tmp_path: Path):
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=0, stdout="", stderr="")
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path, fallback=None)
    with pytest.raises(HermesError):
        provider.search("test", topic="x", time_range="24h")


def test_stdout_passed_through_redactor(monkeypatch, tmp_path: Path):
    risky = ("Hermes responded.\n"
             "Using API key: sk-ant-deadbeefcafebabefacefeed1234567890\n"
             "Sources: https://x.com/i/status/777\n")
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=0, stdout=risky, stderr="")
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path)
    result = provider.search("test", topic="x", time_range="24h")
    body = result.items[0].summary
    assert "sk-ant-deadbeef" not in body
    assert "[REDACTED]" in body or "[REDACTED-SK-KEY]" in body
    # And on-disk file should also be redacted
    raw = Path(result.items[0].raw_response_path).read_text(encoding="utf-8")
    assert "sk-ant-deadbeef" not in raw


def test_no_silent_fallback_writes_warning(monkeypatch, tmp_path: Path):
    from src.utils.logger import drain_warnings
    drain_warnings()  # clear buffer
    def behaviour(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=2, stdout="", stderr="auth")
    _patch_subprocess(monkeypatch, behaviour)
    provider = HermesSearchProvider(raw_response_dir=tmp_path,
                                    fallback=MockSearchProvider())
    provider.search("test", topic="x", time_range="24h")
    msgs = drain_warnings()
    assert any("Hermes failed" in m for m in msgs), (
        "expected Hermes failure warning in shared buffer"
    )
