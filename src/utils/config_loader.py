"""Config loader — YAML files under config/ + .env."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    def load_dotenv(*_, **__):
        return False


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
FIXTURES_PATH = PROJECT_ROOT / "fixtures" / "sample_posts.json"


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


@dataclass
class AppConfig:
    keywords: dict[str, Any]
    topics: dict[str, Any]
    profile: dict[str, Any]
    output: dict[str, Any]
    env: dict[str, str]
    fixtures_path: Path = FIXTURES_PATH

    def config_hash(self) -> str:
        """Hash includes all YAML configs PLUS fixtures content.

        Re-running with the same configs and fixtures yields the same hash,
        making run_manifest replayable.
        """
        payload = json.dumps(
            {
                "keywords": self.keywords,
                "topics": self.topics,
                "profile": self.profile,
                "output": self.output,
                "fixture_hash": self.fixture_hash(),
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def fixture_hash(self) -> str:
        return _hash_file(self.fixtures_path)


def _read_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(env_file: Path | None = None) -> AppConfig:
    if env_file is None:
        env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)

    return AppConfig(
        keywords=_read_yaml("keywords.yaml"),
        topics=_read_yaml("topics.yaml"),
        profile=_read_yaml("profile.yaml"),
        output=_read_yaml("output.yaml"),
        env={k: v for k, v in os.environ.items()},
    )
