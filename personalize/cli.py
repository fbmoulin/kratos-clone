"""Command-line entry point for the personalization pipeline.

Usage:
    python -m personalize <html_dir> --brief brief.txt --logo logo.png \\
        [--budget 1.00] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

from .openai_client import OpenAIBrandClient
from .pipeline import run_pipeline

log = structlog.get_logger()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m personalize")
    parser.add_argument(
        "html_dir",
        type=Path,
        help="directory containing index.html and _inventory.json",
    )
    parser.add_argument(
        "--brief",
        type=Path,
        required=True,
        help="path to a UTF-8 text file with the brand brief",
    )
    parser.add_argument(
        "--logo",
        type=Path,
        required=True,
        help="path to a PNG or JPEG logo (≤ 2 MiB)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=1.0,
        help="USD cap on total OpenAI spend (default: 1.00)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate inputs and print summary without making API calls",
    )
    args = parser.parse_args(argv)

    load_dotenv()  # picks up OPENAI_API_KEY from .env if present

    if not args.brief.exists():
        print(f"error: brief file not found: {args.brief}", file=sys.stderr)
        return 2
    if not args.logo.exists():
        print(f"error: logo file not found: {args.logo}", file=sys.stderr)
        return 2

    raw_brief = args.brief.read_text(encoding="utf-8")
    logo_bytes = args.logo.read_bytes()

    if args.dry_run:
        out = run_pipeline(args.html_dir, raw_brief, logo_bytes, dry_run=True)
        print(f"dry-run OK; would write to {args.html_dir}/personalized.html")
        return 0

    client = OpenAIBrandClient(max_budget_usd=args.budget)
    out = run_pipeline(args.html_dir, raw_brief, logo_bytes, client=client)
    print(f"wrote {out}")
    print(f"spent: ${client.spent_usd:.4f} / ${args.budget:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
