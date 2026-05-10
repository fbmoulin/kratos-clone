import contextlib
import gc
import os
import queue
import re
import shutil
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import structlog
from flask import Flask, Response, jsonify, render_template, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from downloader import WebsiteDownloader, get_site_name, zip_directory

# Structured logging — shared config (also used by `python -m kratos_clone`).
from kratos_clone._logging import configure_logging

configure_logging()

logger = structlog.get_logger("app")

app = Flask(__name__)
# Global body cap. /api/personalize/run (Phase 4) accepts a logo upload up to
# 2 MiB plus brief JSON, so the global cap is 8 MiB. Each non-personalize
# endpoint enforces its own per-route cap (e.g. 64 KiB on /api/client-errors)
# so the global is just the chunked-transfer-encoding backstop, not the actual
# threshold for non-upload endpoints.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# Trust X-Forwarded-For only when explicitly enabled — security review caught
# that without ProxyFix, every external client appears to share the proxy IP
# (e.g. 127.0.0.1 behind nginx) and the rate limiter applies a single global
# bucket. Set TRUST_PROXY=1 only when behind a known reverse proxy that strips
# client-supplied X-Forwarded-For (otherwise spoofable).
if os.getenv("TRUST_PROXY", "0").strip() == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # type: ignore[method-assign]
    logger.info("proxy_fix_enabled", x_for=1, x_proto=1)

# P2-5: rate-limit /api/client-errors. Lazy: limiter is bound to a route via
# `@limiter.limit(...)` at decoration time but its storage backend (which can
# spawn a janitor thread for in-memory expiration) is initialized only inside
# `create_app()`. This keeps `import app` side-effect-free (audit P2-7) — the
# CI smoke job verifies threading.active_count() does not grow on import.
limiter = Limiter(key_func=get_remote_address)

DOWNLOAD_FOLDER = "downloads"

# Request-ID middleware (Phase 6).
# Every request is assigned a UUID4 (or echoes a client-supplied one if it
# matches the safe-character set) and bound to structlog's contextvars so
# every log line in the request scope inherits it. Helps trace a single
# request across structlog backend logs + the browser observability stream.
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _safe_request_id(value: str | None) -> str:
    if value and _REQUEST_ID_RE.match(value):
        return value
    return str(uuid.uuid4())


@app.before_request
def _bind_request_id() -> None:
    rid = _safe_request_id(request.headers.get("X-Request-ID"))
    request.environ["request_id"] = rid
    structlog.contextvars.bind_contextvars(request_id=rid)


@app.after_request
def _emit_request_id(response: Response) -> Response:
    rid = request.environ.get("request_id")
    if rid:
        response.headers["X-Request-ID"] = rid
    structlog.contextvars.clear_contextvars()
    return response


# Tunable retention windows (seconds)
COMPLETE_TTL = 1800  # complete sessions (zip waiting for download)
ERROR_TTL = 600  # error sessions
PROCESSING_TTL = 1800  # safety net for stuck/zombie sessions
ORPHAN_FILE_TTL = 1800  # files on disk with no matching session
CLEANUP_INTERVAL = 300  # how often the janitor runs

# Per-session state. Always touch via session_lock when iterating/mutating.
# Module-level so routes (registered via @app.route below) can close over them;
# cleared/reset by tests via _reset_state().
message_queues: dict[str, queue.Queue[str]] = {}
download_results: dict[str, dict[str, Any]] = {}
session_lock = threading.Lock()


def _reset_state() -> None:
    """Test helper — wipe in-memory session state without touching disk."""
    with session_lock:
        message_queues.clear()
        download_results.clear()


def cleanup_downloads_folder() -> None:
    """Remove all files and folders from downloads directory."""
    try:
        for item in os.listdir(DOWNLOAD_FOLDER):
            item_path = os.path.join(DOWNLOAD_FOLDER, item)
            if os.path.isfile(item_path):
                os.remove(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)
        logger.info("downloads_folder_cleared", folder=DOWNLOAD_FOLDER)
    except Exception as e:
        logger.warning("downloads_folder_clear_failed", folder=DOWNLOAD_FOLDER, error=str(e))


def _purge_session(session_id: str) -> None:
    """Remove a single session's in-memory state and any disk artifacts."""
    with session_lock:
        result = download_results.pop(session_id, None)
        message_queues.pop(session_id, None)

    if not result:
        return

    zip_path = result.get("zip_path")
    if zip_path and os.path.exists(zip_path):
        with contextlib.suppress(Exception):
            os.remove(zip_path)

    # Some error paths may leave the raw directory behind.
    raw_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    if os.path.isdir(raw_dir):
        with contextlib.suppress(Exception):
            shutil.rmtree(raw_dir)


