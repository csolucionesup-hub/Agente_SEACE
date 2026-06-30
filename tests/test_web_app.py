import json
from dataclasses import replace

import web_app
from fastapi.testclient import TestClient

from seace_api import Opportunity
from web_app import create_app, load_dashboard, load_settings


class FakeSearchClient:
    def __init__(self):
        self.records_requested = []
        self.search_pages = []

    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50):
        self.search_pages.append(page)
        if page > 1:
            return []
        base = Opportunity(
            keyword=keyword,
            ocid="ocds-test-search-1",
            tender_id="122",
            process_code="LP-001-2026-PUENTE",
            entity_name="MUNICIPALIDAD DE PRUEBA",
            entity_id="20123456789",
            description="Reparación de puente vehicular",
            category="works",
            procurement_method="Licitación Pública",
            amount=1_500_000,
            currency="PEN",
            date="2026-06-01T00:00:00-05:00",
            tender_start_date="2026-06-01T00:00:00-05:00",
            tender_end_date="2026-06-15T00:00:00-05:00",
            source="SEACE v3",
            api_url="https://contratacionesabiertas.oece.gob.pe/api/v1/record/ocds-test-search-1?format=json",
        )
        return [base, replace(base, ocid="ocds-test-low", process_code="AS-LOW", amount=250_000)]

    def get_record(self, ocid: str):
        self.records_requested.append(ocid)
        return {
            "records": [
                {
                    "compiledRelease": {
                        "ocid": ocid,
                        "date": "2026-06-01T00:00:00-05:00",
                        "tender": {
                            "id": "122",
                            "title": "LP-001-2026-PUENTE",
                            "description": "Reparación de puente vehicular",
                            "statusDetails": "CONVOCADO",
                            "value": {"amount": 1_500_000, "currency": "PEN"},
                            "procuringEntity": {"id": "20123456789", "name": "MUNICIPALIDAD DE PRUEBA"},
                            "tenderPeriod": {"endDate": "2026-06-15T00:00:00-05:00"},
                            "items": [{"statusDetails": "CONVOCADO"}],
                            "documents": [
                                {
                                    "id": "doc-1",
                                    "title": "Bases Administrativas",
                                    "documentType": "biddingDocuments",
                                    "format": "pdf",
                                    "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=test",
                                    "datePublished": "2026-02-01T00:00:00-05:00",
                                },
                                {
                                    "id": "eto-planos",
                                    "title": "Expediente Técnico de Obra - Planos",
                                    "documentType": "technicalSpecifications",
                                    "format": "pdf",
                                    "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=planos",
                                    "datePublished": "2026-02-02T00:00:00-05:00",
                                },
                                {
                                    "id": "eto-metrados",
                                    "title": "Metrados del Expediente Técnico",
                                    "documentType": "technicalSpecifications",
                                    "format": "xlsx",
                                    "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=metrados",
                                    "datePublished": "2026-02-02T00:00:00-05:00",
                                },
                            ],
                        },
                        "awards": [
                            {
                                "id": "award-1",
                                "documents": [
                                    {
                                        "id": "award-doc-1",
                                        "title": "Documentos de Otorgamiento de Buena Pro",
                                        "documentType": "awardNotice",
                                        "format": "zip",
                                        "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=award",
                                    }
                                ],
                            }
                        ],
                    }
                }
            ]
        }


