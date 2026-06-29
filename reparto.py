"""Fan-out de alertas por suscriptor — el repartidor en acción.

Tras refrescar el seguimiento, el worker tiene una lista de eventos nuevos que
salen de UNA búsqueda con la unión de las keywords de todos los suscriptores. Esa
unión es plomería interna: nadie recibe la búsqueda completa. Este módulo reparte
cada evento solo a los suscriptores cuyas keywords matchean (``routing``), manda
el texto a su Telegram y reusa la ficha de la obra (capturada UNA vez) como foto.

Si no hay suscriptores activos cae al comportamiento legacy: chat global del
``.env`` (texto vía ``dispatch_events`` + ficha vía ``despachar_fichas_buena_pro``),
para no romper el setup de un solo usuario mientras no se den de alta clientes.

``repartir_eventos`` es el núcleo puro (sin red ni browser, todo inyectable);
``repartir_sync`` es el punto de entrada del worker (abre la DB, captura fichas).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable

from alerta_ficha import (
    _is_buena_pro,
    capturar_fichas_buena_pro,
    construir_caption,
    despachar_fichas_buena_pro_sync,
)
from notificador import _event_telegram_text, dispatch_events, send_telegram, send_telegram_photo
from routing import suscriptores_para_evento
from seace_tracking import OpportunitySnapshot, Subscriber, TrackingStore

logger = logging.getLogger(__name__)

SnapshotLookup = Callable[[str], "OpportunitySnapshot | None"]
SendTextFn = Callable[..., bool]
SendPhotoFn = Callable[..., bool]


def repartir_eventos(
    events: list[Any],
    subscribers: list[Subscriber],
    snapshot_for: SnapshotLookup,
    fichas: dict[str, str],
    *,
    telegram_token: str = "",
    min_score: int = 1,
    enviar_texto: SendTextFn | None = None,
    enviar_foto: SendPhotoFn | None = None,
) -> dict[str, int]:
    """Reparte ``events`` a los suscriptores que matchean. Núcleo puro y testeable.

    ``snapshot_for(ocid)`` resuelve la obra de cada evento (en el worker es
    ``store.get_snapshot``); ``fichas`` es el mapa ``ocid -> PNG`` ya capturado
    (se reusa el mismo archivo para cada chat). Devuelve conteos por canal.
    """
    token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.info("reparto: sin token de Telegram; no se envían alertas por suscriptor.")
        return {}

    # Resueltos en tiempo de llamada para que el worker (y los tests) puedan
    # sustituirlos vía monkeypatch del módulo.
    texto_fn = enviar_texto or send_telegram
    foto_fn = enviar_foto or send_telegram_photo

    # Agrupar los eventos por suscriptor: cada cliente recibe juntos solo los suyos.
    por_chat: dict[str, dict[str, Any]] = {}
    for event in events:
        ocid = str(getattr(event, "ocid", "") or "")
        snapshot = snapshot_for(ocid) if ocid else None
        if snapshot is None:
            continue
        for sub in suscriptores_para_evento(snapshot, subscribers, min_score=min_score):
            slot = por_chat.setdefault(sub.telegram_chat_id, {"sub": sub, "events": []})
            slot["events"].append(event)

    counts = {"subscribers": 0, "text": 0, "photo": 0}
    for chat_id, slot in por_chat.items():
        sus_eventos = slot["events"]
        counts["subscribers"] += 1
        for event in sus_eventos:
            # Texto a SU chat. Usamos send_telegram (no dispatch_events) para no
            # disparar el webhook global una vez por suscriptor; el formato es el
            # mismo que el dispatcher (_event_telegram_text).
            try:
                if texto_fn(token, chat_id, _event_telegram_text(event)):
                    counts["text"] += 1
            except Exception as exc:
                logger.error("reparto: error enviando texto a %s: %s", chat_id, exc)
            # Foto: buena pro con ficha capturada -> reusar el mismo PNG.
            if not _is_buena_pro(event):
                continue
            path = fichas.get(str(getattr(event, "ocid", "") or ""))
            if not path:
                continue
            try:
                if foto_fn(token, chat_id, path, caption=construir_caption(event)):
                    counts["photo"] += 1
            except Exception as exc:
                logger.error("reparto: error enviando ficha a %s: %s", chat_id, exc)
    return counts


def repartir_sync(
    events: list[Any],
    *,
    db_path: str | Path,
    output_dir: os.PathLike | str = "captures",
    headless: bool = True,
    telegram_token: str = "",
    min_score: int = 1,
) -> dict[str, int]:
    """Punto de entrada del worker: reparte ``events`` leyendo suscriptores de la DB.

    Sin suscriptores activos -> fallback al chat global del ``.env`` (texto +
    ficha), idéntico al comportamiento previo. Con suscriptores -> captura las
    fichas de buena pro una vez y enruta por cliente.
    """
    if not events:
        return {}

    store = TrackingStore(db_path)
    store.initialize()
    try:
        subscribers = store.list_subscribers(active_only=True)

        if not subscribers:
            counts = dict(dispatch_events(events))
            try:
                fichas_enviadas = despachar_fichas_buena_pro_sync(
                    events, output_dir=output_dir, headless=headless
                )
                if fichas_enviadas:
                    counts["fichas_global"] = fichas_enviadas
            except Exception as exc:
                logger.error("reparto(global): captura de ficha falló: %s", exc)
            return counts

        fichas = asyncio.run(
            capturar_fichas_buena_pro(events, output_dir=output_dir, headless=headless)
        )
        return repartir_eventos(
            events,
            subscribers,
            store.get_snapshot,
            fichas,
            telegram_token=telegram_token,
            min_score=min_score,
        )
    finally:
        store.close()
