"""Tests del CLI de suscriptores y del helper getUpdates (descubrir chat_id)."""

from __future__ import annotations

import suscriptores
from notificador import telegram_get_updates
from seace_tracking import TrackingStore
from suscriptores import build_parser, cmd_add


def _store(tmp_path):
    store = TrackingStore(tmp_path / "t.sqlite3")
    store.initialize()
    return store


def test_telegram_get_updates_parses_and_dedups():
    fake_json = {
        "result": [
            {"message": {"text": "hola", "chat": {"id": 111, "first_name": "Ana", "last_name": "Pérez"}}},
            {"message": {"text": "segundo", "chat": {"id": 111, "first_name": "Ana", "last_name": "Pérez"}}},
            {"message": {"text": "grupo", "chat": {"id": -200, "title": "Constructora ABC"}}},
        ]
    }
    chats = telegram_get_updates("tok", fetch=lambda url: fake_json)

    by_id = {c["chat_id"]: c for c in chats}
    assert len(chats) == 2  # 111 deduplicado
    assert by_id["111"]["name"] == "Ana Pérez"
    assert by_id["111"]["text"] == "segundo"  # último mensaje gana
    assert by_id["-200"]["name"] == "Constructora ABC"


def test_telegram_get_updates_vacio():
    assert telegram_get_updates("tok", fetch=lambda url: {}) == []


def test_cmd_add_crea_suscriptor_con_keywords_en_mayuscula(tmp_path):
    store = _store(tmp_path)
    args = build_parser().parse_args(
        ["add", "--name", "ABC", "--chat-id", "123",
         "--keywords", "puente, pilote", "--negative", "hoja de muelle", "--min-amount", "500000"]
    )

    saved = cmd_add(store, args)

    assert saved.keywords == ["PUENTE", "PILOTE"]
    assert saved.negative_keywords == ["HOJA DE MUELLE"]
    assert saved.min_amount == 500000.0
    assert store.get_subscriber("123") is not None
    store.close()


def test_main_add_then_list(tmp_path, capsys):
    db = str(tmp_path / "t.sqlite3")
    assert suscriptores.main(["--db", db, "add", "--name", "ABC", "--chat-id", "123", "--keywords", "PUENTE"]) == 0
    capsys.readouterr()

    assert suscriptores.main(["--db", db, "list"]) == 0
    out = capsys.readouterr().out
    assert "ABC" in out and "123" in out


def test_main_disable_and_remove(tmp_path):
    db = str(tmp_path / "t.sqlite3")
    suscriptores.main(["--db", db, "add", "--name", "ABC", "--chat-id", "123", "--keywords", "PUENTE"])

    suscriptores.main(["--db", db, "disable", "--chat-id", "123"])
    store = TrackingStore(db)
    store.initialize()
    assert store.get_subscriber("123").active is False
    store.close()

    suscriptores.main(["--db", db, "remove", "--chat-id", "123"])
    store = TrackingStore(db)
    store.initialize()
    assert store.get_subscriber("123") is None
    store.close()


def test_cmd_chat_id_sin_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    args = build_parser().parse_args(["chat-id"])
    assert suscriptores.cmd_chat_id(args) == 1
