"""Runtime configuration for Agente SEACE.

The production scraper reads from environment variables so we can run a
small sales/demo scan without editing source code or using paid services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import datetime as _dt
import os


DEFAULT_SEACE_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
DEFAULT_KEYWORDS = ["PUENTE", "CARRETERA", "PILOTE", "MICROPILOTE", "CFA", "MUELLE", "PILOTE HINCADO"]


@dataclass(frozen=True)
class RuntimeConfig:
    seace_url: str
    headless: bool
    keywords: list[str]
    year_start: int
    year_end: int
    max_pages: int | None
    max_captures: int | None
    output_dir: Path


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí", "on"}


def _parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None or not value.strip():
        return default
    return int(value.strip())


def _parse_keywords(value: str | None) -> list[str]:
    if not value:
        return DEFAULT_KEYWORDS.copy()
    keywords = [item.strip().upper() for item in value.split(",") if item.strip()]
    return keywords or DEFAULT_KEYWORDS.copy()


def get_runtime_config() -> RuntimeConfig:
    current_year = _dt.datetime.now().year
    return RuntimeConfig(
        seace_url=os.getenv("SEACE_URL", DEFAULT_SEACE_URL),
        headless=parse_bool(os.getenv("SEACE_HEADLESS"), default=True),
        keywords=_parse_keywords(os.getenv("SEACE_KEYWORDS")),
        year_start=int(os.getenv("SEACE_YEAR_START", "2025")),
        year_end=int(os.getenv("SEACE_YEAR_END", str(current_year))),
        max_pages=_parse_int(os.getenv("SEACE_MAX_PAGES")),
        max_captures=_parse_int(os.getenv("SEACE_MAX_CAPTURES")),
        output_dir=Path(os.getenv("SEACE_OUTPUT_DIR", "screenshots")),
    )
