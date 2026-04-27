"""Tests for scripts.probe — Stage 1 site reconnaissance."""

from __future__ import annotations

from unittest.mock import MagicMock


from scripts.probe import detect_framework, summarize_csp, ProbeResult, run_probe


def _mock_response(
    *, status: int, headers: dict | None = None, text: str = ""
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.headers = headers or {}
    resp.text = text
    return resp


class TestDetectFramework:
    def test_next_via_data_marker(self):
        html = '<html><body><script id="__NEXT_DATA__">{}</script></body></html>'
        assert detect_framework(html, {}) == "next"

    def test_react_via_react_root(self):
        html = '<div id="root"></div><script src="react.production.min.js"></script>'
        assert detect_framework(html, {}) == "react"

    def test_vue_via_app_marker(self):
        html = '<div id="app"></div><script src="vue.runtime.esm-browser.prod.js"></script>'
        assert detect_framework(html, {}) == "vue"

    def test_svelte_via_compiled_marker(self):
        html = "<script>/* compiled by SvelteKit */</script>"
        assert detect_framework(html, {}) == "svelte"

    def test_via_x_powered_by_header(self):
        assert detect_framework("<html></html>", {"x-powered-by": "Next.js"}) == "next"

    def test_unknown_returns_unknown(self):
        assert detect_framework("<html><body>plain</body></html>", {}) == "unknown"


class TestSummarizeCSP:
    def test_returns_dict_when_present(self):
        csp = "default-src 'self'; img-src 'self' data:; script-src 'unsafe-inline'"
        out = summarize_csp({"content-security-policy": csp})
        assert "default-src" in out
        assert out["script-src"] == ["'unsafe-inline'"]

    def test_empty_when_absent(self):
        assert summarize_csp({}) == {}

    def test_strips_whitespace(self):
        out = summarize_csp({"content-security-policy": "  default-src   'self' ; "})
        assert out["default-src"] == ["'self'"]


class TestRunProbe:
    def test_success_path(self, monkeypatch):
        head = _mock_response(
            status=200,
            headers={
                "x-powered-by": "Next.js",
                "content-security-policy": "default-src 'self'",
            },
        )
        get = _mock_response(
            status=200,
            headers={},
            text='<html><body><script id="__NEXT_DATA__">{}</script></body></html>',
        )
        sess = MagicMock()
        sess.head.return_value = head
        sess.get.return_value = get
        result = run_probe("https://example.com", session=sess)
        assert isinstance(result, ProbeResult)
        assert result.url == "https://example.com"
        assert result.status == 200
        assert result.framework == "next"
        assert "default-src" in result.csp
        assert result.reachable is True

    def test_4xx_marks_unreachable_but_records_status(self, monkeypatch):
        head = _mock_response(status=403, headers={})
        sess = MagicMock()
        sess.head.return_value = head
        result = run_probe("https://blocked.example", session=sess)
        assert result.status == 403
        assert result.reachable is False
        assert result.framework == "unknown"

    def test_network_error_records_error(self):
        sess = MagicMock()
        sess.head.side_effect = ConnectionError("dns timeout")
        result = run_probe("https://nope.invalid", session=sess)
        assert result.status is None
        assert result.reachable is False
        assert "ConnectionError" in (result.error or "")
