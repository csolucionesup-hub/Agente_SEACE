"""Tests for the httpx-based JSON HTTP client (timeouts + bounded retries)."""

from __future__ import annotations

import httpx
import pytest

from seace_api import HttpxJsonHttpClient


def test_get_json_sends_params_and_parses_response():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"results": [1, 2]})

    client = HttpxJsonHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    data = client.get_json("https://example.test/api/v1/search", params={"q": "PUENTE", "page": 1})

    assert data == {"results": [1, 2]}
    assert "q=PUENTE" in captured["url"]
    assert "page=1" in captured["url"]


def test_retries_on_transport_error_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": True})

    client = HttpxJsonHttpClient(
        retries=2, backoff=0.0, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    assert client.get_json("https://example.test/x") == {"ok": True}
    assert calls["n"] == 2


def test_does_not_retry_on_4xx():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"error": "nope"})

    client = HttpxJsonHttpClient(
        retries=3, backoff=0.0, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.get_json("https://example.test/x")
    assert calls["n"] == 1
