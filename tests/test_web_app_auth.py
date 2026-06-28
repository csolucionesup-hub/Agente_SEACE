"""API key authentication tests for the web layer."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web_app import create_app


def _client(tmp_path, api_key):
    return TestClient(
        create_app(
            dashboard_path=tmp_path / "dashboard.json",
            settings_path=tmp_path / "settings.json",
            api_key=api_key,
        )
    )


def test_health_is_open_even_with_api_key(tmp_path):
    client = _client(tmp_path, "secret")
    assert client.get("/api/health").status_code == 200


def test_api_requires_key_when_configured(tmp_path):
    client = _client(tmp_path, "secret")
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/dashboard", headers={"X-API-Key": "secret"}).status_code == 200


def test_api_is_open_when_no_key_configured(tmp_path):
    client = _client(tmp_path, "")
    assert client.get("/api/dashboard").status_code == 200