def _cleanup_orphan_files() -> None:
    """
    Remove files/dirs in downloads/ that don't belong to any active session.
    Catches leftovers from worker crashes or restarts.
    """
    try:
        with session_lock:
            known_ids = set(download_results.keys())

        now = time.time()
        for entry in os.listdir(DOWNLOAD_FOLDER):
            path = os.path.join(DOWNLOAD_FOLDER, entry)
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue

            # Strip trailing .zip to recover the session uuid
            base = entry[:-4] if entry.endswith(".zip") else entry
            if base in known_ids:
                continue
            if age < ORPHAN_FILE_TTL:
                continue

            try:
                if os.path.isfile(path):
                    os.remove(path)
                    logger.info("orphan_file_removed", entry=entry, age_s=int(age))
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                    logger.info("orphan_dir_removed", entry=entry, age_s=int(age))
            except Exception as e:
                logger.warning("orphan_remove_failed", entry=entry, error=str(e))
    except Exception as e:
        logger.error("janitor_orphan_scan_failed", error=str(e))


def cleanup_abandoned_sessions() -> None:
    """
    Janitor thread: removes complete/error/zombie sessions and orphan files.
    Runs every CLEANUP_INTERVAL seconds.
    """
    while True:
        time.sleep(CLEANUP_INTERVAL)
        try:
            now = time.time()
            to_remove = []

            with session_lock:
                snapshot = list(download_results.items())

            for session_id, result in snapshot:
                status = result.get("status")
                created_at = result.get("created_at") or result.get("started_at") or 0
                if not created_at:
                    continue
                age = now - created_at

                if status == "complete" and age > COMPLETE_TTL:
                    to_remove.append((session_id, "complete"))
                elif status == "error" and age > ERROR_TTL:
                    to_remove.append((session_id, "error"))
                elif status == "processing" and age > PROCESSING_TTL:
                    to_remove.append((session_id, "zombie"))

            for session_id, reason in to_remove:
                _purge_session(session_id)
                logger.info("session_purged", session_id=session_id[:8], reason=reason)

            _cleanup_orphan_files()
            gc.collect()
        except Exception as e:
            logger.error("janitor_cycle_failed", error=str(e))