def write_dashboard(path):
    payload = {
        "counts_by_stage": {"convocado": 1, "contrato_suscrito": 1},
        "counts_by_outcome": {"activo": 1, "contratado": 1},
        "opportunities": [
            {
                "ocid": "ocds-test-1",
                "process_code": "LP-001-2026",
                "entity_name": "MUNICIPALIDAD DE PRUEBA",
                "description": "Construcción de puente vehicular",
                "amount": 1250000,
                "currency": "PEN",
                "tender_status": "",
                "stage": "convocado",
                "next_critical_date": "2026-06-10T00:00:00-05:00",
                "winner_name": "",
                "winner_ruc": "",
                "awarded_amount": None,
                "award_date": "",
                "contract_id": "",
                "contract_date_signed": "",
                "contract_start_date": "",
                "contract_end_date": "",
                "outcome": "activo",
                "official_source_url": "https://prodapp2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml",
                "official_documents": [
                    {
                        "title": "Bases Administrativas",
                        "format": "pdf",
                        "download_url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=test",
                    }
                ],
                "raw_json": "must-not-leak",
            },
            {
                "ocid": "ocds-test-2",
                "process_code": "AS-002-2025",
                "entity_name": "GOBIERNO REGIONAL DE PRUEBA",
                "description": "Expediente técnico carretera vecinal",
                "amount": 380000,
                "currency": "PEN",
                "tender_status": "",
                "stage": "contrato_suscrito",
                "next_critical_date": "",
                "winner_name": "CONSULTORA GANADORA S.A.C.",
                "winner_ruc": "20555555555",
                "awarded_amount": 365400,
                "award_date": "2025-11-27T00:00:00-05:00",
                "contract_id": "C-123",
                "contract_date_signed": "2025-12-01T00:00:00-05:00",
                "contract_start_date": "2025-12-05T00:00:00-05:00",
                "contract_end_date": "2026-02-05T00:00:00-05:00",
                "outcome": "contratado",
            },
        ],
        "recent_events": [
            {
                "ocid": "ocds-test-2",
                "event_type": "contrato_suscrito",
                "title": "Contrato suscrito",
                "message": "Contrato firmado con CONSULTORA GANADORA S.A.C.",
                "severity": "high",
                "occurred_at": "2025-12-01T00:00:00-05:00",
                "payload": {"raw_json": "must-not-leak"},
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_load_dashboard_sanitizes_raw_fields(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)

    data = load_dashboard(dashboard_path)

    assert "raw_json" not in data["opportunities"][0]
    assert "raw_json" not in data["recent_events"][0]["payload"]
    assert data["opportunities"][0]["priority_label"] in {"Alta", "Media", "Baja"}
    assert "commercial_score" in data["opportunities"][0]
    assert "recommended_action" in data["opportunities"][0]


def test_api_serves_dashboard_and_detail(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    dashboard = client.get("/api/dashboard")
    detail = client.get("/api/opportunities/ocds-test-2")

    assert dashboard.status_code == 200
    assert dashboard.json()["counts_by_stage"]["contrato_suscrito"] == 1
    assert dashboard.json()["opportunities"][0]["official_source_url"].startswith("https://prodapp2.seace")
    assert detail.status_code == 200
    assert detail.json()["opportunity"]["winner_name"] == "CONSULTORA GANADORA S.A.C."
    assert detail.json()["timeline"][-1]["event_type"] == "contrato_suscrito"


def test_api_opportunity_ficha_returns_public_ficha_instructions(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path, seace_client=FakeSearchClient()))

    response = client.get("/api/opportunities/ocds-test-1/ficha")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Ficha de Selección SEACE"
    assert data["process_code"] == "LP-001-2026"
    assert data["entity_name"] == "MUNICIPALIDAD DE PRUEBA"
    assert data["source_url"].startswith("https://prodapp2.seace")
    assert data["embed_url"] == data["source_url"]
    assert data["viewer_mode"] == "embedded_official_portal"
    assert "Buscador Público SEACE" in data["message"]
    assert "Ver Ficha de Selección" in " ".join(data["steps"])


class FakeFichaCaptureService:
    def __call__(self, opportunity, output_dir):
        target = output_dir / "ficha-test.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fake-png")
        return {
            "status": "captured",
            "message": "Ficha encontrada y capturada automáticamente.",
            "image_url": "/assets/evidencias/ficha-test.png",
            "process_code": opportunity["process_code"],
            "evidence_path": str(target),
            "captured_at": "2026-06-07T12:00:00",
            "steps_completed": ["open_search", "search_process", "open_ficha", "capture"],
        }


def test_api_opportunity_ficha_capture_returns_internal_evidence(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    static_dir = tmp_path / "web"
    write_dashboard(dashboard_path)
    client = TestClient(
        create_app(
            dashboard_path=dashboard_path,
            static_dir=static_dir,
            seace_client=FakeSearchClient(),
            ficha_capture_service=FakeFichaCaptureService(),
        )
    )

    response = client.post("/api/opportunities/ocds-test-1/ficha/capture")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "captured"
    assert data["process_code"] == "LP-001-2026"
    assert data["image_url"].startswith("/assets/evidencias/")
    assert "open_ficha" in data["steps_completed"]


def test_api_opportunity_ficha_capture_reports_service_failure(tmp_path):
    class BrokenCaptureService:
        def __call__(self, opportunity, output_dir):
            raise RuntimeError("SEACE no respondió")

    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path, ficha_capture_service=BrokenCaptureService()))

    response = client.post("/api/opportunities/ocds-test-1/ficha/capture")

    assert response.status_code == 502
    assert "SEACE no respondió" in response.json()["detail"]


class FakeEtoScrapeService:
    def __call__(self, opportunity):
        return [
            {"categoria": "Memoria descriptiva", "archivos": [
                {"nombre": "MEMORIA DE ARQUITECTURA.pdf", "doc_id": "abc-123", "url": "", "session_only": True, "fecha": "16/03/2026", "tamano_kb": "444.9"},
            ]},
            {"categoria": "Presupuesto de Obra", "archivos": [
                {"nombre": "PRESUPUESTO DE OBRA.pdf", "doc_id": "def-456", "url": "", "session_only": True, "fecha": "16/03/2026", "tamano_kb": "2621.5"},
            ]},
        ]


class FakeEtoDownloadService:
    def __call__(self, opportunity, doc_id, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / f"{doc_id}.pdf"
        target.write_bytes(b"fake-eto-pdf")
        return str(target)


def test_api_eto_scrape_returns_grouped_documents(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path, eto_scrape_service=FakeEtoScrapeService()))

    response = client.post("/api/opportunities/ocds-test-1/eto/scrape")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert [g["categoria"] for g in data["grupos"]] == ["Memoria descriptiva", "Presupuesto de Obra"]
    assert data["grupos"][0]["archivos"][0]["doc_id"] == "abc-123"


def test_api_eto_scrape_reports_failure(tmp_path):
    class Broken:
        def __call__(self, opportunity):
            raise RuntimeError("SEACE bloqueó el scraping")

    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path, eto_scrape_service=Broken()))

    response = client.post("/api/opportunities/ocds-test-1/eto/scrape")

    assert response.status_code == 502
    assert "SEACE bloqueó el scraping" in response.json()["detail"]


