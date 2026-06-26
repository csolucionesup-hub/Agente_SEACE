from pathlib import Path


def test_frontend_static_contract_exists():
    web_dir = Path("web")
    index = web_dir / "index.html"
    css = web_dir / "styles.css"
    js = web_dir / "app.js"

    assert index.exists()
    assert css.exists()
    assert js.exists()

    html = index.read_text(encoding="utf-8")
    script = js.read_text(encoding="utf-8")

    assert "LicitaScan" in html
    assert "Detecta primero" in html
    assert "licitascan-logo-cropped.jpg" in html
    assert "dashboard-view" in html
    assert "opportunities-view" in html
    assert "detail-view" in html
    assert "alerts-view" in html
    assert "settings-view" in html
    assert "search-view" in html
    assert "Buscar en todo SEACE" in html
    assert "new-search-pages" not in html
    assert "Resultados por página" in html
    assert "Mayor probabilidad" in html
    assert "fetch('/api/dashboard')" in script
    assert "commercial_score" in script
    assert "priority_label" in script
    assert "recommended_action" in script
    assert "official_documents" in script
    assert "official_source_url" in script
    assert "Ver fuente oficial" in script
    assert "Exportar expediente" in script
    assert "Ver ficha SEACE" in script
    assert "/ficha" in script
    assert "renderFichaViewer" in script
    assert "Buscador Público SEACE" in script
    assert "seace-iframe" in script
    assert "Vista oficial embebida" in script
    assert "iframe" in script
    assert "Buscar ficha automáticamente" in script
    assert "/ficha/capture" in script
    assert "renderFichaCapture" in script
    assert "ficha-capture-image" in script
    assert "Documentos oficiales" in html
    assert "/api/opportunities/" in script
    assert "/export" in script
    assert "/api/search" in script
    assert "/api/track" in script
    assert "renderSearchPage" in script
    assert "searchPrevPage" in script
    assert "searchNextPage" in script
    assert "/api/settings" in script
    assert "settings-keyword-list" in html
    assert "settings-custom-list" in html
    assert "settings-save" in html
    assert "data-delete-keyword" in script
    assert "data-delete-custom" in script
    assert "Por qué:" in script
    assert "/api/dismiss" in script
    assert "Descartar" in script
    assert "data-dismiss-ocid" in script
    assert "/api/dismiss/restore" in script
    assert "settings-ignored-list" in html
    assert "data-restore-ocid" in script
    assert "new-search-contract-object" in html
    assert "Bien" in html
    assert "Consultoría de Obra" in html
    assert "Obra" in html
    assert "Servicio" in html
    assert "new-search-selection-type" in html
    assert "new-search-publication-from" in html
    assert "new-search-publication-to" in html
    assert "new-search-entity" in html
    assert "contract_object" in script
    assert "publication_from" in script
    assert "recommended-search-preset" in html
    assert "applyRecommendedSearchPreset" in script
    assert "renderNoResultsAdvice" in script
    assert "Ampliar búsqueda automáticamente" in script
    assert "search_advice" in script
    assert "Tipo de selección" in html
    assert "/documents?verify=true" in script
    assert "/api/documents/download" in script
    assert "Descargar verificada" in script
    assert "Analizar señales" in script
    assert "Pilotes" in script
    assert "no consume créditos ni descargas" in script
    assert "Expediente Técnico de Obra" in script
    assert "/eto?verify=true" in script
    assert "renderTechnicalFile" in script
    assert "Planos" in script
    assert "Metrados" in script
    assert "Presupuesto" in script
    assert "Ficha de Selección" in script
    assert "Buscador de Procedimientos de Selección" in html
    assert "Flujo similar a SEACE" in html
    assert "Objeto de Contratación" in html
    assert "Descripción del Objeto" in html
    assert "Año de la Convocatoria" in html
    assert "Versión SEACE" in html
    assert "Seace 3" in html
    assert "Buscar obras de puente" in html
    assert "Sección 2" in html
    assert "pilotes" in html.lower()
    assert "seace-flow-step" in html


def test_frontend_has_contextual_tooltips_for_seace_terms_and_actions():
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    required_tooltips = [
        "tooltip-contract-object",
        "tooltip-selection-type",
        "tooltip-publication-date",
        "tooltip-convocatoria-date",
        "tooltip-commercial-score",
        "tooltip-track-action",
        "tooltip-dismiss-action",
        "tooltip-settings-keywords",
        "tooltip-custom-variables",
        "tooltip-ignored-ocids",
    ]
    for tooltip_id in required_tooltips:
        assert tooltip_id in html or tooltip_id in script

    assert "¿Qué significa?" in html
    assert "data-tooltip" in html or "data-tooltip" in script
    assert "title=\"" in html or "aria-label" in html


def test_frontend_labels_focus_on_commercial_value():
    html = Path("web/index.html").read_text(encoding="utf-8")

    required_labels = [
        "Prioridad de hoy",
        "¿Qué debo mirar hoy?",
        "Oportunidades prioritarias",
        "Días restantes",
        "Inteligencia competitiva",
        "Timeline del proceso",
        "Alertas comerciales",
    ]
    for label in required_labels:
        assert label in html
