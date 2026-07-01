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
from datetime import datetime
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


def _merge_keywords(base: Any, extra: Any) -> list[str]:
    """Unión de keywords (base ∪ extra), sin duplicar (case-insensitive), preservando orden."""
    merged: list[str] = []
    seen: set[str] = set()
    for item in list(base or []) + list(extra or []):
        clean = str(item).strip()
        if clean and clean.upper() not in seen:
            merged.append(clean)
            seen.add(clean.upper())
    return merged


def active_subscriber_keywords(db_path: str | Path) -> list[str]:
    """Keywords de todos los suscriptores activos (para la búsqueda-unión del worker)."""
    store = TrackingStore(db_path)
    store.initialize()
    try:
        keywords: list[str] = []
        for sub in store.list_subscribers(active_only=True):
            keywords.extend(sub.keywords)
        return keywords
    finally:
        store.close()


def refresh_search_cache(
    client: Any,
    settings: dict[str, Any],
    cache_path: str | Path,
    max_pages: int = 20,
    paginate_by: int = 50,
    deadline_seconds: float | None = None,
    *,
    extra_keywords: list[str] | None = None,
    years: list[int] | None = None,
) -> list[Any]:
    """Corre la búsqueda profunda y la persiste en el cache de disco.

    ``extra_keywords`` (las de los suscriptores activos) se unen a las de settings
    para que un solo crawl cubra el nicho de todos. ``years`` filtra por año de
    convocatoria (default: año actual + anterior, lo reciente) — mismo criterio que la
    búsqueda web, para que el cache que calienta el worker sea el que el web lee. Devuelve
    las oportunidades encontradas (el worker las usa para sembrar el tracking).
    """
    keywords = _merge_keywords(settings.get("keywords"), extra_keywords)
    if not keywords:
        return []
    if years is None:
        current_year = datetime.now().year
        years = [current_year, current_year - 1]
    cache_key = (tuple(sorted(keywords)), tuple(years), max_pages, paginate_by)
    opportunities, truncated = _deep_search_opportunities(
        client, keywords, years=years, max_pages=max_pages, paginate_by=paginate_by, deadline_seconds=deadline_seconds
    )
    _write_disk_search_cache(cache_path, cache_key, opportunities, truncated)
    return opportunities


def refresh_tracking(
    client: Any,
    db_path: str | Path,
    dashboard_path: str | Path,
    *,
    seed_ocids: list[str] | None = None,
) -> tuple[int, list[Any]]:
    """Refresca el seguimiento y devuelve los eventos nuevos.

    Sigue los OCID ya activos UNIDOS a ``seed_ocids`` (OCID nuevos que descubrió la
    búsqueda). Sembrar un OCID nuevo genera un evento ``nueva_oportunidad`` y, a
    partir de ahí, queda en seguimiento para detectar la buena pro. ``track_record_payload``
    maneja nuevos y existentes igual, así que una sola pasada cubre ambos.
    """
    store = TrackingStore(db_path)
    store.initialize()
    ocids = list(store.list_active_ocids())
    seen = set(ocids)
    for ocid in seed_ocids or []:
        clean = str(ocid).strip()
        if clean and clean not in seen:
            ocids.append(clean)
            seen.add(clean)
    events = sync_ocids(client, store, ocids, dashboard_path=dashboard_path)
    store.close()
    return len(ocids), events


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

    opportunities: list[Any] = []
    if not skip_search:
        settings = load_settings(settings_path)
        extra_keywords = active_subscriber_keywords(db_path)
        opportunities = refresh_search_cache(
            client, settings, search_cache_path,
            max_pages=max_pages, paginate_by=paginate_by, extra_keywords=extra_keywords,
        )
        logger.info("Búsqueda precalculada: %d oportunidades -> %s", len(opportunities), search_cache_path)

    if not skip_tracking:
        # Siembra al tracking los OCID nuevos que encontró la búsqueda (con las keywords
        # de settings + suscriptores), así las alertas se disparan también en obras nuevas.
        seed_ocids = [str(getattr(o, "ocid", "") or "") for o in opportunities] or None
        tracked_count, events = refresh_tracking(client, db_path, dashboard_path, seed_ocids=seed_ocids)
        logger.info("Seguimiento: %d OCID, %d eventos nuevos -> %s", tracked_count, len(events), dashboard_path)

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
