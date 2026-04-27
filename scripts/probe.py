"""Stage 1 — site reconnaissance.

Sends HEAD then GET to a target URL; extracts framework markers, response
headers, and a CSP summary. Used as the first step of the capture pipeline
to decide whether the site is worth processing and which strategy to apply.

Usage (CLI):
    python -m scripts.probe https://example.com --output probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

import requests
import structlog

log = structlog.get_logger()


_FRAMEWORK_MARKERS = (
    # (framework_name, [substrings to look for in HTML or x-powered-by header])
    ("next", ["__NEXT_DATA__", "next.js", "_next/static"]),
    ("vue", ["vue.runtime", "vue.global", "__vue_app__", "data-v-app"]),
    ("svelte", ["svelte", "sveltekit"]),
    ("react", ["react.production", "react-dom", "data-reactroot", 'id="root"']),
    ("angular", ["ng-version", "_nghost-", "angular.io"]),
    ("astro", ["astro-island", "astro:client"]),
)


def detect_framework(html: str, headers: dict[str, str]) -> str:
    """Best-effort framework guess. Returns ``"unknown"`` on no match.

    Order matters — Next.js often serves React markers too, so we check Next
    before React. Header detection short-circuits HTML scanning.
    """
    powered_by = (headers.get("x-powered-by") or "").lower()
    for name, _markers in _FRAMEWORK_MARKERS:
        if name in powered_by:
            return name
    lower_html = html.lower()
    for name, markers in _FRAMEWORK_MARKERS:
        if any(m.lower() in lower_html for m in markers):
            return name
    return "unknown"


def summarize_csp(headers: dict[str, str]) -> dict[str, list[str]]:
    """Parse a Content-Security-Policy header into a directive map.

    Directives are split on ``;``, each directive is split on whitespace
    where the first token is the directive name and the rest are sources.
    Returns an empty dict if no CSP is present.
    """
    raw = (
        headers.get("content-security-policy")
        or headers.get("Content-Security-Policy")
        or ""
    )
    if not raw:
        return {}
    out: dict[str, list[str]] = {}
    for clause in raw.split(";"):
        parts = clause.strip().split()
        if not parts:
            continue
        directive, *sources = parts
        out[directive.lower()] = sources
    return out


@dataclass
class ProbeResult:
    url: str
    status: int | None
    reachable: bool
    framework: str
    csp: dict[str, list[str]] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)


def run_probe(
    url: str, *, session: Any | None = None, timeout: float = 10.0
) -> ProbeResult:
    """Run HEAD then conditional GET. Returns ``ProbeResult`` always.

    Network errors are captured in ``result.error``; the function never raises.
    """
    sess = session if session is not None else requests.Session()
    try:
        head = sess.head(url, allow_redirects=True, timeout=timeout)
    except Exception as exc:
        log.warning("probe_head_failed", url=url, error=str(exc))
        return ProbeResult(
            url=url,
            status=None,
            reachable=False,
            framework="unknown",
            error=f"{type(exc).__name__}: {exc}",
        )

    headers = {k.lower(): v for k, v in head.headers.items()}
    if head.status_code >= 400:
        return ProbeResult(
            url=url,
            status=head.status_code,
            reachable=False,
            framework="unknown",
            csp=summarize_csp(headers),
            headers=headers,
        )

    try:
        get = sess.get(url, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        log.warning("probe_get_failed", url=url, error=str(exc))
        return ProbeResult(
            url=url,
            status=head.status_code,
            reachable=False,
            framework="unknown",
            csp=summarize_csp(headers),
            headers=headers,
            error=f"{type(exc).__name__}: {exc}",
        )

    framework = detect_framework(get.text, headers)
    log.info("probe_complete", url=url, status=head.status_code, framework=framework)
    return ProbeResult(
        url=url,
        status=head.status_code,
        reachable=True,
        framework=framework,
        csp=summarize_csp(headers),
        headers=headers,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.probe")
    parser.add_argument("url", help="target URL to probe")
    parser.add_argument(
        "--output",
        default="-",
        help="path to write JSON to (default: stdout)",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="per-request timeout in seconds"
    )
    args = parser.parse_args(argv)
    result = run_probe(args.url, timeout=args.timeout)
    payload = result.to_json()
    if args.output == "-":
        print(payload)
    else:
        from pathlib import Path

        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    return 0 if result.reachable else 1


if __name__ == "__main__":
    raise SystemExit(main())
