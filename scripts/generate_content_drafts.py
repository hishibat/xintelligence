"""Standalone CLI: generate content drafts only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_daily import main as run_main  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return run_main(argv)


if __name__ == "__main__":
    sys.exit(main())
