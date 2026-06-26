from datetime import date

from seace_commercial_scoring import enrich_opportunity


def base_opportunity(**overrides):
    data = {
        "ocid": "ocds-dgv273-seacev3-test",
        "process_code": "AS-SM-1-2026",
        "entity_name": "Municipalidad Distrital",
        "description": "Construcción de puente vehicular",
        "amount": 250000.0,
        "currency": "PEN",
        "stage": "convocado",
        "outcome": "activo",
        "next_critical_date": "2026-06-10T15:00:00-05:00",
        "winner_name": "",
        "winner_ruc": "",
        "awarded_amount": None,
        "award_date": "",
        "contract_id": "",
        "contract_date_signed": "",
    }
    data.update(overrides)
    return data


def test_enrich_opportunity_prioritizes_contract_and_winner_intelligence():
    enriched = enrich_opportunity(
        base_opportunity(
            stage="contrato_suscrito",
            outcome="contratado",
            amount=950000.0,
            winner_name="CONSORCIO PUENTE NORTE",
            winner_ruc="20600000001",
            awarded_amount=910000.0,
            contract_date_signed="2026-06-05T00:00:00-05:00",
        ),
        today=date(2026, 6, 6),
    )

    assert enriched["commercial_score"] >= 85
    assert enriched["priority_label"] == "Alta"
    assert enriched["urgency_label"] == "Ganador/contrato detectado"
    assert enriched["recommended_action"] == "Registrar ganador, monto adjudicado y alimentar inteligencia competitiva"
    assert enriched["commercial_reasons"][:2] == ["Contrato suscrito", "Ganador identificado"]


def test_enrich_opportunity_flags_critical_date_today_as_high_priority():
    enriched = enrich_opportunity(
        base_opportunity(next_critical_date="2026-06-06T23:59:00-05:00", amount=120000.0),
        today=date(2026, 6, 6),
    )

    assert enriched["days_to_critical_date"] == 0
    assert enriched["urgency_level"] == "high"
    assert enriched["urgency_label"] == "Vence hoy"
    assert enriched["priority_label"] == "Alta"
    assert "Fecha crítica vence hoy" in enriched["commercial_reasons"]


def test_enrich_opportunity_scores_large_active_opportunity_as_medium():
    enriched = enrich_opportunity(
        base_opportunity(next_critical_date="2026-06-25", amount=1_200_000.0),
        today=date(2026, 6, 6),
    )

    assert enriched["days_to_critical_date"] == 19
    assert enriched["urgency_level"] == "low"
    assert enriched["priority_label"] == "Media"
    assert enriched["recommended_action"] == "Calificar encaje técnico y decidir si entra a seguimiento comercial"
    assert "Monto referencial alto" in enriched["commercial_reasons"]


def test_enrich_opportunity_marks_failed_process_as_wait_for_restart():
    enriched = enrich_opportunity(
        base_opportunity(stage="desierto", outcome="desierto", next_critical_date="", amount=800000.0),
        today=date(2026, 6, 6),
    )

    assert enriched["priority_label"] == "Baja"
    assert enriched["urgency_level"] == "inactive"
    assert enriched["urgency_label"] == "Proceso caído"
    assert enriched["recommended_action"] == "Esperar reinicio o nueva convocatoria; no invertir gestión comercial ahora"
    assert enriched["commercial_reasons"] == ["Proceso desierto"]
