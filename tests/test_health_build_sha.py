"""`/health` must identify WHICH build is answering, not just that something is.

A 200 from `/health` proves a process is alive. It does not prove the process is
running the commit you think you deployed — an image can be rebuilt under the same
tag, a `docker compose up -d` can decline to re-pull, and a deploy can silently no-op.
Every one of those leaves `/health` returning 200 from stale code.

`build_sha` closes that gap, but only if it is ALWAYS present. An omitted or empty
field is indistinguishable from an old build that predates this endpoint change, so
the resolver reports the literal string `unknown` instead — a value an operator can
see and act on.
"""

from __future__ import annotations

import pytest

import app as app_module

# Every environment variable the resolver consults, in priority order. Each is
# justified by a deploy target committed to this repo: KC_BUILD_SHA by Dockerfile,
# RENDER_GIT_COMMIT by render.yaml, RAILWAY_GIT_COMMIT_SHA by RAILWAY_DEPLOY.md.
SHA_ENV_VARS = ("KC_BUILD_SHA", "RENDER_GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA")


@pytest.fixture
def no_sha_env(monkeypatch):
    """Clear every source, so a test sets exactly the one it means to test."""
    for var in SHA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_health_always_reports_a_build_sha(client, no_sha_env):
    """The field is never absent — absence is what made a 200 unprovable."""
    body = client.get("/health").get_json()
    assert "build_sha" in body


def test_unresolvable_sha_is_the_literal_string_unknown(client, no_sha_env):
    """Not omitted, not None, not empty: a value the operator can read and act on."""
    body = client.get("/health").get_json()
    assert body["build_sha"] == "unknown"


def test_explicit_build_sha_wins_over_platform_variables(client, no_sha_env):
    """KC_BUILD_SHA is what our own Dockerfile injects, so it outranks the platform."""
    no_sha_env.setenv("KC_BUILD_SHA", "aaaaaaa")
    no_sha_env.setenv("RENDER_GIT_COMMIT", "bbbbbbb")
    no_sha_env.setenv("RAILWAY_GIT_COMMIT_SHA", "ccccccc")
    assert client.get("/health").get_json()["build_sha"] == "aaaaaaa"


@pytest.mark.parametrize(
    ("var", "value"),
    [("RENDER_GIT_COMMIT", "deadbee"), ("RAILWAY_GIT_COMMIT_SHA", "cafebab")],
)
def test_platform_variables_are_read_when_no_explicit_sha_is_set(
    client, no_sha_env, var, value
):
    no_sha_env.setenv(var, value)
    assert client.get("/health").get_json()["build_sha"] == value


def test_render_outranks_railway(client, no_sha_env):
    """Both set at once must resolve deterministically, not by dict ordering luck."""
    no_sha_env.setenv("RENDER_GIT_COMMIT", "rrrrrrr")
    no_sha_env.setenv("RAILWAY_GIT_COMMIT_SHA", "yyyyyyy")
    assert client.get("/health").get_json()["build_sha"] == "rrrrrrr"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_value_is_treated_as_unset_not_as_an_answer(client, no_sha_env, blank):
    """A build arg declared but never passed arrives as an empty string.

    Reporting that verbatim would put `"build_sha": ""` in the response, which reads
    as a resolved answer and is not one. It must fall through to the next source.
    """
    no_sha_env.setenv("KC_BUILD_SHA", blank)
    no_sha_env.setenv("RENDER_GIT_COMMIT", "fallback")
    assert client.get("/health").get_json()["build_sha"] == "fallback"


def test_surrounding_whitespace_is_stripped(client, no_sha_env):
    """`$(git rev-parse HEAD)` in a Dockerfile ARG commonly carries a trailing newline."""
    no_sha_env.setenv("KC_BUILD_SHA", "  1bd1aa8\n")
    assert client.get("/health").get_json()["build_sha"] == "1bd1aa8"


def test_resolver_is_read_at_request_time_not_import_time(client, no_sha_env):
    """The value must track the environment the process is actually running under.

    Caching it at import would make the field describe the build that imported the
    module — which is exactly the class of stale-label bug this endpoint exists to
    detect.
    """
    no_sha_env.setenv("KC_BUILD_SHA", "first")
    assert client.get("/health").get_json()["build_sha"] == "first"
    no_sha_env.setenv("KC_BUILD_SHA", "second")
    assert client.get("/health").get_json()["build_sha"] == "second"


def test_existing_health_fields_are_untouched(client, no_sha_env):
    """Adding a field must not disturb what monitoring already reads."""
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    assert "sessions" in body
    assert "queues" in body


def test_resolver_is_importable_and_reusable(no_sha_env):
    """Exposed as a function so deploy scripts can assert against it directly."""
    no_sha_env.setenv("KC_BUILD_SHA", "xyz1234")
    assert app_module._resolve_build_sha() == "xyz1234"
