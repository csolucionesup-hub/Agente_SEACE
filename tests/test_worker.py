"""Tests for the background worker: precompute search cache + warm the web app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from seace_api import Opportunity
from web_app import create_app, load_settings, save_settings
from worker import refresh_search_cache, refresh_tracking


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

    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50):
        self.calls += 1
        if page > 1:
            return []
        return [_opp("ocds-1"), _opp("ocds-2")]

    def get_record(self, ocid: str):
        return {}


def test_opportunity_from_row_roundtrip():
    opportunity = _opp("ocds-x")
    assert Opportunity.from_row(opportunity.to_row()) == opportunity


def test_worker_warms_disk_cache_that_web_reads_without_upstream_calls(tmp_path):
    fake = CountingClient()
    cache_path = tmp_path / "search-cache.json"
    settings_path = tmp_path / "settings.json"
    save_settings({"keywords": ["PUENTE"], "min_amount": 0}, settings_path)

    produced = refresh_search_cache(
        fake, load_settings(settings_path), cache_path, max_pages=20, paginate_by=50
    )
    assert produced == 2
    calls_after_worker = fake.calls
    assert calls_after_worker > 0

    app = create_app(
        dashboard_path=tmp_path / "dashboard.json",
        settings_path=settings_path,
        seace_client=fake,
        search_cache_path=cache_path,
        search_cache_ttl=600,
    )
    client = TestClient(app)
    response = client.get("/api/search")  # usa las keywords de settings -> mismo cache_key del worker
    assert response.status_code == 200
    body = response.json()
    assert body["from_cache"] is True
    assert fake.calls == calls_after_worker  # servido desde disco, sin llamadas extra al upstream


def test_refresh_tracking_with_no_active_ocids(tmp_path):
    active, events = refresh_tracking(CountingClient(), tmp_path / "t.sqlite3", tmp_path / "dash.json")
    assert active == 0
    assert events == []
