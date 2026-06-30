from pdf_export import build_expediente_html, _money, _date


def test_build_html_incluye_datos_y_sin_ganador():
    opp = {
        "process_code": "LP-ABR-10-2025-C-MPC-2",
        "description": "Mejoramiento del mercado modelo",
        "entity_name": "MUNICIPALIDAD DE CALCA",
        "amount": 68254772,
        "ocid": "ocds-x-1",
        "stage": "convocado",
        "outcome": "activo",
        "winner_name": "",
    }
    html = build_expediente_html(opp, [], [{"title": "Convocatoria", "status": "completed", "date": "2025-12-10"}])
    assert "LP-ABR-10-2025-C-MPC-2" in html
    assert "MUNICIPALIDAD DE CALCA" in html
    assert "S/ 68,254,772" in html
    assert "Aún no hay ganador" in html
    assert "Convocatoria" in html
    assert "LicitaScan" in html


def test_build_html_muestra_ganador_cuando_existe():
    opp = {"process_code": "X", "winner_name": "CONSORCIO Z", "awarded_amount": 2827913, "award_date": "2023-09-07"}
    html = build_expediente_html(opp, [], [])
    assert "CONSORCIO Z" in html
    assert "S/ 2,827,913" in html
    assert "07/09/2023" in html


def test_build_html_escapa_contenido_peligroso():
    html = build_expediente_html({"process_code": "<script>", "description": "a & b"}, [], [])
    assert "&lt;script&gt;" in html


def test_money_y_date_formatters():
    assert _money(68254772) == "S/ 68,254,772"
    assert _money(None) == "—"
    assert _money(900000, "USD") == "USD 900,000"
    assert _date("2025-12-10T00:00:00-05:00") == "10/12/2025"
    assert _date("") == "—"
