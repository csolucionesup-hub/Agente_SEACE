import csv
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from seace_api import (
    DEFAULT_OCDS_BASE_URL,
    Opportunity,
    SeaceApiClient,
    export_opportunities_csv,
    match_ocid_by_process_code,
    normalize_search_result,
)


def _opp(ocid, process_code):
    return Opportunity(
        keyword="", ocid=ocid, tender_id="", process_code=process_code, entity_name="",
        entity_id="", description="", category="works", procurement_method="", amount=None,
        currency="", date="", tender_start_date="", tender_end_date="", source="", api_url="",
    )


def test_match_ocid_exacto_por_nomenclatura():
    opps = [_opp("ocid-a", "CP-SM-2-2025-INVERMET-1"), _opp("ocid-b", "LP-SM-1-2025-MTC/20-1")]
    assert match_ocid_by_process_code(opps, "cp-sm-2-2025-invermet-1") == "ocid-a"
    assert match_ocid_by_process_code(opps, "LP-SM-1-2025-MTC/20-1") == "ocid-b"


def test_match_ocid_por_nomenclatura_base_sin_sufijo():
    # CONOSCE trae "...-MPC-2" y OECE tiene "...-MPC-1": empareja por la base sin el -N.
    opps = [_opp("ocid-x", "AS-SM-44-2024-CS/MDSMP-1")]
    assert match_ocid_by_process_code(opps, "AS-SM-44-2024-CS/MDSMP-2") == "ocid-x"


def test_match_ocid_sin_coincidencia_devuelve_vacio():
    opps = [_opp("ocid-a", "CP-SM-2-2025-INVERMET-1")]
    assert match_ocid_by_process_code(opps, "ZZZ-999-INEXISTENTE") == ""
    assert match_ocid_by_process_code(opps, "") == ""


SAMPLE_SEARCH_RESULT = {
    "compiledRelease": {
        "ocid": "ocds-dgv273-seacev3-1221249",
        "date": "2026-06-02T10:23:17.575995-05:00",
        "tender": {
            "id": "1221249",
            "title": "SIE-SIE-4-2026-MML-OGA-OL-1",
            "description": "Suministro para puente peatonal",
            "mainProcurementCategory": "goods",
            "procurementMethodDetails": "Subasta Inversa Electrónica",
            "procuringEntity": {
                "name": "MUNICIPALIDAD METROPOLITANA DE LIMA",
                "id": "PE-CONSUCODE-1307",
            },
            "value": {
                "amount": 12345.67,
                "currency": "PEN",
                "currencyName": "Soles",
            },
            "tenderPeriod": {
                "startDate": "2026-06-01T00:00:00-05:00",
                "endDate": "2026-06-10T00:00:00-05:00",
            },
        },
        "sources": [{"name": "Sistema Electrónico de Contrataciones del Estado - Versión 3"}],
    }
}


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params.copy() if params else {}))
        return self.payload



def test_normalize_search_result_extracts_commercial_fields():
    opportunity = normalize_search_result(SAMPLE_SEARCH_RESULT, keyword="puente")

    assert opportunity == Opportunity(
        keyword="PUENTE",
        ocid="ocds-dgv273-seacev3-1221249",
        tender_id="1221249",
        process_code="SIE-SIE-4-2026-MML-OGA-OL-1",
        entity_name="MUNICIPALIDAD METROPOLITANA DE LIMA",
        entity_id="PE-CONSUCODE-1307",
        description="Suministro para puente peatonal",
        category="goods",
        procurement_method="Subasta Inversa Electrónica",
        amount=12345.67,
        currency="PEN",
        date="2026-06-02T10:23:17.575995-05:00",
        tender_start_date="2026-06-01T00:00:00-05:00",
        tender_end_date="2026-06-10T00:00:00-05:00",
        source="Sistema Electrónico de Contrataciones del Estado - Versión 3",
        api_url=f"{DEFAULT_OCDS_BASE_URL}/api/v1/record/ocds-dgv273-seacev3-1221249?format=json",
    )



def test_client_search_opportunities_calls_official_ocds_search_endpoint():
    http = FakeHttp({"results": [SAMPLE_SEARCH_RESULT], "pagination": {"page": 1}})
    client = SeaceApiClient(http=http)

    opportunities = client.search_opportunities("puente", page=2, paginate_by=25)

    assert len(opportunities) == 1
    assert opportunities[0].keyword == "PUENTE"
    called_url, params = http.calls[0]
    assert called_url == f"{DEFAULT_OCDS_BASE_URL}/api/v1/search"
    # The OECE OCDS API only filters on the `search` param; `q` is silently
    # ignored and returns the unfiltered firehose of every tender.
    assert params == {"search": "puente", "page": 2, "paginateBy": 25, "format": "json"}



def test_export_opportunities_csv_writes_lovable_friendly_columns(tmp_path: Path):
    opportunity = normalize_search_result(SAMPLE_SEARCH_RESULT, keyword="puente")
    out = tmp_path / "oportunidades.csv"

    export_opportunities_csv([opportunity], out)

    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows[0]["keyword"] == "PUENTE"
    assert rows[0]["process_code"] == "SIE-SIE-4-2026-MML-OGA-OL-1"
    assert rows[0]["entity_name"] == "MUNICIPALIDAD METROPOLITANA DE LIMA"
    assert rows[0]["amount"] == "12345.67"
    assert rows[0]["record_url"].endswith("/api/v1/record/ocds-dgv273-seacev3-1221249?format=json")



def test_file_catalog_returns_monthly_download_links():
    payload = {
        "results": [
            {
                "id": "seace_v3-2026-06",
                "source": "seace_v3",
                "year": "2026",
                "month": "06",
                "files": {"csv": "https://example.test/csv.zip", "json": "https://example.test/json.zip"},
            }
        ]
    }
    http = FakeHttp(payload)
    client = SeaceApiClient(http=http)

    catalog = client.list_monthly_files(source="seace_v3", year="2026", month="06")

    assert catalog[0]["files"]["csv"] == "https://example.test/csv.zip"
    called_url, params = http.calls[0]
    assert called_url == f"{DEFAULT_OCDS_BASE_URL}/api/v1/files"
    assert params == {"source": "seace_v3", "year": "2026", "month": "06", "format": "json"}
