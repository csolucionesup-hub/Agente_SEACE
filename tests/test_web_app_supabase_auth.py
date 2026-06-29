"""Tests del gate de auth con Supabase (login con Google) en la capa web."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web_app import create_app


def _fake_verify(token):
    return {"id": "u1", "email": "ana@example.com"} if token == "good" else None


def _client(tmp_path, **kwargs):
    return TestClient(
        create_app(dashboard_path=tmp_path / "d.json", settings_path=tmp_path / "s.json", **kwargs)
    )


def _supa_client(tmp_path, **kwargs):
    return _client(
        tmp_path,
        supabase_url="https://x.supabase.co",
        supabase_anon_key="anon",
        supabase_verify=_fake_verify,
        **kwargs,
    )


def test_config_reports_auth_enabled(tmp_path):
    body = _supa_client(tmp_path).get("/api/config").json()
    assert body["auth_enabled"] is True
    assert body["supabase_url"] == "https://x.supabase.co"
    assert body["supabase_anon_key"] == "anon"


def test_config_open_and_disabled_without_supabase(tmp_path):
    client = _client(tmp_path)
    body = client.get("/api/config").json()
    assert body["auth_enabled"] is False
    # sin auth configurada, las rutas siguen abiertas
    assert client.get("/api/dashboard").status_code == 200


def test_protected_requires_valid_bearer(tmp_path):
    client = _supa_client(tmp_path)
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer good"}).status_code == 200


def test_me_returns_current_user(tmp_path):
    client = _supa_client(tmp_path)
    response = client.get("/api/me", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ana@example.com"


def test_api_key_fallback_works_alongside_supabase(tmp_path):
    client = _supa_client(tmp_path, api_key="secret")
    assert client.get("/api/dashboard", headers={"Authorization": "Bearer good"}).status_code == 200
    assert client.get("/api/dashboard", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/api/dashboard").status_code == 401
