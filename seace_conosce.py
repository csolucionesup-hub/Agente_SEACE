"""Módulo de inteligencia histórica CONOSCE para LicitaScan.

CONOSCE expone archivos XLSX mensuales con convocatorias públicas del Estado peruano
(fuente: https://conosce.osce.gob.pe). Este módulo los descarga, los parsea y genera
resúmenes de mercado: entidades que más compran, categorías, ganadores recurrentes.

Los resultados se cachean localmente 24 h para no sobrecargar la fuente.
"""

from __future__ import annotations

import io
import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any
import urllib.request

logger = logging.getLogger(__name__)

CONOSCE_BASE = "https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/convocatorias"
CACHE_DIR = Path("data/conosce")
CACHE_TTL_SECONDS = 86400  # 24 h


def _candidate_urls(year: int) -> list[str]:
    return [
        f"{CONOSCE_BASE}/{year}/CONOSCE_CONVOCATORIAS{year}_0.xlsx",
        f"{CONOSCE_BASE}/{year}/CONOSCE_CONVOCATORIAS{year}_1.xlsx",
        f"{CONOSCE_BASE}/{year}/CONOSCE_CONVOCATORIAS{year}.xlsx",
    ]


def _download_bytes(url: str, timeout: float = 40.0) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LicitaScan/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return response.read()
    except Exception as exc:
        logger.debug("CONOSCE download failed %s: %s", url, exc)
    return None


def _parse_xlsx_rows(data: bytes) -> list[dict[str, str]]:
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl not installed; cannot parse CONOSCE XLSX")
        return []
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = workbook.active
        all_rows = list(sheet.iter_rows(values_only=True))
        if not all_rows:
            return []
        headers = [str(cell or "").strip().upper() for cell in all_rows[0]]
        result: list[dict[str, str]] = []
        for raw_row in all_rows[1:]:
            if not any(raw_row):
                continue
            result.append({header: str(cell or "").strip() for header, cell in zip(headers, raw_row)})
        return result
    except Exception as exc:
        logger.error("CONOSCE XLSX parse error: %s", exc)
        return []


def _to_float(value: str) -> float:
    try:
        return float(str(value).replace(",", "").replace(" ", "").replace("S/", ""))
    except (ValueError, AttributeError):
        return 0.0


def _field(row: dict[str, str], *candidates: str) -> str:
    for key in candidates:
        value = row.get(key.upper(), "")
        if value:
            return value
    return ""


def summarize_rows(rows: list[dict[str, str]], keyword: str = "") -> dict[str, Any]:
    keyword_lower = keyword.strip().lower()
    filtered = rows
    if keyword_lower:
        filtered = [row for row in rows if keyword_lower in " ".join(row.values()).lower()]

    total = len(filtered)
    total_amount = sum(_to_float(_field(row, "MONTO_REFERENCIAL", "MONTO", "VALOR_REFERENCIAL")) for row in filtered)

    entity_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    winner_counts: dict[str, int] = {}

    for row in filtered:
        entity = _field(row, "ENTIDAD", "NOMBRE_ENTIDAD", "ENTIDAD_COMPRADORA")
        if entity:
            entity_counts[entity] = entity_counts.get(entity, 0) + 1

        category = _field(row, "OBJETO_CONTRATACION", "TIPO_OBJETO", "OBJETO")
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1

        winner = _field(row, "GANADOR", "PROVEEDOR", "POSTOR_GANADOR", "NOMBRE_POSTOR")
        if winner:
            winner_counts[winner] = winner_counts.get(winner, 0) + 1

    return {
        "total_records": total,
        "total_amount": round(total_amount, 2),
        "keyword_filter": keyword,
        "top_entities": [
            {"name": name, "count": count}
            for name, count in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
        "top_categories": [
            {"name": name, "count": count}
            for name, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
        "top_winners": [
            {"name": name, "count": count}
            for name, count in sorted(winner_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
        "sample_records": [
            {
                "entity": _field(row, "ENTIDAD", "NOMBRE_ENTIDAD"),
                "description": _field(row, "DESCRIPCION", "OBJETO_CONTRATACION", "OBJETO"),
                "amount": _to_float(_field(row, "MONTO_REFERENCIAL", "MONTO")),
                "year": _field(row, "ANIO", "YEAR", "AÑO"),
                "process_code": _field(row, "NUMERO_EXPEDIENTE", "NOMENCLATURA", "CODIGO"),
            }
            for row in filtered[:5]
        ],
    }


def _cache_key_path(year: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"convocatorias_{year}.json"


def _load_cache(year: int) -> list[dict[str, str]] | None:
    path = _cache_key_path(year)
    if not path.exists():
        return None
    if (time.time() - path.stat().st_mtime) > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    except Exception:
        return None


def _save_cache(year: int, rows: list[dict[str, str]]) -> None:
    path = _cache_key_path(year)
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_market_intel(keyword: str = "", year: int | None = None, force_refresh: bool = False) -> dict[str, Any]:
    """Return market intelligence summary from CONOSCE data.

    Downloads and caches the XLSX for the requested year. Returns a summary
    filtered by keyword if provided. Falls back gracefully if unavailable.
    """
    target_year = year or date.today().year

    # Try cache first
    if not force_refresh:
        cached_rows = _load_cache(target_year)
        if cached_rows is not None:
            logger.debug("CONOSCE: cache hit for %d (%d rows)", target_year, len(cached_rows))
            return summarize_rows(cached_rows, keyword)

    # Download
    rows: list[dict[str, str]] = []
    for url in _candidate_urls(target_year):
        data = _download_bytes(url)
        if data:
            rows = _parse_xlsx_rows(data)
            if rows:
                _save_cache(target_year, rows)
                logger.info("CONOSCE: downloaded %d rows from %s", len(rows), url)
                break

    if not rows:
        # Try expired cache as last resort
        path = _cache_key_path(target_year)
        if path.exists():
            try:
                rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
                logger.warning("CONOSCE: using stale cache for %d", target_year)
            except Exception:
                pass

    if not rows:
        return {
            "total_records": 0,
            "total_amount": 0,
            "keyword_filter": keyword,
            "top_entities": [],
            "top_categories": [],
            "top_winners": [],
            "sample_records": [],
            "status": "unavailable",
            "message": (
                f"No se pudo descargar el archivo CONOSCE para {target_year}. "
                "El archivo se publica mensualmente y puede no estar disponible aún. "
                "Prueba con el año anterior."
            ),
        }

    result = summarize_rows(rows, keyword)
    result["status"] = "ok"
    return result
