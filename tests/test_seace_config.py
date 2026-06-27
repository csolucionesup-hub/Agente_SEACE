import os

import pytest

from seace_config import get_runtime_config, parse_bool, DEFAULT_SEACE_URL


def test_default_seace_url_uses_current_public_buscador_path():
    assert DEFAULT_SEACE_URL == "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("SI", True),
        ("yes", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("", False),
    ],
)
def test_parse_bool_accepts_common_env_values(value, expected):
    assert parse_bool(value) is expected


def test_runtime_config_reads_safe_sales_demo_overrides(monkeypatch):
    monkeypatch.setenv("SEACE_HEADLESS", "true")
    monkeypatch.setenv("SEACE_KEYWORDS", "puente, pilotes , carretera")
    monkeypatch.setenv("SEACE_YEAR_START", "2025")
    monkeypatch.setenv("SEACE_YEAR_END", "2026")
    monkeypatch.setenv("SEACE_MAX_PAGES", "2")
    monkeypatch.setenv("SEACE_MAX_CAPTURES", "3")
    monkeypatch.setenv("SEACE_OUTPUT_DIR", "demo-output")

    cfg = get_runtime_config()

    assert cfg.headless is True
    assert cfg.keywords == ["PUENTE", "PILOTES", "CARRETERA"]
    assert cfg.year_start == 2025
    assert cfg.year_end == 2026
    assert cfg.max_pages == 2
    assert cfg.max_captures == 3
    assert str(cfg.output_dir) == "demo-output"