def create_app(start_janitor: bool = True, run_boot_cleanup: bool = True) -> Flask:
    """Initialize side-effecting parts of the app: ensure DOWNLOAD_FOLDER exists,
    bind the rate limiter, optionally clear stale downloads on boot, and
    optionally start the janitor thread. Returns the module-level `app` for
    chaining.

    Tests call `create_app(start_janitor=False, run_boot_cleanup=False)` to get
    a fresh, side-effect-free Flask instance. Production uses `wsgi.py` which
    calls `create_app()` with defaults.

    Idempotent re: the Flask `app` object (always the same instance); NOT
    idempotent re: spawning janitor threads — calling twice will start two.
    """
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    # Bind limiter storage now (memory:// would otherwise spawn an
    # expiration thread at module-import time and trip the smoke test).
    app.config.setdefault(
        "RATELIMIT_STORAGE_URI",
        os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    )
    limiter.init_app(app)
    if run_boot_cleanup:
        cleanup_downloads_folder()
    if start_janitor:
        threading.Thread(target=cleanup_abandoned_sessions, daemon=True).start()
        logger.info("janitor_started", interval_s=CLEANUP_INTERVAL)
    return app


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/health")
def health() -> Response:
    """Lightweight health endpoint with memory + session counts for monitoring."""
    info: dict[str, Any] = {"status": "ok"}
    with session_lock:
        info["sessions"] = len(download_results)
        info["queues"] = len(message_queues)

    try:
        import psutil

        proc = psutil.Process()
        info["rss_mb"] = round(proc.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        # psutil is optional - fall back to resource module on POSIX
        try:
            import resource

            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS reports bytes, Linux reports kilobytes
            divisor = 1024 * 1024 if os.uname().sysname == "Darwin" else 1024
            info["rss_mb"] = round(rss_kb / divisor, 1)
        except Exception:
            pass

    return jsonify(info)


@app.route("/start-download", methods=["POST"])
def start_download() -> tuple[Response, int] | Response:
    """Start download process and return session ID for SSE."""
    data = request.get_json(silent=True) or {}
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    session_id = str(uuid.uuid4())
    now = time.time()

    with session_lock:
        message_queues[session_id] = queue.Queue()
        download_results[session_id] = {
            "status": "processing",
            "zip_path": None,
            "filename": None,
            "started_at": now,
        }

    thread = threading.Thread(target=process_download, args=(session_id, url))
    thread.daemon = True
    thread.start()

    return jsonify({"session_id": session_id})


def process_download(session_id: str, url: str) -> None:
    """Background download worker."""
    with session_lock:
        q = message_queues.get(session_id)
    if q is None:
        return

    download_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    zip_path = os.path.join(DOWNLOAD_FOLDER, f"{session_id}.zip")

    def log_callback(message: str) -> None:
        q.put(message)

    downloader = None
    try:
        downloader = WebsiteDownloader(url, download_dir, log_callback=log_callback)
        success = downloader.process()

        if not success:
            q.put("❌ Falha no download")
            with session_lock:
                download_results[session_id] = {
                    "status": "error",
                    "error": "Failed to download site",
                    "created_at": time.time(),
                }
            return

        site_name = get_site_name(url)
        zip_filename = f"{site_name}.zip"

        q.put("📦 Criando arquivo ZIP...")
        zip_directory(download_dir, zip_path)

        # Free raw files immediately
        if os.path.isdir(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)

        q.put("🎉 Download pronto!")
        with session_lock:
            download_results[session_id] = {
                "status": "complete",
                "zip_path": zip_path,
                "filename": zip_filename,
                "created_at": time.time(),
            }

    except Exception as e:
        q.put(f"❌ Erro: {str(e)}")
        with session_lock:
            download_results[session_id] = {
                "status": "error",
                "error": str(e),
                "created_at": time.time(),
            }
        # Best-effort cleanup of partial artifacts
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            with contextlib.suppress(Exception):
                os.remove(zip_path)

    finally:
        # Drop downloader reference so its in-memory buffers can be GC'd
        downloader = None
        gc.collect()


@app.route("/stream/<session_id>")
def stream(session_id: str) -> Response:
    """SSE endpoint for log streaming."""

    def generate() -> Iterator[str]:
        with session_lock:
            q = message_queues.get(session_id)

        if q is None:
            yield "data: ❌ Sessão não encontrada\n\n"
            yield "event: done\ndata: error\n\n"
            return

        # Hard cap how long a single SSE connection can live to avoid
        # accumulating zombie generators.
        deadline = time.time() + 30 * 60  # 30 minutes

        while True:
            if time.time() > deadline:
                yield "data: ⏱️ Conexão encerrada por inatividade\n\n"
                yield "event: done\ndata: timeout\n\n"
                return

            try:
                message = q.get(timeout=30)
                yield f"data: {message}\n\n"

                with session_lock:
                    result = download_results.get(session_id, {})
                if result.get("status") in ("complete", "error"):
                    yield f"event: done\ndata: {result['status']}\n\n"
                    return

            except queue.Empty:
                with session_lock:
                    result = download_results.get(session_id, {})
                # Worker died/finished without final message - don't hang forever
                if result.get("status") in ("complete", "error"):
                    yield f"event: done\ndata: {result['status']}\n\n"
                    return
                yield ": keepalive\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/download-file/<session_id>")
def download_file(session_id: str) -> Response | tuple[str, int]:
    """Download the generated ZIP file and clean up immediately."""
    with session_lock:
        result = download_results.get(session_id)

    if not result or result.get("status") != "complete":
        return "File not ready", 404

    zip_path = result["zip_path"]
    filename = result["filename"]

    if not zip_path or not os.path.exists(zip_path):
        # File was already cleaned up - drop the stale session entry
        _purge_session(session_id)
        return "File not found", 404

    try:
        response = send_file(zip_path, as_attachment=True, download_name=filename)

        def cleanup() -> None:
            time.sleep(2)
            _purge_session(session_id)
            logger.info(
                "session_purged_after_download",
                session_id=session_id[:8],
                filename=filename,
            )

        threading.Thread(target=cleanup, daemon=True).start()
        return response
    except Exception as e:
        logger.error("send_file_failed", session_id=session_id[:8], error=str(e))
        return "Error sending file", 500


# ── Frontend error ingestion ────────────────────────────────────────────────
# Receives errors captured in the browser by the inline logger in
# templates/index.html (window.onerror, unhandledrejection, console.error,
# fetch/EventSource failures). Browser sends batched JSON via sendBeacon.
# All entries land in the same structlog stream with logger="frontend",
# so server + client errors are queryable together.