def test_api_eto_download_streams_the_file(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path, eto_download_service=FakeEtoDownloadService()))

    response = client.get("/api/opportunities/ocds-test-1/eto/download", params={"doc_id": "abc-123", "nombre": "memoria.pdf"})

    assert response.status_code == 200
    assert response.content == b"fake-eto-pdf"


def test_api_eto_download_requires_doc_id(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get("/api/opportunities/ocds-test-1/eto/download", params={"doc_id": "   "})

    assert response.status_code == 400


def test_api_exports_opportunity_expediente_json(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get("/api/opportunities/ocds-test-1/export")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="expediente-LP-001-2026.json"')
    data = response.json()
    assert data["product"] == "LicitaScan"
    assert data["opportunity"]["process_code"] == "LP-001-2026"
    assert data["opportunity"]["official_documents"][0]["title"] == "Bases Administrativas"
    assert "raw_json" not in json.dumps(data)


def test_api_returns_404_for_unknown_ocid(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get("/api/opportunities/no-existe")

    assert response.status_code == 404


def test_security_headers_are_present(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_api_search_filters_by_min_amount(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=dashboard_path, seace_client=fake))

    response = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 1_000_000})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["ocid"] == "ocds-test-search-1"
    assert data["results"][0]["amount"] == 1_500_000
    assert data["results"][0]["priority_label"] in {"Alta", "Media"}
    assert data["results"][0]["commercial_score"] > 0
    assert fake.search_pages == [1, 2]


def test_api_search_supports_safe_deep_search_without_manual_page_picker(tmp_path):
    class MultiPageClient(FakeSearchClient):
        def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50):
            self.search_pages.append(page)
            if page > 3:
                return []
            base = super().search_opportunities(keyword, page=1, paginate_by=paginate_by)[0]
            return [replace(base, ocid=f"ocds-page-{page}", process_code=f"LP-PAGE-{page}", amount=1_000_000 + page)]

    fake = MultiPageClient()
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", seace_client=fake))

    response = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    assert data["results"][0]["ocid"] == "ocds-page-3"
    assert fake.search_pages[-1] == 4


