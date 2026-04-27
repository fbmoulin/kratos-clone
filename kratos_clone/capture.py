"""Hardened Playwright capture for SPA marketing sites.

Implements 5 patches over the v1 downloader to fix recall on lazy-loaded /
IntersectionObserver-gated content:

  Patch A — IntersectionObserver pre-fire polyfill (init script)
  Patch B — networkidle wait + DOM-stable predicate (MutationObserver settle)
  Patch C — Three-pass scroll (forward fast, forward slow, backward slow) + Lenis disable
  Patch D — Recursive shadow DOM + same-origin iframe serializer (Declarative Shadow DOM)
  Patch E — Computed-style snapshot to styles.json

Sources:
  https://playwright.dev/docs/api/class-page#page-add-init-script
  https://docs.anthropic.com/...  (workflow doc)
  https://github.com/gildas-lormeau/SingleFile (shadow DOM walker reference)
"""

from __future__ import annotations
import asyncio
import hashlib
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable
from playwright.async_api import async_playwright, Page, Route


# ── Constants ────────────────────────────────────────────────────────────────
DEFAULT_VIEWPORT = (1920, 1080)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ── Init scripts (injected BEFORE goto via add_init_script) ──────────────────
PATCH_A_IO_PREFIRE = r"""
// Patch A — IntersectionObserver pre-fire polyfill.
// Forces every observer to fire isIntersecting:true on observe(), so lazy-loaded
// content (images, sections gated by ScrollTrigger/AOS/Framer Motion) renders
// without depending on actual scroll-into-view.
(() => {
  if (window.__kratos_io_patched) return;
  window.__kratos_io_patched = true;
  const _IO = window.IntersectionObserver;
  window.IntersectionObserver = class {
    constructor(cb, opts) { this._cb = cb; this._opts = opts || {}; this._targets = []; }
    observe(el) {
      this._targets.push(el);
      queueMicrotask(() => {
        try {
          const rect = el.getBoundingClientRect();
          this._cb([{
            target: el,
            isIntersecting: true,
            intersectionRatio: 1,
            time: performance.now(),
            boundingClientRect: rect,
            intersectionRect: rect,
            rootBounds: null
          }], this);
        } catch(e) { /* swallow — best-effort */ }
      });
    }
    unobserve(el) { this._targets = this._targets.filter(t => t !== el); }
    disconnect() { this._targets = []; }
    takeRecords() { return []; }
    get root() { return this._opts.root || null; }
    get rootMargin() { return this._opts.rootMargin || '0px'; }
    get thresholds() { return [].concat(this._opts.threshold || 0); }
  };
  // Keep original on a back-channel for libs that feature-detect via constructor.toString
  window.__kratos_native_IO = _IO;
})();
"""

