"""Puente: evento de buena pro -> captura de la ficha EXACTA -> foto a Telegram.

Toma los eventos `buena_pro_otorgada` del tracking, captura la ficha de la obra exacta por su
nomenclatura (`agente_seace.capturar_obra_standalone`) y la envía como foto a Telegram con un
caption rico (nomenclatura, entidad, ganador, monto, link al expediente).

Se mantiene separado de `notificador.py` para no arrastrar Playwright a cada import del
dispatcher. El worker llama `despachar_fichas_buena_pro_sync(eventos, ...)` tras `dispatch_events`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

CaptureFn = Callable[..., Awaitable["str | None"]]
SendPhotoFn = Callable[..., bool]


def _fmt_monto(amount: Any) -> str:
    try:
        return f"S/ {float(amount):,.2f}"
    except (TypeError, ValueError):
        return ""


def _is_buena_pro(event: Any) -> bool:
    return str(getattr(event, "event_type", "") or "") == "buena_pro_otorgada"


def construir_caption(event: Any) -> str:
    """Caption HTML para la foto de la ficha (Telegram admite un subconjunto de HTML)."""
    payload = getattr(event, "payload", None) or {}
    nomen = str(payload.get("process_code") or "")
    entidad = str(payload.get("entity_name") or "")
    ganador = str(payload.get("winner_name") or "proveedor por confirmar")
    monto = _fmt_monto(payload.get("awarded_amount"))
    src = str(payload.get("source_url") or "").strip()
    titulo = str(getattr(event, "title", "") or "Buena pro otorgada")

    lines = [f"🔴 <b>{titulo}</b>"]
    if nomen:
        lines.append(f"📋 {nomen}")
    if entidad:
        lines.append(f"🏛️ {entidad}")
    lines.append(f"🏆 {ganador}")
    if monto:
        lines.append(f"💰 {monto}")
    if src:
        lines.append(f'🔗 <a href="{src}">Ver expediente</a>')
    return "\n".join(lines)


async def despachar_fichas_buena_pro(
    events: list[Any],
    *,
    telegram_token: str = "",
    telegram_chat_id: str = "",
    output_dir: os.PathLike | str = ".",
    headless: bool = True,
    capturar: CaptureFn | None = None,
    enviar_foto: SendPhotoFn | None = None,
) -> int:
    """Por cada evento de buena pro: captura la ficha exacta y la manda a Telegram.

    Devuelve cuántas fichas se enviaron con éxito. `capturar`/`enviar_foto` son inyectables
    (por defecto usan Playwright + la Bot API) para poder testear sin red ni navegador.
    """
    token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not (token and chat_id):
        logger.info("alerta_ficha: sin credenciales Telegram; se omite la captura de ficha.")
        return 0

    buena_pro = [e for e in events if _is_buena_pro(e)]
    if not buena_pro:
        return 0

    if capturar is None:
        from agente_seace import capturar_obra_standalone as capturar  # import perezoso (Playwright)
    if enviar_foto is None:
        from notificador import send_telegram_photo as enviar_foto

    enviadas = 0
    for event in buena_pro:
        payload = getattr(event, "payload", None) or {}
        nomen = str(payload.get("process_code") or "").strip()
        desc = str(payload.get("description") or "").strip()
        if not nomen:
            logger.warning("alerta_ficha: evento de buena pro sin process_code; se omite la ficha.")
            continue
        try:
            path = await capturar(
                nomenclatura=nomen,
                descripcion=desc,
                entity_name=str(payload.get("entity_name") or ""),
                output_dir=output_dir,
                headless=headless,
            )
        except Exception as exc:
            logger.error("alerta_ficha: fallo capturando ficha de %s: %s", nomen, exc)
            path = None
        if not path:
            logger.warning(
                "alerta_ficha: no se capturó ficha para %s (la alerta de texto sigue vía dispatch_events).",
                nomen,
            )
            continue
        try:
            if enviar_foto(token, chat_id, path, caption=construir_caption(event)):
                enviadas += 1
                logger.info("alerta_ficha: ficha de %s enviada a Telegram.", nomen)
            else:
                logger.warning("alerta_ficha: Telegram rechazó la ficha de %s.", nomen)
        except Exception as exc:
            logger.error("alerta_ficha: error enviando ficha de %s: %s", nomen, exc)
    return enviadas


def despachar_fichas_buena_pro_sync(events: list[Any], **kwargs: Any) -> int:
    """Envoltorio síncrono para el worker (que corre en hilos / cron, fuera de un event loop)."""
    return asyncio.run(despachar_fichas_buena_pro(events, **kwargs))
