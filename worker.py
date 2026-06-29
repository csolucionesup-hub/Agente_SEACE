"""Worker de fondo para LicitaScan (pensado para cron o modo --serve).

Precalcula la búsqueda de las keywords configuradas y refresca el seguimiento de los
OCID activos, dejando todo en caché de disco / dashboard JSON. Así el backend web solo
lee estado cacheado y nunca ejecuta el crawl pesado dentro de un request.

Además despacha alertas vía Telegram y/o webhook cuando detecta eventos nuevos.

Uso típico:
    python worker.py                  # una sola ejecución (para cron)
    python worker.py --serve          # loop continuo con APScheduler
    python worker.py --skip-tracking  # solo precalcular búsqueda
    python worker.py --skip-search    # solo refrescar seguimiento
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

from seace_api import SeaceApiClient
from seace_seguimiento import sync_ocids
from seace_tracking import TrackingStore
from reparto import repartir_sync
from web_app import (
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_SEARCH_CACHE_PATH,
    DEFAULT_SETTINGS_PATH,
    DEFAULT_TRACKING_DB_PATH,
    _deep_search_opportunities,
    _write_disk_search_cache,
    load_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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


def refresh_tracking(
    client: Any,
    db_path: str | Path,
    dashboard_path: str | Path,
) -> tuple[int, list[Any]]:
    """Update the active OCIDs, regenerate the dashboard JSON and return new events."""
    store = TrackingStore(db_path)
    store.initialize()
    active = store.list_active_ocids()
    events = sync_ocids(client, store, active, dashboard_path=dashboard_path)
    store.close()
    return len(active), events


def run_cycle(
    settings_path: str | Path,
    search_cache_path: str | Path,
    db_path: str | Path,
    dashboard_path: str | Path,
    max_pages: int = 20,
    paginate_by: int = 50,
    skip_search: bool = False,
    skip_tracking: bool = False,
) -> None:
    """Run one full worker cycle: search cache refresh + tracking + notifications."""
    client = SeaceApiClient()

    if not skip_search:
        settings = load_settings(settings_path)
        count = refresh_search_cache(
            client, settings, search_cache_path, max_pages=max_pages, paginate_by=paginate_by
        )
        logger.info("Búsqueda precalculada: %d oportunidades -> %s", count, search_cache_path)

    if not skip_tracking:
        active_count, events = refresh_tracking(client, db_path, dashboard_path)
        logger.info("Seguimiento: %d OCID activos, %d eventos nuevos -> %s", active_count, len(events), dashboard_path)

        if events:
            # Reparte cada obra solo a los suscriptores que matchean (texto + ficha
            # capturada una vez por obra). Sin suscriptores cae al chat global del .env.
            try:
                repartido = repartir_sync(events, db_path=db_path, output_dir="captures")
                for canal, count in repartido.items():
                    logger.info("Alertas repartidas: %d via %s", count, canal)
            except Exception as exc:
                logger.error("Reparto de alertas falló: %s", exc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Worker de fondo LicitaScan: precalcula búsqueda, refresca seguimiento y envía alertas."
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--search-cache", default=str(DEFAULT_SEARCH_CACHE_PATH))
    parser.add_argument("--db", default=str(DEFAULT_TRACKING_DB_PATH))
    parser.add_argument("--dashboard", default=str(DEFAULT_DASHBOARD_PATH))
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--paginate-by", type=int, default=50)
    parser.add_argument("--skip-search", action="store_true", help="No precalcular la búsqueda")
    parser.add_argument("--skip-tracking", action="store_true", help="No refrescar el seguimiento")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Modo servidor: corre el ciclo en loop usando APScheduler (intervalo por LICITASCAN_SCHEDULE_MINUTES)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.serve:
        return _serve_mode(args)

    run_cycle(
        settings_path=args.settings,
        search_cache_path=args.search_cache,
        db_path=args.db,
        dashboard_path=args.dashboard,
        max_pages=args.max_pages,
        paginate_by=args.paginate_by,
        skip_search=args.skip_search,
        skip_tracking=args.skip_tracking,
    )
    return 0


def _serve_mode(args: argparse.Namespace) -> int:
    """Blocking scheduler loop using APScheduler."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler no está instalado. Instala con: pip install apscheduler")
        sys.exit(1)

    interval_minutes = int(os.getenv("LICITASCAN_SCHEDULE_MINUTES", "30"))
    scheduler = BlockingScheduler(timezone="America/Lima")

    def job() -> None:
        logger.info("=== Iniciando ciclo del worker ===")
        try:
            run_cycle(
                settings_path=args.settings,
                search_cache_path=args.search_cache,
                db_path=args.db,
                dashboard_path=args.dashboard,
                max_pages=args.max_pages,
                paginate_by=args.paginate_by,
                skip_search=args.skip_search,
                skip_tracking=args.skip_tracking,
            )
        except Exception as exc:
            logger.error("Error en ciclo del worker: %s", exc, exc_info=True)

    scheduler.add_job(job, "interval", minutes=interval_minutes, id="worker_cycle")
    logger.info("Worker en modo servidor — ciclo cada %d minutos (America/Lima)", interval_minutes)

    # Run immediately on startup, then on schedule
    job()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker detenido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
