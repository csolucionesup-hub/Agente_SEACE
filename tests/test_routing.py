from routing import evaluar_obra, suscriptores_para_evento
from seace_tracking import OpportunitySnapshot, Subscriber


def obra(description="Construccion de puente vehicular", amount=1000000.0, awarded_amount=None):
    return OpportunitySnapshot(
        ocid="ocds-obra-1",
        process_code="LP-1-2026-MTC-1",
        entity_name="MTC",
        description=description,
        amount=amount,
        currency="PEN",
        tender_status="active",
        stage="buena_pro_otorgada",
        next_critical_date="",
        winner_name="Constructora X",
        winner_ruc="",
        awarded_amount=awarded_amount,
        award_date="",
        contract_id="",
        contract_date_signed="",
        contract_start_date="",
        contract_end_date="",
        outcome="adjudicado",
        raw={},
    )


def sub(chat_id, keywords, negative=None, min_amount=None, active=True, name="Cliente"):
    return Subscriber(
        name=name,
        telegram_chat_id=chat_id,
        keywords=keywords,
        negative_keywords=negative or [],
        min_amount=min_amount,
        active=active,
    )


def test_matches_subscriber_with_matching_keyword():
    matches = suscriptores_para_evento(obra(), [sub("100", ["PUENTE"])])
    assert [s.telegram_chat_id for s in matches] == ["100"]


def test_excludes_subscriber_without_matching_keyword():
    matches = suscriptores_para_evento(obra(), [sub("100", ["CARRETERA", "MUELLE"])])
    assert matches == []


def test_routes_only_to_matching_subscribers_in_a_pool():
    subs = [
        sub("puente", ["PUENTE"]),
        sub("carretera", ["CARRETERA"]),
        sub("pilote", ["PILOTE", "PUENTE"]),
    ]
    matches = suscriptores_para_evento(obra(), subs)
    assert {s.telegram_chat_id for s in matches} == {"puente", "pilote"}


def test_inactive_subscriber_is_skipped_even_if_keywords_match():
    matches = suscriptores_para_evento(obra(), [sub("100", ["PUENTE"], active=False)])
    assert matches == []


def test_min_amount_excludes_obra_below_threshold():
    matches = suscriptores_para_evento(obra(amount=200000.0), [sub("100", ["PUENTE"], min_amount=500000.0)])
    assert matches == []


def test_min_amount_includes_obra_at_or_above_threshold():
    matches = suscriptores_para_evento(obra(amount=800000.0), [sub("100", ["PUENTE"], min_amount=500000.0)])
    assert [s.telegram_chat_id for s in matches] == ["100"]


def test_min_amount_uses_awarded_amount_when_referential_missing():
    obra_sin_referencial = obra(amount=None, awarded_amount=900000.0)
    assert suscriptores_para_evento(obra_sin_referencial, [sub("100", ["PUENTE"], min_amount=500000.0)])
    obra_baja = obra(amount=None, awarded_amount=100000.0)
    assert suscriptores_para_evento(obra_baja, [sub("100", ["PUENTE"], min_amount=500000.0)]) == []


def test_unknown_amount_is_not_dropped_by_min_amount():
    obra_sin_monto = obra(amount=None, awarded_amount=None)
    matches = suscriptores_para_evento(obra_sin_monto, [sub("100", ["PUENTE"], min_amount=500000.0)])
    assert [s.telegram_chat_id for s in matches] == ["100"]


def test_anti_dictionary_demotes_noise_out_of_routing():
    # Caso ruido: una obra de repuesto de camión ("hoja de muelle"/"ballesta")
    # que jala la keyword MUELLE. Con dos negativos el score cae a 0 y no rutea.
    ruido = obra(description="Reparacion de hoja de muelle y ballesta del camion")
    sin_anti = sub("sin", ["MUELLE"])
    con_anti = sub("con", ["MUELLE"], negative=["HOJA DE MUELLE", "BALLESTA"])
    assert suscriptores_para_evento(ruido, [sin_anti]) == [sin_anti]
    assert suscriptores_para_evento(ruido, [con_anti]) == []


def test_evaluar_obra_reports_score_and_matched_keywords():
    matches = evaluar_obra(obra(), [sub("100", ["PUENTE", "CARRETERA"])])
    assert len(matches) == 1
    match = matches[0]
    assert match.subscriber.telegram_chat_id == "100"
    assert match.relevance_score > 0
    assert match.matched_keywords == ["PUENTE"]
