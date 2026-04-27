from flask import Flask, render_template, request, send_file, Response, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import os
import re
import shutil
import sys
import uuid
import queue
import threading
import time
import gc
import structlog
from downloader import WebsiteDownloader, zip_directory, get_site_name


# ── Structured logging setup ────────────────────────────────────────────────
# JSON output in production (when LOG_FORMAT=json), pretty console otherwise.
_log_format = os.getenv("LOG_FORMAT", "console").lower()
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=_log_level,
)

_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.format_exc_info,
]
if _log_format == "json":
    _processors.append(structlog.processors.JSONRenderer())
else:
    _processors.append(structlog.dev.ConsoleRenderer(colors=True))

structlog.configure(
    processors=_processors,
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("app")

app = Flask(__name__)
# Hard 1 MiB body cap on every endpoint — backstop for the per-route check
# in /api/client-errors which can be bypassed via Transfer-Encoding: chunked.
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024

# Trust X-Forwarded-For only when explicitly enabled — security review caught
# that without ProxyFix, every external client appears to share the proxy IP
# (e.g. 127.0.0.1 behind nginx) and the rate limiter applies a single global
# bucket. Set TRUST_PROXY=1 only when behind a known reverse proxy that strips
# client-supplied X-Forwarded-For (otherwise spoofable).
if os.getenv("TRUST_PROXY", "0").strip() == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    logger.info("proxy_fix_enabled", x_for=1, x_proto=1)

# P2-5: rate-limit /api/client-errors. Default in-memory storage is fine for
# single-worker gunicorn (our entrypoint.sh uses --workers 1); for multi-worker
# deployments wire RATE_LIMIT_STORAGE_URI to redis://...
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
    # Disabled in tests via app.config["RATELIMIT_ENABLED"] = False to keep
    # parametrized tests fast.
    enabled=True,
)
limiter.init_app(app)

DOWNLOAD_FOLDER = "downloads"

# Tunable retention windows (seconds)
COMPLETE_TTL = 1800  # complete sessions (zip waiting for download)
ERROR_TTL = 600  # error sessions
PROCESSING_TTL = 1800  # safety net for stuck/zombie sessions
ORPHAN_FILE_TTL = 1800  # files on disk with no matching session
CLEANUP_INTERVAL = 300  # how often the janitor runs

# Per-session state. Always touch via session_lock when iterating/mutating.
# Module-level so routes (registered via @app.route below) can close over them;
# cleared/reset by tests via _reset_state().
message_queues = {}
download_results = {}
session_lock = threading.Lock()


def _reset_state():
    """Test helper — wipe in-memory session state without touching disk."""
    with session_lock:
        message_queues.clear()
        download_results.clear()


def cleanup_downloads_folder():
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
        logger.warning(
            "downloads_folder_clear_failed", folder=DOWNLOAD_FOLDER, error=str(e)
        )


def _purge_session(session_id):
    """Remove a single session's in-memory state and any disk artifacts."""
    with session_lock:
        result = download_results.pop(session_id, None)
        message_queues.pop(session_id, None)

    if not result:
        return

    zip_path = result.get("zip_path")
    if zip_path and os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass

    # Some error paths may leave the raw directory behind.
    raw_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    if os.path.isdir(raw_dir):
        try:
            shutil.rmtree(raw_dir)
        except Exception:
            pass


def _cleanup_orphan_files():
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


def cleanup_abandoned_sessions():
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


def create_app(start_janitor: bool = True, run_boot_cleanup: bool = True):
    """Initialize side-effecting parts of the app: ensure DOWNLOAD_FOLDER exists,
    optionally clear stale downloads on boot, and optionally start the janitor
    thread. Returns the module-level `app` for chaining.

    Tests call `create_app(start_janitor=False, run_boot_cleanup=False)` to get
    a fresh, side-effect-free Flask instance. Production uses `wsgi.py` which
    calls `create_app()` with defaults.

    Idempotent re: the Flask `app` object (always the same instance); NOT
    idempotent re: spawning janitor threads — calling twice will start two.
    """
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    if run_boot_cleanup:
        cleanup_downloads_folder()
    if start_janitor:
        threading.Thread(target=cleanup_abandoned_sessions, daemon=True).start()
        logger.info("janitor_started", interval_s=CLEANUP_INTERVAL)
    return app


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Lightweight health endpoint with memory + session counts for monitoring."""
    info = {"status": "ok"}
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
def start_download():
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


def process_download(session_id, url):
    """Background download worker."""
    with session_lock:
        q = message_queues.get(session_id)
    if q is None:
        return

    download_dir = os.path.join(DOWNLOAD_FOLDER, session_id)
    zip_path = os.path.join(DOWNLOAD_FOLDER, f"{session_id}.zip")

    def log_callback(message):
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
            try:
                os.remove(zip_path)
            except Exception:
                pass

    finally:
        # Drop downloader reference so its in-memory buffers can be GC'd
        downloader = None
        gc.collect()


@app.route("/stream/<session_id>")
def stream(session_id):
    """SSE endpoint for log streaming."""

    def generate():
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
def download_file(session_id):
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

        def cleanup():
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


def _truncate(value, limit=_FRONTEND_MAX_FIELD_LEN):
    if value is None:
        return None
    s = _CONTROL_CHARS_RE.sub("?", str(value))
    return s if len(s) <= limit else s[:limit] + "…"


def _strip_query(url):
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
def client_errors():
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


if __name__ == "__main__":
    logger.info("app_starting", port=5001, debug=True)
    create_app()
    app.run(debug=True, port=5001, threaded=True)

# NOTE: when imported (by tests, by `gunicorn app:app` legacy entry, or by `wsgi.py`),
# the module does NOT auto-call create_app(). This is the factory pattern fix for
# audit P2-7 — `import app` must be side-effect free. Production should use `wsgi.py`
# (`gunicorn wsgi:app`); the entrypoint.sh has been updated accordingly.