PATCH_D_SHADOW_DOM_HELPERS = r"""
// Patch D — recursive walker over the LIVE DOM (audit P1-A fix).
//
// PRIOR BUG: the previous implementation used (root || document.documentElement)
// .cloneNode(true) and then walked the clone looking for shadowRoot. Per HTML spec,
// cloneNode does NOT copy shadow roots — every element in the clone had
// shadowRoot === null, so the walker captured zero shadow content despite the
// manifest reporting Patch D as applied.
//
// FIX: walk the live document tree and serialize to a string ourselves, emitting
// Declarative Shadow DOM <template shadowrootmode="open"> for each open shadow root.
// Closed shadow roots cannot be serialized by spec — count them and surface in manifest.
//
// Returns: { html: string, skipped_closed_shadow_roots: number }.
window.__kratos_serialize_with_shadow = function(root) {
  const VOID = new Set([
    'area','base','br','col','embed','hr','img','input','link','meta',
    'param','source','track','wbr'
  ]);
  let skippedClosed = 0;

  const escAttr = (s) => String(s)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const escText = (s) => String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function serialize(node) {
    // TEXT_NODE
    if (node.nodeType === 3) return escText(node.nodeValue);
    // COMMENT_NODE
    if (node.nodeType === 8) return '<!--' + node.nodeValue + '-->';
    // CDATA_SECTION_NODE — drop, not valid in HTML
    if (node.nodeType !== 1) return '';

    const tag = node.tagName.toLowerCase();

    // Skip <script type="application/json"> bodies? No — preserve everything.
    let out = '<' + tag;
    for (let i = 0; i < node.attributes.length; i++) {
      const a = node.attributes[i];
      out += ' ' + a.name + '="' + escAttr(a.value) + '"';
    }
    out += '>';

    if (VOID.has(tag)) return out;

    // Emit shadow root BEFORE children (Declarative Shadow DOM convention)
    const sr = node.shadowRoot;
    if (sr) {
      if (sr.mode === 'open') {
        out += '<template shadowrootmode="open">';
        // Walk the actual shadow tree (live, not cloned)
        for (let i = 0; i < sr.childNodes.length; i++) {
          out += serialize(sr.childNodes[i]);
        }
        out += '</template>';
      } else {
        // mode === 'closed' — inaccessible by spec; count and skip silently
        skippedClosed++;
      }
    }

    // Children of light DOM
    for (let i = 0; i < node.childNodes.length; i++) {
      out += serialize(node.childNodes[i]);
    }

    out += '</' + tag + '>';
    return out;
  }

  const target = root || document.documentElement;
  const html = '<!DOCTYPE html>\n' + serialize(target);
  return { html: html, skipped_closed_shadow_roots: skippedClosed };
};
"""


# ── Wait predicates ──────────────────────────────────────────────────────────
DOM_STABLE_FUNC = r"""
// Resolves only after the DOM has not mutated for `stableMs` consecutive ms.
// Use as a page.waitForFunction predicate.
(stableMs) => new Promise((resolve) => {
  let timer = setTimeout(() => { obs.disconnect(); resolve(true); }, stableMs);
  const obs = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(() => { obs.disconnect(); resolve(true); }, stableMs);
  });
  obs.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
})
"""


# ── Config ───────────────────────────────────────────────────────────────────
@dataclass
class CaptureConfig:
    """Tunable knobs (all overridable via env vars KCD_* or constructor)."""

    viewport_width: int = field(
        default_factory=lambda: int(os.getenv("KCD_VIEWPORT_WIDTH", "1920"))
    )
    viewport_height: int = field(
        default_factory=lambda: int(os.getenv("KCD_VIEWPORT_HEIGHT", "1080"))
    )
    user_agent: str = field(
        default_factory=lambda: os.getenv("KCD_USER_AGENT", DEFAULT_USER_AGENT)
    )
    nav_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("KCD_NAV_TIMEOUT", "90000"))
    )
    dom_stable_ms: int = field(
        default_factory=lambda: int(os.getenv("KCD_DOM_STABLE_MS", "1500"))
    )
    network_idle_buffer_ms: int = field(
        default_factory=lambda: int(os.getenv("KCD_NETIDLE_BUFFER", "5000"))
    )
    scroll_passes: int = field(
        default_factory=lambda: int(os.getenv("KCD_SCROLL_PASSES", "3"))
    )
    scroll_settle_ms_fast: int = 400
    scroll_settle_ms_slow: int = 900
    scroll_jump_ratio_fast: float = 0.8
    scroll_jump_ratio_slow: float = 0.6
    headed: bool = field(
        default_factory=lambda: os.getenv("KCD_HEADED", "false").lower() == "true"
    )
    capture_computed_styles: bool = field(
        default_factory=lambda: (
            os.getenv("KCD_CAPTURE_COMPUTED_STYLES", "true").lower() == "true"
        )
    )
    use_io_polyfill: bool = field(
        default_factory=lambda: os.getenv("KCD_IO_POLYFILL", "true").lower() == "true"
    )
    use_shadow_walker: bool = field(
        default_factory=lambda: os.getenv("KCD_SHADOW_WALKER", "true").lower() == "true"
    )
    disable_lenis: bool = True
    block_analytics: bool = field(
        default_factory=lambda: (
            os.getenv("KCD_BLOCK_ANALYTICS", "true").lower() == "true"
        )
    )
    # P2-2: wall-clock budget for the 3-pass scroll loop. A pathological page
    # with infinite-scroll growing scrollHeight every pass could otherwise run
    # for many minutes (40s+ already observed at 50,000 px). When exceeded we
    # break out of the loop and emit `scroll_budget_exceeded: true` in manifest.
    max_scroll_seconds: float = field(
        default_factory=lambda: float(os.getenv("KCD_MAX_SCROLL_S", "120"))
    )
    # P1-E: global asset disk caps. Per-asset cap (8 MB) is unchanged but a
    # malicious site can serve 1000+ small assets to fill the disk. Cap by
    # cumulative bytes AND count.
    max_total_asset_mb: int = field(
        default_factory=lambda: int(os.getenv("KCD_MAX_TOTAL_MB", "200"))
    )
    max_assets: int = field(
        default_factory=lambda: int(os.getenv("KCD_MAX_ASSETS", "500"))
    )