def test_api_track_adds_ocid_and_regenerates_dashboard(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    db_path = tmp_path / "tracking.sqlite3"
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=dashboard_path, tracking_db_path=db_path, seace_client=fake))

    response = client.post("/api/track", json={"ocids": ["ocds-test-search-1"]})
    dashboard = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["tracked"] == ["ocds-test-search-1"]
    assert dashboard.json()["opportunities"][0]["ocid"] == "ocds-test-search-1"


def test_settings_defaults_and_persistence(tmp_path):
    settings_path = tmp_path / "settings.json"
    defaults = load_settings(settings_path)
    assert defaults["client_name"]
    assert "puente" in defaults["keywords"]

    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", settings_path=settings_path))
    payload = {
        "client_name": "DCC S.A.C.",
        "business_line": "Puentes y obras viales",
        "keywords": ["puente", "pontón", "defensa ribereña", "puente"],
        "min_amount": 2000000,
        "frequency": "cada_hora",
        "channels": ["Telegram", "Excel/PDF"],
        "custom_variables": [{"name": "departamento", "value": "Amazonas"}, {"name": "departamento", "value": "Amazonas"}],
    }

    response = client.put("/api/settings", json=payload)
    reread = client.get("/api/settings")

    assert response.status_code == 200
    assert reread.json()["client_name"] == "DCC S.A.C."
    assert reread.json()["keywords"] == ["puente", "pontón", "defensa ribereña"]
    assert reread.json()["min_amount"] == 2000000
    assert reread.json()["custom_variables"] == [{"name": "departamento", "value": "Amazonas"}]
    assert json.loads(settings_path.read_text(encoding="utf-8"))["frequency"] == "cada_hora"


def test_api_search_hides_dismissed_ocids(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "client_name": "Cliente",
        "business_line": "Infraestructura",
        "keywords": ["PUENTE"],
        "min_amount": 0,
        "frequency": "diario",
        "channels": ["Telegram"],
        "custom_variables": [],
        "ignored_ocids": ["ocds-test-search-1"],
    }), encoding="utf-8")
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", settings_path=settings_path, seace_client=fake))

    response = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["ocid"] == "ocds-test-low"
    assert response.json()["ignored_count"] == 1


def test_api_search_hides_tracked_ocids(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    db_path = tmp_path / "tracking.sqlite3"
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=dashboard_path, tracking_db_path=db_path, seace_client=fake))

    # Sin seguimiento: la búsqueda trae las dos obras.
    before = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})
    assert {row["ocid"] for row in before.json()["results"]} == {"ocds-test-search-1", "ocds-test-low"}
    assert before.json()["tracked_count"] == 0

    # Agrego una a seguimiento.
    assert client.post("/api/track", json={"ocids": ["ocds-test-search-1"]}).status_code == 200

    # Ahora la búsqueda ya no la trae (sería redundante con la bandeja).
    after = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})
    data = after.json()
    assert {row["ocid"] for row in data["results"]} == {"ocds-test-low"}
    assert data["tracked_count"] == 1


def test_api_untrack_removes_from_tracking_and_brings_it_back_to_search(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    db_path = tmp_path / "tracking.sqlite3"
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=dashboard_path, tracking_db_path=db_path, seace_client=fake))

    client.post("/api/track", json={"ocids": ["ocds-test-search-1"]})
    assert client.get("/api/dashboard").json()["opportunities"]

    response = client.post("/api/untrack", json={"ocids": ["ocds-test-search-1"]})
    assert response.status_code == 200
    assert response.json()["untracked"] == ["ocds-test-search-1"]

    # La bandeja queda vacía...
    assert client.get("/api/dashboard").json()["opportunities"] == []
    # ...y la búsqueda vuelve a traer la obra.
    search = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})
    assert "ocds-test-search-1" in {row["ocid"] for row in search.json()["results"]}


def test_api_untrack_requires_ocids(tmp_path):
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", tracking_db_path=tmp_path / "t.sqlite3"))
    assert client.post("/api/untrack", json={"ocids": []}).status_code == 400


