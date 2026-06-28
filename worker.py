"""Worker de fondo para LicitaScan (pensado para cron).

Precalcula la búsqueda de las keywords configuradas y refresca el seguimiento de los
OCID activos, dejando todo en caché de disco / dashboard JSON. Así el backend web solo
lee estado cacheado y nunca ejecuta el crawl pesado dentro de un request.

Uso típico (cron):
    python worker.py
    python worker.py --skip-tracking      # solo precalcular búsqueda
    python worker.py --skip-search        # solo refrescar seguimiento
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from seace_api import SeaceApiClient
from seace_seguimiento import sync_ocids
from seace_tracking import TrackingStore
from web_app import (
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_SEARCH_CACHE_PATH,
    DEFAULT_SETTINGS_PATH,
    DEFAULT_TRACKING_DB_PATH,
    _deep_search_opportunities,
    _write_disk_search_cache,
    load_settings,
)


def refresh_search_cache(
    client: Any,
    settings: dict[str, Any],
    cache_path: str | Path,
    max_pages: int = 20,
    paginate_by: int = 50,
    deadline_seconds: float | None = None,
) -> int:
    """Run the deep search for the configured keywords and persist it to the disk cache."""
    keywords = [str(item).strip() for item in settings.get("keywords") or [] if str(item).strip()]
    if not keywords:
        return 0
    cache_key = (tuple(sorted(keywords)), max_pages, paginate_by)
    opportunities, truncated = _deep_search_opportunities(
        client, keywords, max_pages=max_pages, paginate_by=paginate_by, deadline_seconds=deadline_seconds
    )
    _write_disk_search_cache(cache_path, cache_key, opportunities, truncated)
    return len(opportunities)


def refresh_tracking(client: Any, db_path: str | Path, dashboard_path: str | Path) -> tuple[int, int]:
    """Update the active OCIDs and regenerate the dashboard JSON the web app serves."""
    store = TrackingStore(db_path)
    store.initialize()
    active = store.list_active_ocids()
    events = sync_ocids(client, store, active, dashboard_path=dashboard_path)
    store.close()
    return len(active), len(events)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Worker de fondo LicitaScan (cron): precalcula búsqueda y refresca seguimiento."
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--search-cache", default=str(DEFAULT_SEARCH_CACHE_PATH))
    parser.add_argument("--db", default=str(DEFAULT_TRACKING_DB_PATH))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD_PATH))
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--paginate-by", type=int, default=50)
    parser.add_argument("--skip-search", action="store_true", help="No precalcular la búsqueda")
    parser.add_argument("--skip-tracking", action="store_true", help="No refrescar el seguimiento")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = SeaceApiClient()

    if not args.skip_search:
        settings = load_settings(args.settings)
        count = refresh_search_cache(
            client, settings, args.search_cache, max_pages=args.max_pages, paginate_by=args.paginate_by
        )
        print(f"Búsqueda precalculada: {count} oportunidades -> {args.search_cache}")

    if not args.skip_tracking:
        active, events = refresh_tracking(client, args.db, args.dashboard)
        print(f"Seguimiento: {active} OCID activos, {events} eventos nuevos -> {args.dashboard}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