# Hard caps to keep this endpoint cheap and DoS-resistant.
_FRONTEND_MAX_ENTRIES_PER_REQUEST = 20
_FRONTEND_MAX_BODY_BYTES = 32 * 1024  # 32 KB
_FRONTEND_MAX_FIELD_LEN = 2000

# P2-4: strip control chars (esp. ANSI escape sequences \x1b[) before passing to
# console renderer — prevents a malicious entry from clearing or scrolling the
# operator's terminal in dev mode (LOG_FORMAT=console).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

frontend_logger = structlog.get_logger("frontend")


def _truncate(value: Any, limit: int = _FRONTEND_MAX_FIELD_LEN) -> str | None:
    if value is None:
        return None
    s = _CONTROL_CHARS_RE.sub("?", str(value))
    return s if len(s) <= limit else s[:limit] + "…"


def _strip_query(url: Any) -> str | None:
    """P1-I: drop query string + fragment from logged URLs.

    Avoids capturing tokens, session IDs, PII parameters into structured logs
    that may be exported to 3rd-party aggregators (LGPD/GDPR concern). Keeps
    scheme + host + pathname only.
    """
    if not url:
        return None
    s = str(url)
    for sep in ("?", "#"):
        i = s.find(sep)
        if i >= 0:
            s = s[:i]
    return s


@app.route("/api/client-errors", methods=["POST"])
@limiter.limit(os.getenv("CLIENT_ERRORS_RATE_LIMIT", "60 per minute"))
def client_errors() -> tuple[Response, int] | tuple[str, int]:
    """Ingest frontend error reports from the browser logger."""
    # P2-3: refuse non-JSON content-types. `force=True` previously allowed
    # `text/plain` which bypasses CORS preflight; we now require declared JSON.
    ctype = (request.content_type or "").split(";", 1)[0].strip().lower()
    if ctype and ctype != "application/json":
        return jsonify({"error": "content-type must be application/json"}), 415

    # Per-route cap. Flask's app-wide MAX_CONTENT_LENGTH (1 MiB) is the backstop
    # for chunked-transfer-encoding requests where Content-Length is missing.
    # `cache=True` so request.get_json() can re-read after this size check.
    raw_len = request.content_length or 0
    if raw_len > _FRONTEND_MAX_BODY_BYTES:
        return jsonify({"error": "payload too large"}), 413

    raw_body = request.get_data(cache=True)
    if len(raw_body) > _FRONTEND_MAX_BODY_BYTES:
        return jsonify({"error": "payload too large"}), 413

    try:
        body = request.get_json(silent=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    if not isinstance(body, dict):
        # Empty/null/list/string bodies — no entries to log, return 204 (RFC 9110)
        return ("", 204)

    entries = body.get("entries")
    if entries is None:
        return ("", 204)
    if not isinstance(entries, list):
        return jsonify({"error": "entries must be a list"}), 400

    accepted = 0
    for entry in entries[:_FRONTEND_MAX_ENTRIES_PER_REQUEST]:
        if not isinstance(entry, dict):
            continue
        level = str(entry.get("level", "error")).lower()
        if level not in ("debug", "info", "warning", "error", "critical"):
            level = "error"
        log = getattr(frontend_logger, level, frontend_logger.error)
        log(
            entry.get("event", "client_event"),
            message=_truncate(entry.get("message")),
            stack=_truncate(entry.get("stack")),
            url=_truncate(_strip_query(entry.get("url")), 500),
            user_agent=_truncate(entry.get("userAgent"), 300),
            ts_client=entry.get("ts"),
            session_id=_truncate(entry.get("sessionId"), 64),
            extra=_truncate(entry.get("extra")),
        )
        accepted += 1
    if accepted == 0:
        return ("", 204)  # RFC 9110: 204 must not have a body
    return jsonify({"accepted": accepted}), 200


# ── Phase 4 personalization routes ──────────────────────────────────────────

_PERSONALIZE_BRIEF_MAX_BYTES = 4 * 1024  # 4 KiB JSON brief
_PERSONALIZE_RUN_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB multipart (logo ≤ 2 MiB)
_PERSONALIZE_LOGO_MAX_BYTES = 2 * 1024 * 1024


@app.route("/personalize")
def personalize_page() -> str:
    """Render the Phase 4 intake form. No auth, mirrors the legacy / route."""
    return render_template("personalize.html")


@app.route("/api/personalize/structure", methods=["POST"])
@limiter.limit(os.getenv("PERSONALIZE_STRUCTURE_RATE_LIMIT", "5 per minute"))
def personalize_structure() -> tuple[Response, int]:
    """Step 2 — structure a free-form brief into fields via gpt-5-mini."""
    ctype = (request.content_type or "").split(";", 1)[0].strip().lower()
    if ctype != "application/json":
        return jsonify({"error": "content-type must be application/json"}), 415
    if (request.content_length or 0) > _PERSONALIZE_BRIEF_MAX_BYTES:
        return jsonify({"error": "payload too large"}), 413
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "invalid json body"}), 400
    raw_brief = body.get("brief")
    if not isinstance(raw_brief, str) or not raw_brief.strip():
        return jsonify({"error": "brief field required (non-empty string)"}), 400

    from personalize.openai_client import BudgetExceededError, OpenAIBrandClient

    try:
        client = OpenAIBrandClient(max_budget_usd=0.05)
        structured = client.structure_brief(raw_brief)
    except BudgetExceededError as exc:
        logger.warning("personalize_structure_budget", error=str(exc))
        return jsonify({"error": "budget exceeded"}), 429
    except Exception as exc:
        logger.error("personalize_structure_failed", error=str(exc))
        return jsonify({"error": "structure call failed"}), 502
    return jsonify(structured), 200


