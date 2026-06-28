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


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send a plain-text/HTML message via the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    return _http_post_json(url, {"chat_id": chat_id, "text": text, "parse_mode": "HTML"})


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
