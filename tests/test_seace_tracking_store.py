import json

from seace_tracking import TrackingStore, OpportunitySnapshot, TrackingEvent


def sample_snapshot(ocid="ocds-test-1", status="active"):
    return OpportunitySnapshot(
        ocid=ocid,
        process_code="LP-1-2026-MTC-1",
        entity_name="MTC",
        description="Construcción de puente",
        amount=1000000.0,
        currency="PEN",
        tender_status=status,
        stage="convocado",
        next_critical_date="2026-06-20T00:00:00-05:00",
        winner_name="",
        winner_ruc="",
        awarded_amount=None,
        award_date="",
        contract_id="",
        contract_date_signed="",
        contract_start_date="",
        contract_end_date="",
        outcome="activo",
        raw={"hello": "world"},
    )


def test_store_initializes_sqlite_tables(tmp_path):
    db_path = tmp_path / "tracking.sqlite3"

    store = TrackingStore(db_path)
    store.initialize()

    tables = store.connection.execute(
        "select name from sqlite_master where type='table' order by name"
    ).fetchall()
    table_names = [row[0] for row in tables]
    assert "opportunities" in table_names
    assert "opportunity_events" in table_names


def test_upsert_snapshot_persists_latest_state(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()

    snapshot = sample_snapshot()
    store.upsert_snapshot(snapshot)

    saved = store.get_snapshot("ocds-test-1")
    assert saved == snapshot


def test_add_event_and_list_timeline(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    store.upsert_snapshot(sample_snapshot())

    event = TrackingEvent(
        ocid="ocds-test-1",
        event_type="buena_pro_otorgada",
        title="Buena pro otorgada",
        message="Ganó Empresa X por S/ 900000",
        severity="high",
        occurred_at="2026-06-10T10:00:00-05:00",
        payload={"winner_name": "Empresa X"},
    )
    store.add_event(event)

    timeline = store.list_events("ocds-test-1")
    assert timeline == [event]


def test_list_active_ocids_excludes_terminal_outcomes(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    store.upsert_snapshot(sample_snapshot("active-1", status="active"))
    store.upsert_snapshot(sample_snapshot("contracted-1", status="complete"))
    store.upsert_snapshot(sample_snapshot("cancelled-1", status="cancelled"))

    assert store.list_active_ocids() == ["active-1"]