@app.route("/api/personalize/run", methods=["POST"])
@limiter.limit(os.getenv("PERSONALIZE_RUN_RATE_LIMIT", "2 per minute"))
def personalize_run() -> tuple[Response, int]:
    """Steps 4–8 — apply personalization to a captured site."""
    if (request.content_length or 0) > _PERSONALIZE_RUN_MAX_BYTES:
        return jsonify({"error": "payload too large"}), 413
    brief_raw = request.form.get("brief")
    html_dir_str = request.form.get("html_dir")
    logo_file = request.files.get("logo")
    if not (brief_raw and html_dir_str and logo_file):
        return jsonify({"error": "brief, html_dir, logo required"}), 400

    import json as _json

    try:
        brief = _json.loads(brief_raw)
    except _json.JSONDecodeError:
        return jsonify({"error": "brief must be JSON-encoded"}), 400
    if not isinstance(brief, dict):
        return jsonify({"error": "brief must be a JSON object"}), 400

    logo_bytes = logo_file.read(_PERSONALIZE_LOGO_MAX_BYTES + 1)
    if len(logo_bytes) > _PERSONALIZE_LOGO_MAX_BYTES:
        return jsonify({"error": "logo exceeds 2 MiB cap"}), 413

    # Confine html_dir to DOWNLOAD_FOLDER to prevent traversal.
    html_dir = os.path.realpath(os.path.join(DOWNLOAD_FOLDER, html_dir_str))
    base = os.path.realpath(DOWNLOAD_FOLDER)
    if not html_dir.startswith(base + os.sep) and html_dir != base:
        return jsonify({"error": "html_dir must be inside downloads/"}), 400

    from personalize.openai_client import BudgetExceededError
    from personalize.pipeline import run_pipeline

    try:
        out_path = run_pipeline(
            Path(html_dir),
            raw_brief="",  # not used when override provided
            logo_bytes=logo_bytes,
            structured_brief_override=brief,
        )
    except FileNotFoundError as exc:
        return jsonify({"error": f"missing input: {exc}"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except BudgetExceededError as exc:
        logger.warning("personalize_run_budget", error=str(exc))
        return jsonify({"error": "budget exceeded"}), 429
    except Exception as exc:
        logger.error("personalize_run_failed", error=str(exc))
        return jsonify({"error": "pipeline failed"}), 502

    return jsonify({"output_path": str(out_path) if out_path else None}), 200


if __name__ == "__main__":
    logger.info("app_starting", port=5001, debug=True)
    create_app()
    # Dev-only entry point. Production uses ``gunicorn wsgi:app`` (see wsgi.py
    # + Dockerfile + entrypoint.sh). The Werkzeug debugger from debug=True is
    # therefore never exposed to the network in prod.
    app.run(debug=True, port=5001, threaded=True)  # nosec B201

# NOTE: when imported (by tests, by `gunicorn app:app` legacy entry, or by `wsgi.py`),
# the module does NOT auto-call create_app(). This is the factory pattern fix for
# audit P2-7 — `import app` must be side-effect free. Production should use `wsgi.py`
# (`gunicorn wsgi:app`); the entrypoint.sh has been updated accordingly.
