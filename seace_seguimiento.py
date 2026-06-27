"""CLI para seguimiento diario de oportunidades SEACE por OCID."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Protocol

from seace_api import SeaceApiClient
from seace_tracking import TrackingEvent, TrackingStore, export_dashboard_json, track_record_payload


class RecordClient(Protocol):
    def get_record(self, ocid: str) -> dict:
        ...


def sync_ocids(
    client: RecordClient,
    store: TrackingStore,
    ocids: Iterable[str],
    dashboard_path: str | Path | None = None,
) -> list[TrackingEvent]:
    all_events: list[TrackingEvent] = []
    for ocid in ocids:
        clean_ocid = ocid.strip()
        if not clean_ocid:
            continue
        payload = client.get_record(clean_ocid)
        all_events.extend(track_record_payload(store, payload))

    if dashboard_path:
        export_dashboard_json(store, dashboard_path)
    return all_events


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Actualizar seguimiento de oportunidades SEACE por OCID.")
    parser.add_argument("--db", default="data/seace_tracking.sqlite3", help="Ruta SQLite de seguimiento")
    parser.add_argument("--dashboard", default="reportes/dashboard-seguimiento.json", help="Ruta JSON para Lovable/dashboard")
    parser.add_argument("--ocids", default="", help="OCID separados por coma para actualizar")
    parser.add_argument("--active", action="store_true", help="Actualizar OCID activos guardados en la base")
    return parser


def _parse_ocids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    args = build_parser().parse_args()
    store = TrackingStore(args.db)
    store.initialize()
    client = SeaceApiClient()

    ocids = _parse_ocids(args.ocids)
    if args.active:
        ocids.extend([ocid for ocid in store.list_active_ocids() if ocid not in ocids])

    if not ocids:
        export_dashboard_json(store, args.dashboard)
        print("No hay OCID para actualizar. Dashboard generado con datos existentes.")
        print(f"Dashboard: {args.dashboard}")
        return 0

    events = sync_ocids(client, store, ocids, dashboard_path=args.dashboard)
    print(f"OCID actualizados: {len(ocids)}")
    print(f"Eventos nuevos: {len(events)}")
    print(f"Dashboard: {args.dashboard}")
    for event in events:
        print(f"- [{event.severity}] {event.title}: {event.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