# ── Asset hashing & filename helpers ─────────────────────────────────────────
def hash_url(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def asset_filename(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = urllib.parse.unquote(parsed.path).rstrip("/").split("/")[-1] or "asset"
    # sanitize
    name, _, ext = path.rpartition(".")
    if not name:
        name = ext
        ext = ""
    name = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:30] or "asset"
    h = hash_url(url)
    return f"{name}_{h}.{ext}" if ext else f"{name}_{h}"


# ── Logger callback type ─────────────────────────────────────────────────────
LogCallback = Optional[Callable[[str], None]]


# ── Main capture ─────────────────────────────────────────────────────────────
class HardenedCapture:
    """Capture an SPA marketing site with maximum recall.

    Usage:
        cfg = CaptureConfig()
        cap = HardenedCapture(url, output_dir, cfg, log=print)
        manifest = await cap.run()
    """

    def __init__(
        self,
        url: str,
        output_dir: str | Path,
        cfg: CaptureConfig | None = None,
        log: LogCallback = None,
    ):
        self.url = url
        self.output_dir = Path(output_dir)
        self.assets_dir = self.output_dir / "assets"
        self.cfg = cfg or CaptureConfig()
        self._log = log or (lambda m: None)
        self.captured_assets: dict[str, str] = {}  # url → relative filename
        self.network_resources: list[dict] = []
        self.errors: list[str] = []
        self.shadow_skipped_closed: int = 0  # Patch D walker stat
        self._pending_writes: set[asyncio.Task] = set()  # P1-B asset write tracking
        # P1-E: cumulative tracking for disk caps
        self._total_asset_bytes: int = 0
        self._asset_count_dropped: int = 0  # how many assets we refused due to caps
        # P2-2: scroll budget exceeded flag
        self.scroll_budget_exceeded: bool = False

    def log(self, msg: str) -> None:
        self._log(msg)

    async def run(self) -> dict:
        """Returns a manifest dict with stats and file paths."""
        t_start = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(exist_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=not self.cfg.headed)
            context = await browser.new_context(
                viewport={
                    "width": self.cfg.viewport_width,
                    "height": self.cfg.viewport_height,
                },
                user_agent=self.cfg.user_agent,
                locale="en-US",
                timezone_id="America/New_York",
            )

            # Patch A — IntersectionObserver pre-fire (BEFORE first navigation)
            if self.cfg.use_io_polyfill:
                await context.add_init_script(PATCH_A_IO_PREFIRE)
                self.log("🧬 Patch A: IntersectionObserver pre-fire polyfill injected")

            # Patch D helpers
            if self.cfg.use_shadow_walker:
                await context.add_init_script(PATCH_D_SHADOW_DOM_HELPERS)
                self.log("🧬 Patch D: Shadow DOM walker helpers injected")

            # Block analytics noise (saves bandwidth + reduces network-idle delay)
            if self.cfg.block_analytics:
                await context.route("**/*", self._route_handler)

            page = await context.new_page()

            # Network capture — wrap async handler in a tracked task so we can
            # await all pending writes before context.close() (P1-B fix).
            def _on_response_tracked(response):
                task = asyncio.create_task(self._on_response(response))
                self._pending_writes.add(task)
                task.add_done_callback(self._pending_writes.discard)

            page.on("response", _on_response_tracked)
            page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))

            try:
                self.log(f"🌐 Loading {self.url}...")
                # Patch B — networkidle is the right choice here, NOT domcontentloaded
                await page.goto(
                    self.url, wait_until="networkidle", timeout=self.cfg.nav_timeout_ms
                )
                self.log("✓ Page loaded (networkidle)")
            except Exception as e:
                self.log(
                    f"⚠️  networkidle timeout, falling back to domcontentloaded: {e}"
                )
                try:
                    await page.goto(
                        self.url,
                        wait_until="domcontentloaded",
                        timeout=self.cfg.nav_timeout_ms,
                    )
                except Exception as e2:
                    self.errors.append(f"navigation: {e2}")
                    raise

            # Patch B — DOM-stable predicate
            try:
                self.log(
                    f"⏳ Waiting for DOM to stabilize ({self.cfg.dom_stable_ms} ms)..."
                )
                await page.wait_for_function(
                    DOM_STABLE_FUNC, arg=self.cfg.dom_stable_ms, timeout=30000
                )
                self.log("✓ DOM stable")
            except Exception as e:
                self.log(f"⚠️  DOM-stable wait timed out, proceeding: {e}")

            # Disable Lenis if present
            if self.cfg.disable_lenis:
                await page.evaluate("""
                    if (window.lenis && typeof window.lenis.destroy === 'function') {
                        try { window.lenis.destroy(); } catch(e) {}
                        window.lenis = null;
                    }
                    if (window.Lenis) { window.Lenis = null; }
                """)
                self.log("🧬 Lenis smooth-scroll disabled (if present)")

            # Patch C — Three-pass scroll
            await self._three_pass_scroll(page)

            # Force-load all <img loading="lazy"> by removing the attribute
            await page.evaluate("""
                document.querySelectorAll('img[loading="lazy"]').forEach(i => {
                    i.removeAttribute('loading');
                    if (i.dataset && i.dataset.src) i.src = i.dataset.src;
                });
            """)
            await page.wait_for_timeout(800)

            # Iframe extraction (Aura/srcdoc pattern preserved from v1 logic)
            html = await self._extract_html(page)

            # Patch E — Computed-style snapshot
            styles_json = None
            if self.cfg.capture_computed_styles:
                self.log("🎨 Capturing computed styles...")
                styles_json = await self._capture_computed_styles(page)

            # P1-B fix: explicitly wait for pending response-handler tasks before
            # closing the context. Previously a 500 ms sleep was the only guard,
            # which let late asset writes get truncated mid-byte. Now we await
            # every tracked task; the timeout caps total wait at 10s in case a
            # response body() never resolves.
            if self._pending_writes:
                self.log(
                    f"⏳ Awaiting {len(self._pending_writes)} pending asset write(s)..."
                )
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self._pending_writes, return_exceptions=True),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    leaked = len(self._pending_writes)
                    self.log(f"⚠️  {leaked} asset write(s) did not finish in 10s")
                    self.errors.append(f"asset_write_timeout: {leaked} pending")

            await context.close()
            await browser.close()

        # Write outputs
        from .post import rewrite_html_assets

        index_path = self.output_dir / "index.html"
        rewritten_html = rewrite_html_assets(html, self.captured_assets, self.url)
        index_path.write_text(rewritten_html, encoding="utf-8")

        if styles_json is not None:
            (self.output_dir / "styles.json").write_text(
                json.dumps(styles_json, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

        manifest = {
            "url": self.url,
            "captured_at": int(time.time()),
            "duration_s": round(time.time() - t_start, 2),
            "assets_count": len(self.captured_assets),
            "html_size_kb": round(len(rewritten_html) / 1024, 1),
            "styles_json_size_kb": (
                round(len(json.dumps(styles_json)) / 1024, 1) if styles_json else None
            ),
            "shadow_skipped_closed": self.shadow_skipped_closed,
            "scroll_budget_exceeded": self.scroll_budget_exceeded,
            "asset_caps_dropped": self._asset_count_dropped,
            "total_asset_bytes": self._total_asset_bytes,
            "errors": self.errors,
            "config": asdict(self.cfg),
            "patches_applied": [
                "A_io_prefire" if self.cfg.use_io_polyfill else None,
                "B_dom_stable",
                "C_three_pass_scroll",
                "D_shadow_walker" if self.cfg.use_shadow_walker else None,
                "E_computed_styles" if self.cfg.capture_computed_styles else None,
            ],
        }
        manifest["patches_applied"] = [p for p in manifest["patches_applied"] if p]
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.log(
            f"✅ Capture complete: {len(self.captured_assets)} assets, "
            f"{manifest['html_size_kb']} KB HTML"
        )
        return manifest

    async def _route_handler(self, route: Route):
        """Block analytics/tracking for cleaner network-idle and faster captures."""
        url = route.request.url
        BLOCK_PATTERNS = (
            "google-analytics.com",
            "googletagmanager.com",
            "googletagservices.com",
            "doubleclick.net",
            "facebook.net",
            "facebook.com/tr",
            "hotjar.com",
            "segment.com",
            "segment.io",
            "mixpanel.com",
            "intercom.io",
            "sentry.io",
            "fullstory.com",
            "logrocket.com",
            "amplitude.com",
            "snowplow",
            "linkedin.com/li",
            "/collect?",
            "/pixel?",
            "supabase.co/realtime",
        )
        if any(p in url for p in BLOCK_PATTERNS):
            await route.abort()
        else:
            await route.continue_()

    async def _on_response(self, response):
        """Capture network resources for asset rewriting."""
        try:
            url = response.url
            ctype = (response.headers or {}).get("content-type", "")
            status = response.status
            if status >= 400:
                return
            # Only capture asset types
            if not any(
                p in ctype.lower()
                for p in (
                    "css",
                    "javascript",
                    "image/",
                    "font/",
                    "octet-stream",
                    "woff",
                    "woff2",
                )
            ):
                return
            if url in self.captured_assets:
                return
            # P1-E: enforce global asset count cap before fetching body
            if len(self.captured_assets) >= self.cfg.max_assets:
                self._asset_count_dropped += 1
                return
            try:
                body = await response.body()
                if len(body) > 8 * 1024 * 1024:  # 8 MB cap per asset
                    return
                # P1-E: enforce cumulative bytes cap before write
                max_total = self.cfg.max_total_asset_mb * 1024 * 1024
                if self._total_asset_bytes + len(body) > max_total:
                    self._asset_count_dropped += 1
                    return
                fname = asset_filename(url)
                (self.assets_dir / fname).write_bytes(body)
                self.captured_assets[url] = f"assets/{fname}"
                self._total_asset_bytes += len(body)
                self.network_resources.append(
                    {"url": url, "size": len(body), "ctype": ctype}
                )
            except Exception:
                pass  # body() can fail for some responses; skip
        except Exception as e:
            self.errors.append(f"response_handler: {e}")

    async def _three_pass_scroll(self, page: Page):
        """Patch C — three-pass scroll: forward-fast, forward-slow, backward-slow.

        P2-2 fix: hard wall-clock budget (`KCD_MAX_SCROLL_S`, default 120s).
        Pages with infinite-scroll feeds can grow scrollHeight every pass,
        producing an effectively unbounded loop. Once the budget is exceeded
        we break out and emit `scroll_budget_exceeded: true` in manifest so
        operators can flag captures that finished early.
        """
        budget_start = time.time()

        def over_budget() -> bool:
            return (time.time() - budget_start) > self.cfg.max_scroll_seconds

        h = await page.evaluate("() => document.body.scrollHeight")
        vh = await page.evaluate("() => window.innerHeight")

        # Pass 1: forward fast (warm-up)
        if self.cfg.scroll_passes >= 1 and not over_budget():
            self.log("📜 Scroll pass 1/3 (forward fast)...")
            for y in range(0, h + vh, int(vh * self.cfg.scroll_jump_ratio_fast)):
                if over_budget():
                    self.scroll_budget_exceeded = True
                    break
                await page.evaluate(
                    f"window.scrollTo({{top: {y}, behavior: 'instant'}})"
                )
                await page.wait_for_timeout(self.cfg.scroll_settle_ms_fast)

        # Pass 2: forward slow (settle observers)
        if self.cfg.scroll_passes >= 2 and not over_budget():
            self.log("📜 Scroll pass 2/3 (forward slow)...")
            h = await page.evaluate("() => document.body.scrollHeight")
            for y in range(0, h + vh, int(vh * self.cfg.scroll_jump_ratio_slow)):
                if over_budget():
                    self.scroll_budget_exceeded = True
                    break
                await page.evaluate(
                    f"window.scrollTo({{top: {y}, behavior: 'instant'}})"
                )
                await page.wait_for_timeout(self.cfg.scroll_settle_ms_slow)

        # Pass 3: backward slow (parallax/sticky)
        if self.cfg.scroll_passes >= 3 and not over_budget():
            self.log("📜 Scroll pass 3/3 (backward slow)...")
            h = await page.evaluate("() => document.body.scrollHeight")
            for y in range(h, -vh, -int(vh * self.cfg.scroll_jump_ratio_slow)):
                if over_budget():
                    self.scroll_budget_exceeded = True
                    break
                await page.evaluate(
                    f"window.scrollTo({{top: {max(0, y)}, behavior: 'instant'}})"
                )
                await page.wait_for_timeout(self.cfg.scroll_settle_ms_slow)

        # Return to top
        await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        await page.wait_for_timeout(500)
        elapsed = time.time() - budget_start
        if self.scroll_budget_exceeded:
            self.log(
                f"⚠️  Scroll budget exceeded ({elapsed:.1f}s > "
                f"{self.cfg.max_scroll_seconds}s) — capture may be incomplete"
            )
        else:
            self.log(f"✓ Three-pass scroll complete ({elapsed:.1f}s)")

    async def _extract_html(self, page: Page) -> str:
        """Pick the most informative source: main doc, iframe[srcdoc], or same-origin frame.

        P1-G fix: do NOT take iframe[srcdoc] unconditionally. Compare length against
        the main doc and require the iframe content to be at least
        `KCD_IFRAME_MIN_RATIO` of main doc length (default 0.5) — otherwise we'd
        replace 100KB of real content with a 2KB cookie-banner srcdoc.
        Opt-out entirely via `KCD_NO_IFRAME_SRCDOC=true`.

        P1-D fix: same-origin check uses `urlparse().netloc` instead of substring
        match (the old `"srcdoc" in f_url.lower()` could be triggered by any URL
        whose path contained the word "srcdoc").

        Uses Patch D shadow DOM walker if enabled.
        """
        # Capture main doc first so we can compare lengths
        main_html = (
            await page.evaluate("() => document.documentElement.outerHTML") or ""
        )
        main_html_len = len(main_html)

        if os.getenv("KCD_NO_IFRAME_SRCDOC", "false").lower() == "true":
            self.log("🔍 KCD_NO_IFRAME_SRCDOC=true → skipping srcdoc detection")
        else:
            # Iframe srcdoc detection (Aura wraps user sites in iframe[srcdoc])
            iframe_html = await page.evaluate(r"""
                () => {
                    const ifr = document.querySelector('iframe[srcdoc]');
                    if (ifr && ifr.srcdoc && ifr.srcdoc.length > 1000) {
                        const tmp = document.createElement('textarea');
                        tmp.innerHTML = ifr.srcdoc;
                        return tmp.value;
                    }
                    return null;
                }
            """)
            if iframe_html:
                ratio = (len(iframe_html) / main_html_len) if main_html_len else 0.0
                min_ratio = float(os.getenv("KCD_IFRAME_MIN_RATIO", "0.5"))
                if ratio >= min_ratio:
                    self.log(
                        f"🔍 Using iframe[srcdoc] ({len(iframe_html) // 1024} KB, "
                        f"ratio={ratio:.2f} ≥ {min_ratio})"
                    )
                    return iframe_html
                else:
                    self.log(
                        f"⚠️  iframe[srcdoc] too small ({len(iframe_html)} B vs "
                        f"{main_html_len} B main, ratio={ratio:.2f} < {min_ratio}) — "
                        "preferring main doc"
                    )

        # Same-origin iframe whose document we can access — proper netloc compare
        from urllib.parse import urlparse

        page_netloc = urlparse(self.url).netloc
        for f in page.frames:
            if f == page.main_frame:
                continue
            try:
                f_url = f.url
                if not f_url or f_url == "about:blank":
                    continue
                f_netloc = urlparse(f_url).netloc
                # P1-D: strict netloc match OR explicit about:srcdoc
                same_origin = bool(f_netloc) and f_netloc == page_netloc
                is_srcdoc = f_url.startswith("about:srcdoc")
                if same_origin or is_srcdoc:
                    f_html = await f.evaluate(
                        "() => document.documentElement.outerHTML"
                    )
                    if len(f_html) > 1000 and len(f_html) >= main_html_len * 0.5:
                        self.log(
                            "🔍 Using same-origin iframe content "
                            f"({len(f_html) // 1024} KB, "
                            f"netloc={f_netloc or 'about:srcdoc'})"
                        )
                        return "<!DOCTYPE html>\n" + f_html
            except Exception as e:
                self.log(f"⚠️  iframe enumeration error: {e}")

        # Default: main document with shadow walker if enabled
        if self.cfg.use_shadow_walker:
            result = await page.evaluate(
                "() => window.__kratos_serialize_with_shadow(document.documentElement)"
            )
            html = result["html"]
            self.shadow_skipped_closed = int(
                result.get("skipped_closed_shadow_roots", 0)
            )
            self.log(
                f"📄 Captured main doc with shadow walker ({len(html) // 1024} KB"
                + (
                    f", {self.shadow_skipped_closed} closed shadow root(s) skipped)"
                    if self.shadow_skipped_closed
                    else ")"
                )
            )
        else:
            html = main_html or await page.content()
            self.log(f"📄 Captured main doc ({len(html) // 1024} KB)")
        return html

    async def _capture_computed_styles(self, page: Page) -> dict:
        """Patch E — sample key computed styles per element for downstream extraction."""
        return await page.evaluate(r"""
            () => {
                const props = ['fontSize','fontWeight','fontFamily','lineHeight','letterSpacing',
                               'color','backgroundColor','backgroundImage',
                               'borderRadius','borderWidth','borderColor','borderStyle',
                               'boxShadow','padding','margin','gap',
                               'transitionDuration','transitionTimingFunction','transitionProperty',
                               'animation','transform','opacity','display'];
                const cssPath = (el) => {
                    if (!el || !el.tagName) return '';
                    const parts = [];
                    let n = el;
                    let depth = 0;
                    while (n && n.nodeType === 1 && depth < 8) {
                        let s = n.tagName.toLowerCase();
                        if (n.id) { s += '#' + n.id; parts.unshift(s); break; }
                        if (n.className && typeof n.className === 'string') {
                            const c = n.className.split(/\s+/).filter(Boolean).slice(0, 2).join('.');
                            if (c) s += '.' + c;
                        }
                        const sib = Array.from(n.parentNode?.children || []).indexOf(n);
                        s += `:nth-child(${sib + 1})`;
                        parts.unshift(s);
                        n = n.parentElement;
                        depth++;
                    }
                    return parts.join('>');
                };
                const out = {};
                let i = 0;
                document.querySelectorAll('h1,h2,h3,h4,h5,h6,p,a,button,section,nav,header,footer,article,div[class*="card"],div[class*="hero"]').forEach((el) => {
                    if (i > 800) return;  // cap at 800 elements
                    const cs = getComputedStyle(el);
                    const o = {
                        tag: el.tagName.toLowerCase(),
                        classes: (el.className && typeof el.className === 'string') ? el.className : '',
                        selector: cssPath(el),
                    };
                    for (const p of props) o[p] = cs[p];
                    out['e' + i] = o;
                    i++;
                });
                return out;
            }
        """)
