"""CLI de alta manual de suscriptores de alertas LicitaScan.

MVP sin bot /start: el operador da de alta a cada cliente a mano. Flujo típico:

  1. El cliente le manda cualquier mensaje al bot de Telegram.
  2. ``python suscriptores.py chat-id`` -> muestra su chat_id (vía getUpdates).
  3. ``python suscriptores.py add --name "Constructora ABC" --chat-id 123 \
        --keywords "PUENTE,PILOTE" --negative "HOJA DE MUELLE" --min-amount 500000``
  4. ``python suscriptores.py list`` / ``disable`` / ``enable`` / ``remove``.

Las keywords se guardan en mayúsculas (consistente con seace_config y el scoring).
La misma SQLite del seguimiento (``data/seace_tracking.sqlite3``) guarda la tabla
``subscribers``; el worker lee de ahí para repartir.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from seace_tracking import Subscriber, TrackingStore

DEFAULT_DB_PATH = "data/seace_tracking.sqlite3"


def _split_keywords(raw: str | None) -> list[str]:
    return [item.strip().upper() for item in (raw or "").split(",") if item.strip()]


def _fmt_subscriber(sub: Subscriber) -> str:
    estado = "activo" if sub.active else "inactivo"
    monto = f"S/ {sub.min_amount:,.0f}" if sub.min_amount is not None else "sin mínimo"
    neg = f" | excluye: {', '.join(sub.negative_keywords)}" if sub.negative_keywords else ""
    return (
        f"[{sub.id}] {sub.name} (chat {sub.telegram_chat_id}) — {estado}\n"
        f"      keywords: {', '.join(sub.keywords) or '(ninguna)'}{neg} | {monto}"
    )


def cmd_add(store: TrackingStore, args: argparse.Namespace) -> Subscriber:
    sub = Subscriber(
        name=args.name,
        telegram_chat_id=str(args.chat_id),
        keywords=_split_keywords(args.keywords),
        negative_keywords=_split_keywords(args.negative),
        min_amount=args.min_amount,
        active=True,
    )
    saved = store.upsert_subscriber(sub)
    print("Suscriptor guardado:")
    print(_fmt_subscriber(saved))
    return saved


def cmd_list(store: TrackingStore, args: argparse.Namespace) -> list[Subscriber]:
    subs = store.list_subscribers(active_only=args.active_only)
    if not subs:
        print("No hay suscriptores." if not args.active_only else "No hay suscriptores activos.")
        return subs
    for sub in subs:
        print(_fmt_subscriber(sub))
    return subs


def cmd_enable(store: TrackingStore, args: argparse.Namespace) -> bool:
    ok = store.set_subscriber_active(str(args.chat_id), True)
    print("Suscriptor activado." if ok else f"No existe un suscriptor con chat {args.chat_id}.")
    return ok


def cmd_disable(store: TrackingStore, args: argparse.Namespace) -> bool:
    ok = store.set_subscriber_active(str(args.chat_id), False)
    print("Suscriptor desactivado." if ok else f"No existe un suscriptor con chat {args.chat_id}.")
    return ok


def cmd_remove(store: TrackingStore, args: argparse.Namespace) -> bool:
    ok = store.delete_subscriber(str(args.chat_id))
    print("Suscriptor eliminado." if ok else f"No existe un suscriptor con chat {args.chat_id}.")
    return ok


def cmd_chat_id(args: argparse.Namespace) -> int:
    """Muestra los chats recientes que escribieron al bot (para sacar el chat_id)."""
    from notificador import telegram_get_updates

    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Falta TELEGRAM_BOT_TOKEN (en el entorno o --token).")
        return 1
    chats = telegram_get_updates(token)
    if not chats:
        print("No hay mensajes recientes. Pedile al cliente que le escriba al bot y reintentá.")
        return 0
    print("Chats recientes (que le escribieron al bot):")
    for chat in chats:
        texto = f' — "{chat["text"]}"' if chat["text"] else ""
        print(f'  chat_id {chat["chat_id"]}: {chat["name"]}{texto}')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alta manual de suscriptores de alertas LicitaScan.")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Ruta SQLite del seguimiento/suscriptores")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Dar de alta (o actualizar) un suscriptor")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--chat-id", required=True)
    p_add.add_argument("--keywords", required=True, help="Lista separada por comas")
    p_add.add_argument("--negative", default="", help="Anti-diccionario, separado por comas")
    p_add.add_argument("--min-amount", type=float, default=None)

    p_list = sub.add_parser("list", help="Listar suscriptores")
    p_list.add_argument("--active-only", action="store_true")

    p_enable = sub.add_parser("enable", help="Activar un suscriptor")
    p_enable.add_argument("--chat-id", required=True)

    p_disable = sub.add_parser("disable", help="Desactivar un suscriptor")
    p_disable.add_argument("--chat-id", required=True)

    p_remove = sub.add_parser("remove", help="Eliminar un suscriptor")
    p_remove.add_argument("--chat-id", required=True)

    p_chat = sub.add_parser("chat-id", help="Descubrir el chat_id de un cliente vía getUpdates")
    p_chat.add_argument("--token", default="", help="Bot token (default: TELEGRAM_BOT_TOKEN del entorno)")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "chat-id":
        return cmd_chat_id(args)

    store = TrackingStore(args.db)
    store.initialize()
    try:
        handlers = {
            "add": cmd_add,
            "list": cmd_list,
            "enable": cmd_enable,
            "disable": cmd_disable,
            "remove": cmd_remove,
        }
        handlers[args.command](store, args)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
