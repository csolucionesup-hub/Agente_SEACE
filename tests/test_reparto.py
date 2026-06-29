"""Tests del repartidor de alertas por suscriptor (reparto.py).

El núcleo (repartir_eventos) y la captura (capturar_fichas_buena_pro) se prueban
con fakes inyectados: sin red, sin navegador, sin Telegram.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import reparto
from alerta_ficha import capturar_fichas_buena_pro
from reparto import repartir_eventos, repartir_sync
from seace_tracking import OpportunitySnapshot, Subscriber, TrackingStore


@dataclass
class FakeEvent:
    ocid: str
    event_type: str = "buena_pro_otorgada"
    title: str = "Buena pro otorgada"
    message: str = "msg"
    severity: str = "high"
    occurred_at: str = "2026-06-10T10:00:00"
    payload: dict = field(default_factory=dict)


def snapshot(ocid, description, amount=1000000.0):
    return OpportunitySnapshot(
        ocid=ocid,
        process_code=f"LP-{ocid}",
        entity_name="MTC",
        description=description,
        amount=amount,
        currency="PEN",
        tender_status="active",
        stage="buena_pro_otorgada",
        next_critical_date="",
        winner_name="X",
        winner_ruc="",
        awarded_amount=amount,
        award_date="",
        contract_id="",
        contract_date_signed="",
        contract_start_date="",
        contract_end_date="",
        outcome="adjudicado",
        raw={},
    )


def sub(chat, keywords, negative=None, min_amount=None, active=True):
    return Subscriber(
        name="cliente",
        telegram_chat_id=chat,
        keywords=keywords,
        negative_keywords=negative or [],
        min_amount=min_amount,
        active=active,
    )


def buena_pro(ocid, process_code="LP-1", description="puente", message="msg"):
    return FakeEvent(
        ocid=ocid,
        event_type="buena_pro_otorgada",
        message=message,
        payload={
            "process_code": process_code,
            "description": description,
            "entity_name": "MTC",
            "winner_name": "X",
            "awarded_amount": 1000.0,
        },
    )


# --- núcleo: repartir_eventos ---------------------------------------------


def test_ficha_se_captura_una_vez_y_se_reenvia_a_cada_chat():
    ev = buena_pro("ocds-1", description="puente")
    snaps = {"ocds-1": snapshot("ocds-1", "construccion de puente")}
    subs = [sub("A", ["PUENTE"]), sub("B", ["PUENTE"])]

    textos, fotos = [], []

    def texto(token, chat, text):
        textos.append(chat)
        return True

    def foto(token, chat, path, caption=""):
        fotos.append((chat, path))
        return True

    counts = repartir_eventos(
        [ev], subs, snaps.get, {"ocds-1": "/tmp/ficha.png"},
        telegram_token="t", enviar_texto=texto, enviar_foto=foto,
    )

    assert counts == {"subscribers": 2, "text": 2, "photo": 2}
    assert sorted(textos) == ["A", "B"]
    # el mismo PNG reenviado a ambos chats (captura 1 vez, reenvía N)
    assert sorted(fotos) == [("A", "/tmp/ficha.png"), ("B", "/tmp/ficha.png")]


def test_cada_chat_recibe_solo_lo_suyo():
    ev_p = buena_pro("ocds-p", description="puente", message="ES-PUENTE")
    ev_c = buena_pro("ocds-c", description="carretera", message="ES-CARRETERA")
    snaps = {
        "ocds-p": snapshot("ocds-p", "construccion de puente vehicular"),
        "ocds-c": snapshot("ocds-c", "mejoramiento de carretera"),
    }
    subs = [sub("A", ["PUENTE"]), sub("B", ["CARRETERA"])]

    recibido: dict[str, list[str]] = {}

    def texto(token, chat, text):
        recibido.setdefault(chat, []).append(text)
        return True

    repartir_eventos(
        [ev_p, ev_c], subs, snaps.get, {},
        telegram_token="t", enviar_texto=texto, enviar_foto=lambda *a, **k: True,
    )

    assert set(recibido) == {"A", "B"}
    assert any("PUENTE" in t for t in recibido["A"]) and len(recibido["A"]) == 1
    assert any("CARRETERA" in t for t in recibido["B"]) and len(recibido["B"]) == 1


def test_evento_no_buena_pro_manda_texto_sin_foto():
    ev = FakeEvent(ocid="ocds-1", event_type="nueva_oportunidad", payload={})
    snaps = {"ocds-1": snapshot("ocds-1", "construccion de puente")}

    fotos = []
    counts = repartir_eventos(
        [ev], [sub("A", ["PUENTE"])], snaps.get, {"ocds-1": "/tmp/ficha.png"},
        telegram_token="t",
        enviar_texto=lambda *a, **k: True,
        enviar_foto=lambda *a, **k: fotos.append(1) or True,
    )

    assert counts["text"] == 1 and counts["photo"] == 0
    assert fotos == []


def test_sub_sin_keyword_que_matchea_no_recibe():
    counts = repartir_eventos(
        [buena_pro("ocds-1", description="puente")],
        [sub("A", ["MUELLE"])],
        {"ocds-1": snapshot("ocds-1", "construccion de puente")}.get,
        {}, telegram_token="t",
        enviar_texto=lambda *a, **k: True, enviar_foto=lambda *a, **k: True,
    )
    assert counts["subscribers"] == 0


def test_sin_token_no_envia_nada(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    enviados = []
    counts = repartir_eventos(
        [buena_pro("ocds-1")], [sub("A", ["PUENTE"])],
        {"ocds-1": snapshot("ocds-1", "puente")}.get, {},
        telegram_token="",
        enviar_texto=lambda *a, **k: enviados.append(1) or True,
        enviar_foto=lambda *a, **k: True,
    )
    assert counts == {}
    assert enviados == []


def test_evento_sin_snapshot_se_ignora():
    # ocid sin snapshot conocido -> no se puede rutear; no rompe.
    counts = repartir_eventos(
        [buena_pro("ocds-desconocido")], [sub("A", ["PUENTE"])],
        lambda ocid: None, {}, telegram_token="t",
        enviar_texto=lambda *a, **k: True, enviar_foto=lambda *a, **k: True,
    )
    assert counts == {"subscribers": 0, "text": 0, "photo": 0}


# --- captura: capturar_fichas_buena_pro -----------------------------------


def test_capturar_fichas_una_sola_vez_por_ocid():
    calls = []

    async def fake_capturar(**kwargs):
        calls.append(kwargs["nomenclatura"])
        return f"/tmp/{kwargs['nomenclatura']}.png"

    events = [
        buena_pro("ocds-1", "LP-1"),
        buena_pro("ocds-1", "LP-1"),  # mismo ocid -> no recaptura
        buena_pro("ocds-2", "LP-2"),
        FakeEvent(ocid="ocds-3", event_type="nueva_oportunidad", payload={"process_code": "LP-3"}),
    ]

    fichas = asyncio.run(capturar_fichas_buena_pro(events, capturar=fake_capturar))

    assert fichas == {"ocds-1": "/tmp/LP-1.png", "ocds-2": "/tmp/LP-2.png"}
    assert calls == ["LP-1", "LP-2"]  # ocds-1 una vez, nueva_oportunidad ignorada


def test_capturar_omite_buena_pro_sin_process_code():
    async def fake_capturar(**kwargs):
        return "/tmp/x.png"

    ev = FakeEvent(ocid="ocds-1", event_type="buena_pro_otorgada", payload={})
    fichas = asyncio.run(capturar_fichas_buena_pro([ev], capturar=fake_capturar))
    assert fichas == {}


# --- orquestación: repartir_sync ------------------------------------------


def test_repartir_sync_sin_suscriptores_cae_al_chat_global(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite3"
    store = TrackingStore(db)
    store.initialize()
    store.close()  # tabla vacía: sin suscriptores activos

    called = {}

    def fake_dispatch(events):
        called["dispatch"] = len(events)
        return {"telegram": len(events)}

    def fake_fichas_global(events, **kwargs):
        called["fichas"] = 1
        return 1

    monkeypatch.setattr(reparto, "dispatch_events", fake_dispatch)
    monkeypatch.setattr(reparto, "despachar_fichas_buena_pro_sync", fake_fichas_global)

    counts = repartir_sync([buena_pro("ocds-1")], db_path=db)

    assert called == {"dispatch": 1, "fichas": 1}
    assert counts == {"telegram": 1, "fichas_global": 1}


def test_repartir_sync_con_suscriptores_captura_y_reparte(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite3"
    store = TrackingStore(db)
    store.initialize()
    store.upsert_subscriber(sub("A", ["PUENTE"]))
    store.upsert_snapshot(snapshot("ocds-1", "construccion de puente"))
    store.close()

    async def fake_capturar(events, **kwargs):
        return {"ocds-1": "/tmp/ficha.png"}

    sent_text, sent_photo = [], []
    monkeypatch.setattr(reparto, "capturar_fichas_buena_pro", fake_capturar)
    monkeypatch.setattr(reparto, "send_telegram", lambda token, chat, text: sent_text.append(chat) or True)
    monkeypatch.setattr(
        reparto, "send_telegram_photo",
        lambda token, chat, path, caption="": sent_photo.append((chat, path)) or True,
    )

    counts = repartir_sync([buena_pro("ocds-1")], db_path=db, telegram_token="t")

    assert counts == {"subscribers": 1, "text": 1, "photo": 1}
    assert sent_text == ["A"]
    assert sent_photo == [("A", "/tmp/ficha.png")]
