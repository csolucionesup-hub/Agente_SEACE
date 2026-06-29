"""Tests for the background worker: precompute search cache + warm the web app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from seace_api import Opportunity
from seace_tracking import Subscriber, TrackingStore
from web_app import create_app, load_settings, save_settings
from worker import _merge_keywords, active_subscriber_keywords, refresh_search_cache, refresh_tracking


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
    assert len(produced) == 2  # devuelve las oportunidades (para sembrar el tracking)
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


def test_merge_keywords_dedups_case_insensitive_preserving_order():
    assert _merge_keywords(["PUENTE", "Carretera"], ["carretera", "PILOTE"]) == ["PUENTE", "Carretera", "PILOTE"]
    assert _merge_keywords(None, None) == []


def test_active_subscriber_keywords_only_active(tmp_path):
    db = tmp_path / "t.sqlite3"
    store = TrackingStore(db)
    store.initialize()
    store.upsert_subscriber(Subscriber(name="a", telegram_chat_id="1", keywords=["PUENTE"], negative_keywords=[], active=True))
    store.upsert_subscriber(Subscriber(name="b", telegram_chat_id="2", keywords=["MUELLE"], negative_keywords=[], active=False))
    store.close()

    assert active_subscriber_keywords(db) == ["PUENTE"]


class RecordingClient:
    def __init__(self):
        self.searched = []

    def search_opportunities(self, keyword, page=1, paginate_by=50):
        self.searched.append(keyword)
        if page > 1:
            return []
        return [_opp(f"ocds-{keyword}")]

    def get_record(self, ocid):
        return {}


def test_refresh_search_cache_unions_extra_keywords(tmp_path):
    client = RecordingClient()
    opps = refresh_search_cache(
        client, {"keywords": ["PUENTE"]}, tmp_path / "c.json", extra_keywords=["PILOTE", "puente"]
    )
    # unión sin duplicar (case-insensitive): PUENTE + PILOTE, no dos veces puente
    assert set(client.searched) == {"PUENTE", "PILOTE"}
    assert len(opps) == 2


class SeedClient:
    def __init__(self):
        self.fetched = []

    def search_opportunities(self, keyword, page=1, paginate_by=50):
        return []

    def get_record(self, ocid):
        self.fetched.append(ocid)
        return {"compiledRelease": {"ocid": ocid, "tender": {"title": f"LP-{ocid}", "description": "puente", "status": "active"}}}


def test_refresh_tracking_seeds_new_ocids(tmp_path):
    db = tmp_path / "t.sqlite3"
    client = SeedClient()

    tracked, events = refresh_tracking(client, db, tmp_path / "d.json", seed_ocids=["ocds-new-1", "ocds-new-2"])

    assert tracked == 2
    assert client.fetched == ["ocds-new-1", "ocds-new-2"]
    assert {e.event_type for e in events} == {"nueva_oportunidad"}

    store = TrackingStore(db)
    store.initialize()
    assert store.get_snapshot("ocds-new-1") is not None
    assert store.list_active_ocids() == ["ocds-new-1", "ocds-new-2"]
    store.close()
