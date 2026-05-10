"""Stage 3 — post-capture asset audit, inline, and scroll-fix strip.

Functions:
- ``audit_assets`` — count files + total bytes in ``<capture>/assets/``
- ``inline_small_assets`` — base64-inline any asset under ``max_bytes`` into
  the HTML, dropping the ``<img src="assets/...">`` reference
- ``strip_scroll_fix_cli`` — wrapper around ``kratos_clone.post.strip_scroll_fix``
  for CLI invocation post-capture

Usage (CLI):
    python -m scripts.post_process <capture_dir> --inline-max-bytes 5000
"""

from __future__ import annotations

import argparse
import base64
import mimetypes
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import structlog
from bs4 import BeautifulSoup, Tag
from bs4.element import AttributeValueList

log = structlog.get_logger()


def _as_str(v: str | AttributeValueList | None) -> str:
    """Coerce a BS4 attribute value to ``str``.

    BS4 returns multi-token attrs (``class``, ``rel``) as ``AttributeValueList``;
    everything else as ``str`` (or ``None`` for missing keys). Inlined per
    project convention (scripts intentionally one-shot, not a library).
    """
    if v is None:
        return ""
    return v if isinstance(v, str) else " ".join(v)


@dataclass
class AssetAudit:
    """Snapshot of a capture's ``assets/`` directory."""

    count: int
    total_bytes: int
    paths: list[Path] = field(default_factory=list)


def audit_assets(capture_dir: Path) -> AssetAudit:
    """Walk ``<capture_dir>/assets/`` and tally file count + size."""
    capture_dir = Path(capture_dir)
    assets_dir = capture_dir / "assets"
    if not assets_dir.is_dir():
        return AssetAudit(count=0, total_bytes=0, paths=[])
    paths = sorted(p for p in assets_dir.iterdir() if p.is_file())
    total = sum(p.stat().st_size for p in paths)
    log.info(
        "asset_audit",
        capture_dir=str(capture_dir),
        count=len(paths),
        total_bytes=total,
    )
    return AssetAudit(count=len(paths), total_bytes=total, paths=paths)


def _iter_asset_refs(soup: BeautifulSoup) -> Iterable[tuple[Tag, str, str]]:
    """Yield ``(tag, attr, value)`` for every URL-bearing attribute pointing
    at a relative path under ``assets/``.
    """
    for attr in ("src", "href"):
        for tag in soup.find_all(attrs={attr: True}):
            value = tag.get(attr)
            if isinstance(value, str) and value.startswith("assets/"):
                yield tag, attr, value


def inline_small_assets(html_path: Path, out_path: Path, *, max_bytes: int = 5000) -> int:
    """Replace ``<tag attr="assets/...">`` with ``data:`` URIs for small files.

    Returns the number of references rewritten. ``max_bytes=0`` is a no-op
    (nothing inlined). Files larger than ``max_bytes`` keep their relative
    paths. External (``http(s)://``, ``//``) URLs are untouched.
    """
    html_path = Path(html_path)
    out_path = Path(out_path)
    base_dir = html_path.parent
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    rewritten = 0
    for tag, attr, value in _iter_asset_refs(soup):
        local = base_dir / value
        if not local.exists():
            continue
        size = local.stat().st_size
        if size > max_bytes:
            continue
        mime, _ = mimetypes.guess_type(local.name)
        if mime is None:
            mime = "application/octet-stream"
        data = base64.b64encode(local.read_bytes()).decode("ascii")
        tag[attr] = f"data:{mime};base64,{data}"
        rewritten += 1
    out_path.write_text(str(soup), encoding="utf-8")
    log.info(
        "inline_small_assets",
        html_path=str(html_path),
        rewritten=rewritten,
        max_bytes=max_bytes,
    )
    return rewritten


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.post_process")
    parser.add_argument("capture_dir", type=Path, help="capture directory")
    parser.add_argument(
        "--inline-max-bytes",
        type=int,
        default=5000,
        help="inline assets below this size into the HTML (default: 5000)",
    )
    parser.add_argument(
        "--no-inline",
        action="store_true",
        help="skip inlining; only emit the asset audit",
    )
    args = parser.parse_args(argv)

    audit = audit_assets(args.capture_dir)
    print(
        f"assets: count={audit.count} total_bytes={audit.total_bytes}",
        file=sys.stderr,
    )
    if args.no_inline or audit.count == 0:
        return 0
    src = args.capture_dir / "index.html"
    if not src.exists():
        print(f"error: {src} not found", file=sys.stderr)
        return 2
    out = args.capture_dir / "index.inlined.html"
    n = inline_small_assets(src, out, max_bytes=args.inline_max_bytes)
    print(f"wrote {out} (rewrote {n} refs)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
