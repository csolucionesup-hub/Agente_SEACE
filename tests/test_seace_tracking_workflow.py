import json

from seace_tracking import TrackingStore, track_record_payload, export_dashboard_json
from tests.test_seace_tracking_snapshot import record_with_award_and_contract, record_with_tender_only


def test_track_record_payload_stores_snapshot_and_new_event(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()

    events = track_record_payload(store, record_with_tender_only())

    assert len(events) == 1
    assert events[0].event_type == "nueva_oportunidad"
    assert store.get_snapshot("ocds-test-tender").stage == "convocado"
    assert store.list_events("ocds-test-tender")[0].event_type == "nueva_oportunidad"


def test_track_record_payload_detects_transition_to_contract(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    payload = record_with_award_and_contract()
    original = payload["records"][0]["compiledRelease"]
    tender_only = {"records": [{"compiledRelease": {**original, "awards": [], "contracts": []}}]}
    track_record_payload(store, tender_only)

    events = track_record_payload(store, payload)

    event_types = [event.event_type for event in events]
    assert "contrato_suscrito" in event_types
    assert store.get_snapshot("ocds-test-award").outcome == "contratado"


def test_export_dashboard_json_groups_counts_and_recent_events(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    track_record_payload(store, record_with_tender_only())
    track_record_payload(store, record_with_award_and_contract())
    out = tmp_path / "dashboard.json"

    export_dashboard_json(store, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["counts_by_stage"]["convocado"] == 1
    assert data["counts_by_stage"]["contrato_suscrito"] == 1
    assert data["opportunities"][0]["ocid"]
    assert "raw_json" not in data["opportunities"][0]
    assert "commercial_score" in data["opportunities"][0]
    assert data["opportunities"][0]["priority_label"] in {"Alta", "Media", "Baja"}
    assert data["opportunities"][0]["recommended_action"]
    tender_opportunity = next(item for item in data["opportunities"] if item["ocid"] == "ocds-test-tender")
    assert tender_opportunity["official_documents"][0]["title"] == "Bases Administrativas"
    assert tender_opportunity["official_documents"][0]["download_url"].startswith("https://")
    assert data["recent_events"][0]["event_type"] == "nueva_oportunidad"
    assert "payload_json" not in data["recent_events"][0]
    assert "raw_json" not in data["recent_events"][0]["payload"]
