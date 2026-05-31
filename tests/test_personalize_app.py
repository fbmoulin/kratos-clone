"""Tests for the Flask routes added in Phase 4."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _png_bytes() -> bytes:
    img = Image.new("RGB", (16, 16), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def captured_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a downloads/<id>/ layout with an inventory + index.html."""
    downloads = tmp_path / "downloads"
    site_dir = downloads / "site-A"
    site_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_DIR / "sample_captured.html", site_dir / "index.html")
    shutil.copy(FIXTURE_DIR / "sample_inventory.json", site_dir / "_inventory.json")
    monkeypatch.chdir(tmp_path)
    return site_dir


def test_personalize_page_renders(client):
    resp = client.get("/personalize")
    assert resp.status_code == 200
    assert b"Personalizar site" in resp.data
    assert b"/api/personalize/structure" in resp.data
    assert b"/api/personalize/run" in resp.data


def test_structure_requires_json_content_type(client):
    resp = client.post(
        "/api/personalize/structure",
        data="brief=hi",
        content_type="application/x-www-form-urlencoded",
    )
    assert resp.status_code == 415


def test_structure_requires_brief_field(client):
    resp = client.post(
        "/api/personalize/structure",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_structure_oversized_payload_413(client):
    big = "x" * (5 * 1024)
    resp = client.post(
        "/api/personalize/structure",
        data=json.dumps({"brief": big}),
        content_type="application/json",
    )
    assert resp.status_code == 413


def test_structure_happy_path(client):
    fake_structured = {
        "company": "Acme",
        "tagline": "Move fast",
        "audience": "indie devs",
        "category": "developer tools",
        "tone": ["friendly", "direct"],
    }
    with patch("personalize.openai_client.OpenAIBrandClient") as Mocked:
        instance = Mocked.return_value
        instance.structure_brief.return_value = fake_structured
        resp = client.post(
            "/api/personalize/structure",
            data=json.dumps({"brief": "We make tools for indie devs."}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    assert resp.get_json() == fake_structured


def test_run_requires_logo_and_brief(client):
    resp = client.post(
        "/api/personalize/run",
        data={"brief": "{}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_run_rejects_html_dir_outside_downloads(client, captured_dir):
    resp = client.post(
        "/api/personalize/run",
        data={
            "brief": json.dumps(
                {
                    "company": "Acme",
                    "tagline": "x",
                    "audience": "y",
                    "category": "z",
                    "tone": ["a", "b"],
                }
            ),
            "html_dir": "../etc",
            "logo": (io.BytesIO(_png_bytes()), "logo.png"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_run_happy_path(client, captured_dir, tmp_path):
    fake_plan = {
        "palette": {
            "primary": "#3b82f6",
            "primary_hover": "#60a5fa",
            "primary_pressed": "#2563eb",
            "accent_evidence": "blue",
        },
        "patches": [{"slot_id": "hero.headline", "value": "Brand New"}],
        "images": [],
    }
    with patch("personalize.pipeline.OpenAIBrandClient") as Mocked:
        instance = Mocked.return_value
        instance.structure_brief.return_value = {
            "company": "Acme",
            "tagline": "Move fast",
            "audience": "indie devs",
            "category": "developer tools",
            "tone": ["friendly", "direct"],
        }
        instance.personalize.return_value = fake_plan

        # generate_images_parallel is async — return an awaitable that yields {}
        async def _no_images(*_a, **_kw):
            return {}

        instance.generate_images_parallel = _no_images
        instance.spent_usd = 0.1
        instance.remaining_usd = 0.9

        resp = client.post(
            "/api/personalize/run",
            data={
                "brief": json.dumps(
                    {
                        "company": "Acme",
                        "tagline": "Move fast",
                        "audience": "indie devs",
                        "category": "developer tools",
                        "tone": ["friendly", "direct"],
                    }
                ),
                "html_dir": "site-A",
                "logo": (io.BytesIO(_png_bytes()), "logo.png"),
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["output_path"] is not None
    assert body["output_path"].endswith("personalized.html")
    assert (captured_dir / "personalized.html").exists()


def _run_form(html_dir: str = "site-A") -> dict:
    """Multipart form body for /api/personalize/run with a valid brief + logo."""
    return {
        "brief": json.dumps(
            {
                "company": "Acme",
                "tagline": "Move fast",
                "audience": "indie devs",
                "category": "developer tools",
                "tone": ["friendly", "direct"],
            }
        ),
        "html_dir": html_dir,
        "logo": (io.BytesIO(_png_bytes()), "logo.png"),
    }


def test_run_success_json_includes_html_dir(client, captured_dir):
    """Change C: the success response echoes the submitted html_dir form field."""
    with patch("personalize.pipeline.run_pipeline") as mock_run:
        mock_run.return_value = captured_dir / "personalized.html"
        resp = client.post(
            "/api/personalize/run",
            data=_run_form("site-A"),
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert resp.get_json()["html_dir"] == "site-A"


def test_run_success_clears_stale_preview_screenshots(client, captured_dir):
    """R2-PRC006: a successful re-personalize clears stale preview-*.png so a
    previous run's screenshot is never served as if current."""
    before = captured_dir / "preview-before.png"
    after = captured_dir / "preview-after.png"
    before.write_bytes(_png_bytes())
    after.write_bytes(_png_bytes())

    with patch("personalize.pipeline.run_pipeline") as mock_run:
        mock_run.return_value = captured_dir / "personalized.html"
        resp = client.post(
            "/api/personalize/run",
            data=_run_form("site-A"),
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert not before.exists()
    assert not after.exists()


def test_run_failure_does_not_clear_preview_screenshots(client, captured_dir):
    """R2-PRC006: on pipeline failure the cache clear must NOT run, so a prior
    run's screenshot survives rather than being silently dropped on a failed run."""
    after = captured_dir / "preview-after.png"
    after.write_bytes(_png_bytes())

    with patch("personalize.pipeline.run_pipeline") as mock_run:
        mock_run.side_effect = RuntimeError("boom")
        resp = client.post(
            "/api/personalize/run",
            data=_run_form("site-A"),
            content_type="multipart/form-data",
        )
    assert resp.status_code == 502
    assert after.exists()  # cache clear did NOT run on the failure path
