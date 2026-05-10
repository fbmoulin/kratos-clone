"""Shared structlog configuration.

Both the Flask UI (`app.py`) and the CLI (`python -m kratos_clone`) need
the same renderer + log-level setup so that ``LOG_FORMAT=json`` /
``LOG_LEVEL=...`` env vars behave identically across entry points.

Importing this module is side-effect-free; call ``configure_logging()``
once from each entry point before any logger is used.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging() -> None:
    """Configure structlog renderer + log-level filtering.

    Reads ``LOG_FORMAT`` (``"console"`` default, ``"json"`` for prod) and
    ``LOG_LEVEL`` (``"INFO"`` default). Idempotent; calling twice is a no-op
    beyond reapplying the current env-var state.
    """
    log_format = os.getenv("LOG_FORMAT", "console").lower()
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
    ]
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