def test_ficha_capture_skips_old_seace_v2_obras_without_browser(tmp_path):
    # Las obras v2 (procesos antiguos) no están en el buscador v3 → corta sin abrir el
    # navegador y devuelve un estado claro en vez de intentar (y fallar) la captura.
    from web_app import _default_ficha_capture_service
    opp = {
        "ocid": "ocds-dgv273-seacev2-247622",
        "process_code": "LPN-3-2005-MTC/20",
        "entity_name": "MTC - PROVIAS NACIONAL",
        "description": "Construccion de puentes",
    }
    result = _default_ficha_capture_service(opp, tmp_path)
    assert result["status"] == "old_version"
    assert result["image_url"] == ""
    assert "SEACE v2" in result["message"]


def test_api_dismiss_persists_ignored_ocid(tmp_path):
    settings_path = tmp_path / "settings.json"
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", settings_path=settings_path))

    response = client.post("/api/dismiss", json={"ocid": "ocds-test-search-1"})
    settings = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json()["ignored_ocids"] == ["ocds-test-search-1"]
    assert settings.json()["ignored_ocids"] == ["ocds-test-search-1"]


def test_api_restore_dismissed_ocid_makes_it_visible_again(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "client_name": "Cliente",
        "business_line": "Infraestructura",
        "keywords": ["PUENTE"],
        "min_amount": 0,
        "frequency": "diario",
        "channels": ["Telegram"],
        "custom_variables": [],
        "ignored_ocids": ["ocds-test-search-1", "ocds-test-low"],
    }), encoding="utf-8")
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", settings_path=settings_path, seace_client=fake))

    restore = client.post("/api/dismiss/restore", json={"ocid": "ocds-test-search-1"})
    search = client.get("/api/search", params={"keywords": "PUENTE", "min_amount": 0})

    assert restore.status_code == 200
    assert restore.json()["ignored_ocids"] == ["ocds-test-low"]
    assert search.status_code == 200
    assert [item["ocid"] for item in search.json()["results"]] == ["ocds-test-search-1"]
    assert search.json()["ignored_count"] == 1


def test_api_search_supports_seace_style_filters_for_object_type_entity_method_and_dates(tmp_path):
    class FilterClient(FakeSearchClient):
        def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50):
            self.search_pages.append(page)
            if page > 1:
                return []
            base = super().search_opportunities(keyword, page=1, paginate_by=paginate_by)[0]
            return [
                base,
                replace(base, ocid="ocds-goods", category="goods", process_code="BIEN-001", description="Compra de cemento", amount=2_000_000),
                replace(base, ocid="ocds-service", category="services", process_code="SERV-001", description="Servicio de mantenimiento", amount=2_500_000),
                replace(base, ocid="ocds-old", category="works", process_code="OBRA-OLD", entity_name="MUNICIPALIDAD DE PRUEBA", date="2026-05-01T00:00:00-05:00"),
                replace(base, ocid="ocds-other-entity", category="works", process_code="OBRA-OTHER", entity_name="GOBIERNO REGIONAL", amount=3_000_000),
                replace(base, ocid="ocds-other-method", category="works", process_code="OBRA-AS", procurement_method="Adjudicación Simplificada", amount=3_500_000),
            ]

    fake = FilterClient()
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", seace_client=fake))

    response = client.get("/api/search", params={
        "keywords": "PUENTE",
        "min_amount": 0,
        "contract_object": "obra",
        "entity_name": "municipalidad",
        "selection_type": "licitación",
        "publication_from": "2026-06-01",
        "publication_to": "2026-06-30",
    })

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["ocid"] == "ocds-test-search-1"
    assert response.json()["filters"]["contract_object"] == "obra"
    assert response.json()["filtered_out_count"] == 5


