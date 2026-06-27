from dataclasses import replace

from seace_tracking import OpportunitySnapshot, diff_snapshots


def snapshot(**overrides):
    base = OpportunitySnapshot(
        ocid="ocds-test-1",
        process_code="LP-1-2026-MTC-1",
        entity_name="MTC",
        description="Construcción de puente",
        amount=1000000.0,
        currency="PEN",
        tender_status="active",
        stage="convocado",
        next_critical_date="2026-06-20T00:00:00-05:00",
        winner_name="",
        winner_ruc="",
        awarded_amount=None,
        award_date="",
        contract_id="",
        contract_date_signed="",
        contract_start_date="",
        contract_end_date="",
        outcome="activo",
        raw={},
    )
    return replace(base, **overrides)


def test_diff_none_to_snapshot_creates_new_opportunity_event():
    events = diff_snapshots(None, snapshot())

    assert len(events) == 1
    assert events[0].event_type == "nueva_oportunidad"
    assert events[0].severity == "medium"
    assert "MTC" in events[0].message


def test_diff_award_transition_creates_buena_pro_event():
    before = snapshot()
    after = snapshot(
        stage="buena_pro_otorgada",
        outcome="adjudicado",
        winner_name="CONSTRUCTORA X SAC",
        winner_ruc="20123456789",
        awarded_amount=900000.0,
        award_date="2026-06-15T00:00:00-05:00",
    )

    events = diff_snapshots(before, after)

    assert [event.event_type for event in events] == ["buena_pro_otorgada"]
    assert events[0].severity == "high"
    assert "CONSTRUCTORA X SAC" in events[0].message
    assert events[0].payload["awarded_amount"] == 900000.0


def test_diff_contract_transition_creates_contract_event():
    before = snapshot(stage="buena_pro_otorgada", outcome="adjudicado", winner_name="CONSTRUCTORA X SAC")
    after = snapshot(
        stage="contrato_suscrito",
        outcome="contratado",
        winner_name="CONSTRUCTORA X SAC",
        contract_id="contract-1",
        contract_date_signed="2026-06-25T00:00:00-05:00",
    )

    events = diff_snapshots(before, after)

    assert [event.event_type for event in events] == ["contrato_suscrito"]
    assert events[0].severity == "high"
    assert "contract-1" in events[0].message


def test_diff_terminal_fall_creates_process_fell_event():
    before = snapshot()
    after = snapshot(stage="desierto", outcome="desierto", tender_status="unsuccessful")

    events = diff_snapshots(before, after)

    assert [event.event_type for event in events] == ["proceso_caido"]
    assert events[0].severity == "high"
    assert "desierto" in events[0].message.lower()


def test_diff_next_critical_date_change_creates_calendar_event():
    before = snapshot(next_critical_date="2026-06-20T00:00:00-05:00")
    after = snapshot(next_critical_date="2026-06-25T00:00:00-05:00")

    events = diff_snapshots(before, after)

    assert [event.event_type for event in events] == ["fecha_critica_actualizada"]
    assert events[0].severity == "medium"
    assert "2026-06-25" in events[0].message
