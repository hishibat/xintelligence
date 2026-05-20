"""Tiny logger with a shared warnings buffer the orchestrator can dump
into RunManifest.warnings.
"""
from __future__ import annotations

import logging
import os
import sys

_WARNINGS: list[str] = []


def get_logger(name: str = "x-intelligence") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def warn(message: str) -> None:
    """Record a warning into the shared buffer AND emit on stderr."""
    _WARNINGS.append(message)
    get_logger().warning(message)


def drain_warnings() -> list[str]:
    out = list(_WARNINGS)
    _WARNINGS.clear()
    return out
