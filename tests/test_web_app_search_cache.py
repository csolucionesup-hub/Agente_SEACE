"""Tests for /api/search caching (TTL) and deadline-bounded deep search."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from seace_api import Opportunity
from web_app import create_app


def _opp(ocid: str) -> Opportunity:
    return Opportunity(
        keyword="PUENTE",
        ocid=ocid,
        tender_id="1",
        process_code=f"LP-{ocid}",
        entity_name="ENTIDAD",
        entity_id="20100000001",
        description="reparacion de puente",
        category="works",
        procurement_method="Licitacion Publica",
        amount=2_000_000,
        currency="PEN",
        date="2026-06-01T00:00:00-05:00",
        tender_start_date="2026-06-01T00:00:00-05:00",
        tender_end_date="2026-06-15T00:00:00-05:00",
        source="SEACE",
        api_url="https://example.test/record",
    )


class CountingClient:
    def __init__(self):
        self.calls = 0

    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50, year=None):
        self.calls += 1
        if page > 1:
            return []
        return [_opp("ocds-1"), _opp("ocds-2")]

    def get_record(self, ocid: str):
        return {}


class SlowEndlessClient:
    """Always returns a fresh non-empty page, so only the deadline can stop the crawl."""

    def __init__(self):
        self.calls = 0

    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50, year=None):
        self.calls += 1
        time.sleep(0.05)
        return [_opp(f"ocds-{keyword}-{page}")]

    def get_record(self, ocid: str):
        return {}


def _app(tmp_path, client, **kwargs):
    return create_app(
        dashboard_path=tmp_path / "dashboard.json",
        settings_path=tmp_path / "settings.json",
        seace_client=client,
        **kwargs,
    )


def test_second_identical_search_is_served_from_cache(tmp_path):
    fake = CountingClient()
    client = TestClient(_app(tmp_path, fake))

    first = client.get("/api/search", params={"keywords": "PUENTE", "max_pages": 2, "min_amount": 0})
    assert first.status_code == 200
    assert first.json()["from_cache"] is False
    calls_after_first = fake.calls
    assert calls_after_first > 0

    second = client.get("/api/search", params={"keywords": "PUENTE", "max_pages": 2, "min_amount": 0})
    assert second.json()["from_cache"] is True
    assert fake.calls == calls_after_first  # no extra upstream calls on a cache hit


def test_search_stops_at_deadline_and_flags_truncation(tmp_path):
    slow = SlowEndlessClient()
    client = TestClient(_app(tmp_path, slow, search_deadline=0.1, search_cache_ttl=0))

    response = client.get("/api/search", params={"keywords": "PUENTE", "max_pages": 50, "min_amount": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["search_truncated"] is True
    assert slow.calls < 50  # the crawl stopped early instead of hitting all 50 pages
