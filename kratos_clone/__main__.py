"""CLI entry point.

Usage:
    python -m kratos_clone <url> [--output-dir DIR] [--headed] [--no-styles] [--passes N]

Examples:
    python -m kratos_clone https://nexusflow-saas.aura.build/ \
        --output-dir extracted_v2

    KCD_HEADED=true KCD_SCROLL_PASSES=4 \
        python -m kratos_clone https://example.com/
"""

from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

from .capture import HardenedCapture, CaptureConfig


def main():
    ap = argparse.ArgumentParser(prog="kratos_clone")
    ap.add_argument("url")
    ap.add_argument("--output-dir", default="./capture")
    ap.add_argument(
        "--headed", action="store_true", help="Run browser headed (for WebGL/Spline)"
    )
    ap.add_argument(
        "--no-styles", action="store_true", help="Skip computed-style snapshot"
    )
    ap.add_argument("--no-shadow", action="store_true", help="Skip shadow DOM walker")
    ap.add_argument(
        "--no-io-polyfill",
        action="store_true",
        help="Disable IntersectionObserver pre-fire (debug)",
    )
    ap.add_argument("--passes", type=int, default=3, help="Scroll pass count (1-3)")
    ap.add_argument("--viewport", default="1920x1080", help="WxH viewport")
    args = ap.parse_args()

    w, h = (int(x) for x in args.viewport.lower().split("x"))
    cfg = CaptureConfig(
        viewport_width=w,
        viewport_height=h,
        headed=args.headed,
        capture_computed_styles=not args.no_styles,
        use_shadow_walker=not args.no_shadow,
        use_io_polyfill=not args.no_io_polyfill,
        scroll_passes=max(1, min(3, args.passes)),
    )

    cap = HardenedCapture(
        args.url, args.output_dir, cfg, log=lambda m: print(m, flush=True)
    )
    manifest = asyncio.run(cap.run())
    print()
    print("=" * 60)
    print(f"Output: {Path(args.output_dir).resolve()}")
    print(f"  Assets: {manifest['assets_count']}")
    print(f"  HTML:   {manifest['html_size_kb']} KB")
    if manifest.get("styles_json_size_kb"):
        print(f"  Styles: {manifest['styles_json_size_kb']} KB")
    print(f"  Time:   {manifest['duration_s']} s")
    print(f"  Patches: {', '.join(manifest['patches_applied'])}")
    if manifest["errors"]:
        print(f"  ⚠️  Errors: {len(manifest['errors'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