def test_api_search_returns_zero_result_advice_for_restrictive_filters(tmp_path):
    class NoMatchClient(FakeSearchClient):
        def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50):
            return [
                Opportunity(
                    keyword=keyword,
                    ocid=f"ocds-zero-{page}",
                    tender_id=f"rel-zero-{page}",
                    process_code="LP-001-2026-PUENTE",
                    entity_name="MUNICIPALIDAD DE PRUEBA",
                    entity_id="20123456789",
                    description="CONTRATACIÓN PARA LA EJECUCIÓN DE OBRA: REPARACION DE PUENTE",
                    category="works",
                    procurement_method="",
                    amount=1_200_000,
                    currency="PEN",
                    date="2026-02-01T00:00:00Z",
                    tender_start_date="2026-02-01T00:00:00Z",
                    tender_end_date="2026-03-01T00:00:00Z",
                    source="SEACE v3",
                    api_url="https://contratacionesabiertas.oece.gob.pe/api/v1/record/ocds-zero?format=json",
                )
            ]

    app = create_app(seace_client=NoMatchClient(), settings_path=tmp_path / "settings.json")
    with TestClient(app) as client:
        response = client.get(
            "/api/search",
            params={
                "keywords": "puente",
                "contract_object": "obra",
                "selection_type": "licitacion publica",
                "description_filter": "puentes",
                "min_amount": "1000000",
                "publication_from": "2026-01-01",
                "publication_to": "2026-12-31",
                "convocatoria_from": "2026-01-01",
                "convocatoria_to": "2026-12-31",
                "max_pages": "1",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["filtered_out_count"] == 1
    assert data["search_advice"]
    assert any("Tipo de selección" in item for item in data["search_advice"])
    assert any("convocatoria" in item.lower() for item in data["search_advice"])
    assert data["recommended_relaxation"]["selection_type"] == ""
    assert data["recommended_relaxation"]["convocatoria_from"] == ""


def test_search_uses_settings_defaults_when_fields_are_omitted(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "client_name": "Cliente",
        "business_line": "Infraestructura",
        "keywords": ["PUENTE"],
        "min_amount": 1000000,
        "frequency": "diario",
        "channels": ["Telegram"],
        "custom_variables": [{"name": "especialidad", "value": "puente"}],
    }), encoding="utf-8")
    fake = FakeSearchClient()
    client = TestClient(create_app(dashboard_path=tmp_path / "dashboard.json", settings_path=settings_path, seace_client=fake))

    response = client.get("/api/search")

    assert response.status_code == 200
    assert response.json()["keywords"] == ["PUENTE"]
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["amount"] == 1500000
    assert "Coincide con variable especialidad: puente" in response.json()["results"][0]["commercial_reasons"]


