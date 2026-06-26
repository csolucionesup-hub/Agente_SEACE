from seace_tracking import snapshot_from_record


def record_with_tender_only():
    return {
        "records": [
            {
                "compiledRelease": {
                    "ocid": "ocds-test-tender",
                    "date": "2026-06-01T10:00:00-05:00",
                    "tender": {
                        "id": "123",
                        "title": "LP-1-2026-MTC-1",
                        "description": "Construcción de puente",
                        "status": "active",
                        "procuringEntity": {"name": "MTC"},
                        "value": {"amount": 1000000.0, "currency": "PEN"},
                        "tenderPeriod": {
                            "startDate": "2026-06-01T00:00:00-05:00",
                            "endDate": "2026-06-20T00:00:00-05:00",
                        },
                        "items": [{"statusDetails": "CONVOCADO"}],
                        "documents": [
                            {
                                "id": "doc-bases",
                                "title": "Bases Administrativas",
                                "documentType": "biddingDocuments",
                                "format": "pdf",
                                "url": "https://seace.example/bases.pdf",
                                "datePublished": "2026-06-01T11:00:00-05:00",
                                "language": "es",
                            },
                            {
                                "id": "doc-propuestas",
                                "title": "Documentos de Presentación de Propuestas",
                                "documentType": "biddingDocuments",
                                "format": "zip",
                                "url": "https://seace.example/propuestas.zip",
                                "datePublished": "2026-06-02T11:00:00-05:00",
                                "language": "es",
                            },
                        ],
                    },
                }
            }
        ]
    }


def record_with_award_and_contract():
    return {
        "records": [
            {
                "compiledRelease": {
                    "ocid": "ocds-test-award",
                    "date": "2026-07-01T10:00:00-05:00",
                    "tender": {
                        "title": "LP-2-2026-MTC-1",
                        "description": "Construcción de carretera",
                        "status": "complete",
                        "procuringEntity": {"name": "MTC"},
                        "value": {"amount": 2000000.0, "currency": "PEN"},
                    },
                    "awards": [
                        {
                            "id": "award-1",
                            "date": "2026-07-10T00:00:00-05:00",
                            "value": {"amount": 1800000.0, "currency": "PEN"},
                            "suppliers": [{"id": "PE-RUC-20123456789", "name": "CONSTRUCTORA GANADORA SAC"}],
                        }
                    ],
                    "contracts": [
                        {
                            "id": "contract-1",
                            "dateSigned": "2026-07-20T00:00:00-05:00",
                            "period": {
                                "startDate": "2026-08-01T00:00:00-05:00",
                                "endDate": "2026-12-31T00:00:00-05:00",
                            },
                        }
                    ],
                }
            }
        ]
    }


def test_snapshot_from_record_maps_active_tender():
    snapshot = snapshot_from_record(record_with_tender_only())

    assert snapshot.ocid == "ocds-test-tender"
    assert snapshot.process_code == "LP-1-2026-MTC-1"
    assert snapshot.entity_name == "MTC"
    assert snapshot.amount == 1000000.0
    assert snapshot.currency == "PEN"
    assert snapshot.tender_status == "active"
    assert snapshot.stage == "convocado"
    assert snapshot.next_critical_date == "2026-06-20T00:00:00-05:00"
    assert snapshot.outcome == "activo"
    assert snapshot.winner_name == ""


def test_snapshot_preserves_official_tender_documents_for_dashboard():
    snapshot = snapshot_from_record(record_with_tender_only())

    documents = snapshot.raw["tender"]["documents"]
    assert documents[0]["title"] == "Bases Administrativas"
    assert documents[0]["url"].startswith("https://")


def test_snapshot_from_record_maps_award_and_contract():
    snapshot = snapshot_from_record(record_with_award_and_contract())

    assert snapshot.stage == "contrato_suscrito"
    assert snapshot.outcome == "contratado"
    assert snapshot.winner_name == "CONSTRUCTORA GANADORA SAC"
    assert snapshot.winner_ruc == "20123456789"
    assert snapshot.awarded_amount == 1800000.0
    assert snapshot.award_date == "2026-07-10T00:00:00-05:00"
    assert snapshot.contract_id == "contract-1"
    assert snapshot.contract_date_signed == "2026-07-20T00:00:00-05:00"
    assert snapshot.contract_start_date == "2026-08-01T00:00:00-05:00"
    assert snapshot.contract_end_date == "2026-12-31T00:00:00-05:00"
