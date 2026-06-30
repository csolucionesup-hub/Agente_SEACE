from seace_documents import filter_relevant_documents


def _docs_reales_de_la_obra():
    # Muestra real del record OCDS de PEC-PROC-6-2023 (ocds-dgv273-seacev3-2023-24-91):
    # 4 documentos de licitación que valen + ruido (calificación, resumen ejecutivo) +
    # documentos de contrato. El usuario solo quiere los 4.
    return [
        {"title": "Bases Administrativas", "document_type": "biddingDocuments", "section": "tender"},
        {"title": "Bases Integradas", "document_type": "biddingDocuments", "section": "tender"},
        {"title": "Documentos de Calificación y Evaluación", "document_type": "evaluationReports", "section": "tender"},
        {"title": "Documentos de Otorgamiento de Buena Pro", "document_type": "awardNotice", "section": "tender"},
        {"title": "Documentos de Presentación de Propuestas", "document_type": "biddingDocuments", "section": "tender"},
        {"title": "Resumen ejecutivo", "document_type": "biddingDocuments", "section": "tender"},
        {"title": "152663831", "document_type": "", "section": "contract-1"},
        {"title": "Archivos del contrato", "document_type": "contractSigned", "section": "contract-1"},
        {"title": "Archivos de la ampliación del contrato", "document_type": "contractAnnexe", "section": "contract-1"},
    ]


def test_filter_keeps_only_the_four_relevant_tender_documents():
    kept = [d["title"] for d in filter_relevant_documents(_docs_reales_de_la_obra())]
    assert kept == [
        "Bases Administrativas",
        "Bases Integradas",
        "Documentos de Otorgamiento de Buena Pro",
        "Documentos de Presentación de Propuestas",
    ]


def test_filter_drops_resumen_ejecutivo_despite_sharing_type_with_bases():
    # "Resumen ejecutivo" es biddingDocuments igual que las Bases; se filtra por título.
    titles = [d["title"] for d in filter_relevant_documents(_docs_reales_de_la_obra())]
    assert "Resumen ejecutivo" not in titles
    assert "Documentos de Calificación y Evaluación" not in titles


def test_filter_drops_all_contract_documents():
    titles = [d["title"] for d in filter_relevant_documents(_docs_reales_de_la_obra())]
    assert "Archivos del contrato" not in titles
    assert "152663831" not in titles


def test_filter_handles_missing_title_gracefully():
    assert filter_relevant_documents([{"document_type": "biddingDocuments"}]) == []
    assert filter_relevant_documents([]) == []
