from seace_tracking import Subscriber, TrackingStore


def sample_subscriber(chat_id="100", name="Constructora ABC", active=True):
    return Subscriber(
        name=name,
        telegram_chat_id=chat_id,
        keywords=["PUENTE", "PILOTE"],
        negative_keywords=["HOJA DE MUELLE"],
        min_amount=500000.0,
        active=active,
    )


def make_store(tmp_path):
    store = TrackingStore(tmp_path / "tracking.sqlite3")
    store.initialize()
    return store


def test_initialize_creates_subscribers_table(tmp_path):
    store = make_store(tmp_path)

    tables = store.connection.execute(
        "select name from sqlite_master where type='table' order by name"
    ).fetchall()
    table_names = [row[0] for row in tables]
    assert "subscribers" in table_names


def test_initialize_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    store.upsert_subscriber(sample_subscriber())

    # Re-correr initialize no debe borrar ni romper datos existentes.
    store.initialize()

    assert len(store.list_subscribers()) == 1


def test_upsert_assigns_id_and_round_trips_fields(tmp_path):
    store = make_store(tmp_path)

    saved = store.upsert_subscriber(sample_subscriber())

    assert saved.id is not None
    assert saved.name == "Constructora ABC"
    assert saved.telegram_chat_id == "100"
    assert saved.keywords == ["PUENTE", "PILOTE"]
    assert saved.negative_keywords == ["HOJA DE MUELLE"]
    assert saved.min_amount == 500000.0
    assert saved.active is True


def test_upsert_updates_existing_chat_without_duplicating(tmp_path):
    store = make_store(tmp_path)
    first = store.upsert_subscriber(sample_subscriber(name="Nombre viejo"))

    updated = store.upsert_subscriber(
        Subscriber(
            name="Nombre nuevo",
            telegram_chat_id="100",
            keywords=["CARRETERA"],
            negative_keywords=[],
            min_amount=None,
        )
    )

    assert updated.id == first.id  # mismo registro, no uno nuevo
    assert len(store.list_subscribers()) == 1
    assert updated.name == "Nombre nuevo"
    assert updated.keywords == ["CARRETERA"]
    assert updated.min_amount is None


def test_get_subscriber_returns_none_when_absent(tmp_path):
    store = make_store(tmp_path)
    assert store.get_subscriber("999") is None


def test_list_subscribers_active_only(tmp_path):
    store = make_store(tmp_path)
    store.upsert_subscriber(sample_subscriber(chat_id="100", active=True))
    store.upsert_subscriber(sample_subscriber(chat_id="200", active=False))

    assert {s.telegram_chat_id for s in store.list_subscribers()} == {"100", "200"}
    assert [s.telegram_chat_id for s in store.list_subscribers(active_only=True)] == ["100"]


def test_set_subscriber_active_toggles_flag(tmp_path):
    store = make_store(tmp_path)
    store.upsert_subscriber(sample_subscriber(chat_id="100", active=True))

    assert store.set_subscriber_active("100", False) is True
    assert store.get_subscriber("100").active is False
    assert store.set_subscriber_active("999", False) is False  # no existe


def test_delete_subscriber(tmp_path):
    store = make_store(tmp_path)
    store.upsert_subscriber(sample_subscriber(chat_id="100"))

    assert store.delete_subscriber("100") is True
    assert store.get_subscriber("100") is None
    assert store.delete_subscriber("100") is False  # ya no existe
