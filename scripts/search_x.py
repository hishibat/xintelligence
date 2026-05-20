"""Single-purpose CLI: run search only and dump JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adapters.search_mock import MockSearchProvider  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True)
    p.add_argument("--topic", default="all")
    p.add_argument("--time-range", default="24h")
    args = p.parse_args(argv)

    provider = MockSearchProvider()
    result = provider.search(args.query, topic=args.topic, time_range=args.time_range)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
