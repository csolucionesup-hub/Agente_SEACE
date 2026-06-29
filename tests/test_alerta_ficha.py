"""Tests del puente buena pro -> captura de ficha -> Telegram (alerta_ficha).

La captura (Playwright) y el envío (Bot API) se inyectan como fakes, así que estos tests no
tocan red ni navegador.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from alerta_ficha import construir_caption, despachar_fichas_buena_pro


@dataclass
class FakeEvent:
    event_type: str
    title: str = "Buena pro otorgada"
    payload: dict = field(default_factory=dict)


def _buena_pro(nomen="LP-ABR-2-2025-CS-MDPP-1", **extra) -> FakeEvent:
    payload = {
        "process_code": nomen,
        "entity_name": "MUNICIPALIDAD DISTRITAL DE PUENTE PIEDRA",
        "description": "REPARACION DE PISTA Y VEREDA EN AV SAN JUAN",
        "winner_name": "CONSTRUCTORA XYZ SAC",
        "awarded_amount": 1234567.5,
        "source_url": "https://prodapp2.seace.gob.pe/x",
    }
    payload.update(extra)
    return FakeEvent(event_type="buena_pro_otorgada", payload=payload)


def test_caption_incluye_datos_clave():
    cap = construir_caption(_buena_pro())
    assert "LP-ABR-2-2025-CS-MDPP-1" in cap
    assert "PUENTE PIEDRA" in cap
    assert "CONSTRUCTORA XYZ SAC" in cap
    assert "S/ 1,234,567.50" in cap
    assert "Ver expediente" in cap


def test_caption_tolera_payload_incompleto():
    ev = FakeEvent(event_type="buena_pro_otorgada", payload={"process_code": "X-1"})
    cap = construir_caption(ev)
    assert "X-1" in cap
    assert "proveedor por confirmar" in cap  # fallback de ganador


def test_solo_procesa_eventos_de_buena_pro():
    calls = []

    async def fake_capturar(**kwargs):
        calls.append(kwargs)
        return "/tmp/ficha.png"

    def fake_enviar(token, chat_id, path, caption=""):
        return True

    events = [
        FakeEvent(event_type="nueva_oportunidad", payload={"process_code": "A-1"}),
        _buena_pro("LP-1"),
        FakeEvent(event_type="contrato_suscrito", payload={"process_code": "B-1"}),
    ]
    enviadas = asyncio.run(
        despachar_fichas_buena_pro(
            events, telegram_token="t", telegram_chat_id="c",
            capturar=fake_capturar, enviar_foto=fake_enviar,
        )
    )
    assert enviadas == 1
    assert len(calls) == 1
    assert calls[0]["nomenclatura"] == "LP-1"


def test_pasa_nomenclatura_descripcion_y_entidad_a_la_captura():
    received = {}

    async def fake_capturar(**kwargs):
        received.update(kwargs)
        return "/tmp/ficha.png"

    captions = []

    def fake_enviar(token, chat_id, path, caption=""):
        captions.append((path, caption))
        return True

    asyncio.run(
        despachar_fichas_buena_pro(
            [_buena_pro("LP-ABR-2-2025-CS-MDPP-1")],
            telegram_token="t", telegram_chat_id="c",
            capturar=fake_capturar, enviar_foto=fake_enviar,
        )
    )
    assert received["nomenclatura"] == "LP-ABR-2-2025-CS-MDPP-1"
    assert "REPARACION DE PISTA" in received["descripcion"]
    assert "PUENTE PIEDRA" in received["entity_name"]
    assert captions and captions[0][0] == "/tmp/ficha.png"


def test_si_no_hay_captura_no_se_envia():
    async def fake_capturar(**kwargs):
        return None  # captura falló

    sent = []

    def fake_enviar(token, chat_id, path, caption=""):
        sent.append(path)
        return True

    enviadas = asyncio.run(
        despachar_fichas_buena_pro(
            [_buena_pro()], telegram_token="t", telegram_chat_id="c",
            capturar=fake_capturar, enviar_foto=fake_enviar,
        )
    )
    assert enviadas == 0
    assert sent == []


def test_evento_sin_process_code_se_omite():
    calls = []

    async def fake_capturar(**kwargs):
        calls.append(kwargs)
        return "/tmp/ficha.png"

    enviadas = asyncio.run(
        despachar_fichas_buena_pro(
            [_buena_pro(nomen="")], telegram_token="t", telegram_chat_id="c",
            capturar=fake_capturar, enviar_foto=lambda *a, **k: True,
        )
    )
    assert enviadas == 0
    assert calls == []


def test_sin_credenciales_no_hace_nada(monkeypatch):
    # El .env del proyecto puede poblar estas vars; las limpiamos para probar el caso real.
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    calls = []

    async def fake_capturar(**kwargs):
        calls.append(kwargs)
        return "/tmp/ficha.png"

    enviadas = asyncio.run(
        despachar_fichas_buena_pro(
            [_buena_pro()], telegram_token="", telegram_chat_id="",
            capturar=fake_capturar, enviar_foto=lambda *a, **k: True,
        )
    )
    assert enviadas == 0
    assert calls == []