def test_api_lists_documents_with_verification_and_analysis_without_download_quota(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    fake = FakeSearchClient()
    monkeypatch.setattr(
        web_app,
        "verify_document_link",
        lambda url: {
            "status": "available",
            "ok": True,
            "content_type": "application/pdf",
            "content_length": 1234,
            "probe_bytes": 512,
            "message": "Documento verificado. La vista/listado no consume descarga.",
        },
    )
    monkeypatch.setattr(
        web_app,
        "analyze_document",
        lambda url, fmt="": {
            "verification": {"ok": True, "status": "available"},
            "analysis_status": "analyzed",
            "format": fmt or "pdf",
            "technical_signals": {
                "pilotes": {"status": "not_detected", "matches": []},
                "zapatas": {"status": "detected", "matches": [{"term": "zapatas", "count": 2}]},
                "estribos": {"status": "detected", "matches": [{"term": "estribos", "count": 1}]},
            },
            "message": "PDF analizado por texto extraíble; si está escaneado puede requerir OCR.",
        },
    )
    client = TestClient(create_app(dashboard_path=dashboard_path, seace_client=fake))

    response = client.get("/api/opportunities/ocds-test-1/documents", params={"verify": "true", "analyze": "true"})

    assert response.status_code == 200
    data = response.json()
    assert data["quota_policy"]["viewing_consumes_credit"] is False
    assert data["quota_policy"]["verification_consumes_download"] is False
    assert data["quota_policy"]["download_consumes_only_on_success"] is True
    assert data["count"] >= 2
    assert data["documents"][0]["title"] == "Bases Administrativas"
    assert data["documents"][0]["verification"]["ok"] is True
    assert data["documents"][0]["analysis"]["technical_signals"]["zapatas"]["status"] == "detected"
    assert fake.records_requested == ["ocds-test-1"]


def test_document_download_failure_returns_no_quota_message(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)

    def fail_download(url, filename=""):
        raise RuntimeError("SEACE no respondió")

    monkeypatch.setattr(web_app, "download_verified_document", fail_download)
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get(
        "/api/documents/download",
        params={
            "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=test",
            "filename": "bases.pdf",
        },
    )

    assert response.status_code == 502
    assert "no debe consumir cuota" in response.json()["detail"]


def test_document_download_success_returns_attachment_only_after_fetch_success(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)

    class Download:
        filename = "bases.pdf"
        content_type = "application/pdf"
        content = b"%PDF-test"

    monkeypatch.setattr(web_app, "download_verified_document", lambda url, filename="": Download())
    client = TestClient(create_app(dashboard_path=dashboard_path))

    response = client.get(
        "/api/documents/download",
        params={
            "url": "https://prod1.seace.gob.pe/SeaceWeb-PRO/SdescargarArchivoAlfresco?fileCode=test",
            "filename": "bases.pdf",
        },
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-test"
    assert response.headers["content-disposition"] == 'attachment; filename="bases.pdf"'


def test_api_exposes_separate_eto_layer_with_official_sections_and_quota_policy(tmp_path, monkeypatch):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)
    fake = FakeSearchClient()
    monkeypatch.setattr(
        web_app,
        "verify_document_link",
        lambda url: {
            "status": "available",
            "ok": True,
            "content_type": "application/pdf" if "planos" in url else "application/octet-stream",
            "content_length": 2048,
            "probe_bytes": 512,
            "message": "Documento verificado. La vista/listado no consume descarga.",
        },
    )
    monkeypatch.setattr(
        web_app,
        "analyze_document",
        lambda url, fmt="": {
            "verification": {"ok": True, "status": "available"},
            "analysis_status": "analyzed",
            "format": fmt or "pdf",
            "technical_signals": {
                "pilotes": {"status": "not_detected", "matches": []},
                "planos": {"status": "detected", "matches": [{"term": "planos", "count": 1}]},
                "metrados": {"status": "detected", "matches": [{"term": "metrados", "count": 1}]},
                "expediente_tecnico": {"status": "detected", "matches": [{"term": "expediente técnico", "count": 1}]},
            },
            "message": "Documento ETO analizado por texto extraíble.",
        },
    )
    client = TestClient(create_app(dashboard_path=dashboard_path, seace_client=fake))

    response = client.get("/api/opportunities/ocds-test-1/eto", params={"verify": "true", "analyze": "true"})

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Expediente Técnico de Obra"
    assert data["status"] == "detected"
    assert data["eligibility"]["is_work"] is True
    assert "Objeto de contratación = Obra" in data["eligibility"]["reason"]
    assert data["quota_policy"]["viewing_consumes_credit"] is False
    assert data["quota_policy"]["failed_download_consumes_download"] is False
    assert {section["id"] for section in data["sections"]} >= {"section_2", "section_3", "section_4"}
    section_2 = next(section for section in data["sections"] if section["id"] == "section_2")
    assert "Metrados" in section_2["official_components"]
    assert any(doc["eto_component"] == "planos" for doc in data["documents"])
    assert any(doc["eto_component"] == "metrados" for doc in data["documents"])
    assert data["technical_summary"]["planos"] == "detected"
    assert data["technical_summary"]["pilotes"] == "not_detected"


def test_api_eto_for_work_without_registered_eto_explains_public_ficha_requirement(tmp_path):
    dashboard_path = tmp_path / "dashboard.json"
    write_dashboard(dashboard_path)

    class WorkWithoutEtoClient(FakeSearchClient):
        def get_record(self, ocid: str):
            payload = super().get_record(ocid)
            payload["records"][0]["compiledRelease"]["tender"]["documents"] = [
                payload["records"][0]["compiledRelease"]["tender"]["documents"][0]
            ]
            return payload

    client = TestClient(create_app(dashboard_path=dashboard_path, seace_client=WorkWithoutEtoClient()))

    response = client.get("/api/opportunities/ocds-test-1/eto")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "requires_public_ficha_check"
    assert data["documents"] == []
    assert "Ficha de Selección" in data["message"]
    assert "Ver Expediente Técnico de Obra" in data["message"]
