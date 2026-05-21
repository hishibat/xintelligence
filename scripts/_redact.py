"""Thin CLI wrapper around src.utils.redact for use during Hermes probes.

Usage:
    python scripts/_redact.py --in raw.txt --out clean.txt
    cat raw.txt | python scripts/_redact.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils.redact import redact  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Mask secret-like tokens in stdin/file.")
    p.add_argument("--in", dest="in_path", help="Input file (default: stdin)")
    p.add_argument("--out", dest="out_path", help="Output file (default: stdout)")
    args = p.parse_args()

    text = Path(args.in_path).read_text(encoding="utf-8", errors="replace") if args.in_path else sys.stdin.read()
    redacted = redact(text)
    if args.out_path:
        Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_path).write_text(redacted, encoding="utf-8")
    else:
        sys.stdout.write(redacted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
