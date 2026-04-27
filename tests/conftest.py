"""Shared pytest fixtures.

Critical pattern: app is imported with NO side effects (factory pattern, audit P2-7).
Each test gets a fresh client + clean in-memory state."""

from __future__ import annotations
import pytest


@pytest.fixture
def flask_app():
    """Side-effect-free Flask app instance. No janitor, no boot cleanup."""
    import app as app_module

    app_module.create_app(start_janitor=False, run_boot_cleanup=False)
    app_module._reset_state()
    yield app_module.app
    app_module._reset_state()


@pytest.fixture
def client(flask_app):
    """Flask test client backed by the side-effect-free app fixture."""
    return flask_app.test_client()
