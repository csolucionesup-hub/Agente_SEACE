"""Tests de la captura dirigida por nomenclatura (helpers puros de agente_seace).

La parte Playwright (buscar_y_capturar_obra) se valida con un test de integración en vivo
aparte; aquí cubrimos la lógica pura: derivación de año y término de búsqueda.
"""

from __future__ import annotations

import datetime

from agente_seace import _base_nomenclatura, _derive_year_from_nomenclatura, _parse_eto_doc, _termino_busqueda_obra


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


def test_termino_usa_el_nombre_entre_comillas_y_evita_el_mojibake():
    # Caso real Calca: la comilla de apertura llega corrupta como '¿' y rompe la búsqueda.
    # El término debe ser el nombre del proyecto (entre comillas), sin el prefijo ni el ¿.
    desc = 'EJECUCION DE OBRA ¿MEJORAMIENTO Y AMPLIACIÓN DE LOS SERVICIOS COMERCIALES DEL MERCADO MODELO DE LA CIUDAD DE CALCA'
    termino = _termino_busqueda_obra(desc, "LP-ABR-10-2025-C-MPC-2")
    assert termino.startswith("MEJORAMIENTO Y AMPLIACIÓN")
    assert "¿" not in termino
    assert "EJECUCION DE OBRA" not in termino


def test_base_nomenclatura_quita_la_convocatoria_final():
    # SEACE lista la obra con otra convocatoria (-1) aunque la data traiga -2.
    assert _base_nomenclatura("LP-ABR-10-2025-C-MPC-2") == "LP-ABR-10-2025-C-MPC"
    assert _base_nomenclatura("PEC-PROC-4-2023-MTC/01-1") == "PEC-PROC-4-2023-MTC/01"


def test_base_nomenclatura_no_se_come_el_anio():
    # Si el sufijo es el año, NO se debe quitar (no hay 20XX antes que sobreviva).
    assert _base_nomenclatura("AS-1-2025") == "AS-1-2025"
    assert _base_nomenclatura("") == ""


def test_parse_eto_doc_privado_flag3_sin_url():
    # Caso real del ETO: descarga privada por sesión (flag 3) y 3er argumento vacío.
    onclick = ("javascript:descargaDocGeneral('45346b46-3b4a-4b40-89aa-77c716dbaaea','3','');;"
               "PrimeFaces.ab({source:'frm:tbDetalleTecnicoObra:dsMemoriaETO:0:j_idt221'});return false;")
    doc_id, flag, url = _parse_eto_doc(onclick)
    assert doc_id == "45346b46-3b4a-4b40-89aa-77c716dbaaea"
    assert flag == "3"
    assert url == ""


def test_parse_eto_doc_con_url_directa():
    onclick = "javascript:descargaDocGeneral('id-1','1','https://prod2.seace.gob.pe/archivo/x.pdf')"
    doc_id, flag, url = _parse_eto_doc(onclick)
    assert doc_id == "id-1"
    assert url == "https://prod2.seace.gob.pe/archivo/x.pdf"
