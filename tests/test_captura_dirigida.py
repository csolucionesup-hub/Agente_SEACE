"""Tests de la captura dirigida por nomenclatura (helpers puros de agente_seace).

La parte Playwright (buscar_y_capturar_obra) se valida con un test de integración en vivo
aparte; aquí cubrimos la lógica pura: derivación de año y término de búsqueda.
"""

from __future__ import annotations

import datetime

from agente_seace import _derive_year_from_nomenclatura, _termino_busqueda_obra


def test_year_se_deriva_de_la_nomenclatura():
    assert _derive_year_from_nomenclatura("LP-ABR-2-2025-CS-MDPP-1") == 2025
    assert _derive_year_from_nomenclatura("AS-SM-13-2024-MDSMV/CS-1") == 2024
    assert _derive_year_from_nomenclatura("LP-SM-9-2024-MTC/20-1") == 2024


def test_year_usa_fallback_cuando_no_hay_anio_parseable():
    assert _derive_year_from_nomenclatura("RARO-SIN-ANIO", fallback=2099) == 2099
    assert _derive_year_from_nomenclatura("", fallback=2031) == 2031


def test_year_cae_al_anio_actual_si_no_hay_fallback():
    assert _derive_year_from_nomenclatura("SIN-ANIO") == datetime.datetime.now().year


def test_year_ignora_numeros_que_no_son_anio_valido():
    # un '1999' o '2101' no debe colarse; cae al fallback
    assert _derive_year_from_nomenclatura("COD-1999-X", fallback=2025) == 2025
    assert _derive_year_from_nomenclatura("COD-2101-X", fallback=2025) == 2025


def test_termino_usa_tramo_de_la_descripcion():
    desc = "REPARACION DE PISTA Y VEREDA; EN EL(LA) AV. SAN JUAN DESDE VIA AUXILIAR"
    termino = _termino_busqueda_obra(desc, "LP-ABR-2-2025-CS-MDPP-1")
    assert termino == desc[:90]
    assert "REPARACION DE PISTA" in termino


def test_termino_cae_a_la_nomenclatura_si_no_hay_descripcion():
    assert _termino_busqueda_obra("", "LP-ABR-2-2025-CS-MDPP-1") == "LP-ABR-2-2025-CS-MDPP-1"
    assert _termino_busqueda_obra("   ", "LP-ABR-2-2025-CS-MDPP-1") == "LP-ABR-2-2025-CS-MDPP-1"
    # descripción demasiado corta para ser distintiva -> nomenclatura
    assert _termino_busqueda_obra("PUENTE", "LP-X-1") == "LP-X-1"
