from seace_seguimiento import sync_ocids
from seace_tracking import TrackingStore
from tests.test_seace_tracking_snapshot import record_with_award_and_contract, record_with_tender_only


class FakeClient:
    def __init__(self):
        self.calls = []
        self.payloads = {
            "ocds-test-tender": record_with_tender_only(),
            "ocds-test-award": record_with_award_and_contract(),
        }

    def get_record(self, ocid):
        self.calls.append(ocid)
        return self.payloads[ocid]


def test_sync_ocids_fetches_records_tracks_events_and_exports_dashboard(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    out = tmp_path / "dashboard.json"
    client = FakeClient()

    events = sync_ocids(client, store, ["ocds-test-tender", "ocds-test-award"], dashboard_path=out)

    assert client.calls == ["ocds-test-tender", "ocds-test-award"]
    assert [event.event_type for event in events] == ["nueva_oportunidad", "nueva_oportunidad"]
    assert out.exists()
    assert store.get_snapshot("ocds-test-award").outcome == "contratado"
