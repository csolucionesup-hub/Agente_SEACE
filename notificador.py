"""Dispatcher de alertas para LicitaScan.

Envía eventos comerciales a canales configurados:
  - Telegram: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
  - Webhook genérico: LICITASCAN_WEBHOOK_URL

Llamar desde worker.py después de sync_ocids() para despachar los eventos nuevos.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🔵", "info": "🔵"}


def _http_post_json(url: str, payload: dict[str, Any], timeout: float = 10.0) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        import httpx
        response = httpx.post(url, content=data, headers={"Content-Type": "application/json"}, timeout=timeout)
        return response.is_success
    except ImportError:
        pass
    try:
        import urllib.request
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception as exc:
        logger.warning("HTTP POST to %s failed: %s", url, exc)
        return False
    return False


def _http_get_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """GET + parse JSON, con httpx si está disponible y urllib de fallback."""
    try:
        import httpx
        response = httpx.get(url, timeout=timeout)
        return response.json() if response.is_success else {}
    except ImportError:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status >= 400:
                return {}
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("HTTP GET to %s failed: %s", url, exc)
        return {}


def telegram_get_updates(token: str, *, timeout: float = 10.0, fetch: Any = None) -> list[dict[str, Any]]:
    """Lista los chats recientes que le escribieron al bot, para descubrir su ``chat_id``.

    El cliente le manda cualquier mensaje al bot; corriendo esto se obtiene su
    ``chat_id`` (que después se da de alta como suscriptor). Devuelve
    ``[{chat_id, name, text}]`` deduplicado por chat (último mensaje gana). ``fetch``
    es inyectable (recibe ``url`` y devuelve el JSON) para testear sin red.
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    data = _http_get_json(url, timeout) if fetch is None else fetch(url)
    chats: dict[str, dict[str, Any]] = {}
    for update in (data or {}).get("result") or []:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        name = (
            chat.get("title")
            or " ".join(part for part in [chat.get("first_name"), chat.get("last_name")] if part)
            or chat.get("username")
            or ""
        )
        chats[str(chat_id)] = {
            "chat_id": str(chat_id),
            "name": str(name),
            "text": str(message.get("text") or ""),
        }
    return list(chats.values())


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send a plain-text/HTML message via the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _http_post_json(url, {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


def send_telegram_photo(token: str, chat_id: str, photo_path: str, caption: str = "", timeout: float = 60.0) -> bool:
    """Send a local image (e.g. the SEACE ficha screenshot) via sendPhoto.

    Usa multipart/form-data para subir el PNG. Caption admite HTML (link al
    expediente, ganador, monto). Pensado para la alerta de buena pro, donde la
    captura full-page de la ficha aporta el cronograma y el look oficial.
    """
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        import httpx
        with open(photo_path, "rb") as handle:
            response = httpx.post(
                url,
                data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
                files={"photo": handle},
                timeout=timeout,
            )
        return response.is_success
    except Exception as exc:
        logger.error("Telegram sendPhoto failed: %s", exc)
        return False


def send_webhook(webhook_url: str, payload: dict[str, Any]) -> bool:
    """POST the event payload to an arbitrary webhook URL."""
    return _http_post_json(webhook_url, payload)


def _event_telegram_text(event: Any) -> str:
    severity = str(getattr(event, "severity", "") or "")
    emoji = SEVERITY_EMOJI.get(severity, "🔵")
    title = str(getattr(event, "title", "") or "")
    message = str(getattr(event, "message", "") or "")
    occurred = str(getattr(event, "occurred_at", "") or "")
    text = f"{emoji} <b>{title}</b>\n{message}"
    if occurred:
        text += f"\n<i>{occurred[:19].replace('T', ' ')}</i>"
    payload = getattr(event, "payload", None)
    source_url = str((payload or {}).get("source_url") or "").strip() if isinstance(payload, dict) else ""
    if source_url:
        text += f'\n🔗 <a href="{source_url}">Ver expediente</a>'
    return text


def _event_to_dict(event: Any) -> dict[str, Any]:
    return {
        "ocid": str(getattr(event, "ocid", "") or ""),
        "event_type": str(getattr(event, "event_type", "") or ""),
        "title": str(getattr(event, "title", "") or ""),
        "message": str(getattr(event, "message", "") or ""),
        "severity": str(getattr(event, "severity", "") or ""),
        "occurred_at": str(getattr(event, "occurred_at", "") or ""),
    }


def dispatch_events(
    events: list[Any],
    *,
    telegram_token: str = "",
    telegram_chat_id: str = "",
    webhook_url: str = "",
    only_severities: set[str] | None = None,
) -> dict[str, int]:
    """Send new commercial events to all configured channels.

    Returns a dict mapping channel name -> number of events dispatched.
    ``only_severities`` filters events before dispatch (default: all).
    """
    if not events:
        return {}

    token = telegram_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    hook_url = webhook_url or os.getenv("LICITASCAN_WEBHOOK_URL", "")

    # Apply severity filter if requested
    if only_severities:
        events = [e for e in events if str(getattr(e, "severity", "") or "") in only_severities]
    if not events:
        return {}

    counts: dict[str, int] = {}

    if token and chat_id:
        sent = 0
        for event in events:
            try:
                if send_telegram(token, chat_id, _event_telegram_text(event)):
                    sent += 1
                    logger.info("Telegram: sent event '%s' for %s", getattr(event, "event_type", ""), getattr(event, "ocid", ""))
                else:
                    logger.warning("Telegram: failed to send event for %s", getattr(event, "ocid", ""))
            except Exception as exc:
                logger.error("Telegram dispatch error: %s", exc)
        counts["telegram"] = sent

    if hook_url:
        payload = {
            "source": "licitascan",
            "count": len(events),
            "events": [_event_to_dict(e) for e in events],
        }
        try:
            ok = send_webhook(hook_url, payload)
            counts["webhook"] = len(events) if ok else 0
            if not ok:
                logger.warning("Webhook dispatch failed: %s", hook_url)
        except Exception as exc:
            logger.error("Webhook dispatch error: %s", exc)
            counts["webhook"] = 0

    return counts
