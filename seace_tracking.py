"""Tracking engine for SEACE opportunities.

This module stores one latest snapshot per OCID plus a timeline of commercial
events. It intentionally uses SQLite from the Python standard library so the MVP
can run locally, in cron, or behind a small Lovable/backend integration without
extra infrastructure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import sqlite3

from seace_commercial_scoring import enrich_opportunity


TERMINAL_OUTCOMES = {"contratado", "desierto", "cancelado", "nulo", "perdida_buena_pro", "no_suscripcion"}


@dataclass(frozen=True)
class OpportunitySnapshot:
    ocid: str
    process_code: str
    entity_name: str
    description: str
    amount: float | None
    currency: str
    tender_status: str
    stage: str
    next_critical_date: str
    winner_name: str
    winner_ruc: str
    awarded_amount: float | None
    award_date: str
    contract_id: str
    contract_date_signed: str
    contract_start_date: str
    contract_end_date: str
    outcome: str
    raw: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["raw_json"] = json.dumps(self.raw, ensure_ascii=False, sort_keys=True)
        del row["raw"]
        return row

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "OpportunitySnapshot":
        data = dict(row)
        raw_json = data.pop("raw_json") or "{}"
        data.pop("updated_at", None)
        return cls(raw=json.loads(raw_json), **data)


@dataclass(frozen=True)
class TrackingEvent:
    ocid: str
    event_type: str
    title: str
    message: str
    severity: str
    occurred_at: str
    payload: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["payload_json"] = json.dumps(self.payload, ensure_ascii=False, sort_keys=True)
        del row["payload"]
        return row

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TrackingEvent":
        data = dict(row)
        data.pop("id", None)
        payload_json = data.pop("payload_json") or "{}"
        return cls(payload=json.loads(payload_json), **data)


@dataclass(frozen=True)
class Subscriber:
    """Un cliente de LicitaScan con su propio criterio de alerta.

    Cada suscriptor define *qué* obras le interesan (``keywords`` /
    ``negative_keywords``, mismo anti-diccionario que ``seace_relevance``) y *a
    dónde* recibirlas (``telegram_chat_id``). El worker hace UNA búsqueda con la
    unión de las keywords de todos y un repartidor rutea cada obra solo a los
    suscriptores cuyas keywords matchean: cada cliente recibe únicamente lo suyo.
    """

    name: str
    telegram_chat_id: str
    keywords: list[str]
    negative_keywords: list[str]
    min_amount: float | None = None
    active: bool = True
    id: int | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "telegram_chat_id": str(self.telegram_chat_id),
            "keywords_json": json.dumps(list(self.keywords), ensure_ascii=False),
            "negative_keywords_json": json.dumps(list(self.negative_keywords), ensure_ascii=False),
            "min_amount": self.min_amount,
            "active": 1 if self.active else 0,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Subscriber":
        data = dict(row)
        return cls(
            id=data.get("id"),
            name=data["name"],
            telegram_chat_id=str(data["telegram_chat_id"]),
            keywords=json.loads(data.get("keywords_json") or "[]"),
            negative_keywords=json.loads(data.get("negative_keywords_json") or "[]"),
            min_amount=data.get("min_amount"),
            active=bool(data.get("active", 1)),
        )


def _dig(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current if current is not None else default


def _compiled_release(record_payload: dict[str, Any]) -> dict[str, Any]:
    if "compiledRelease" in record_payload:
        return record_payload.get("compiledRelease") or {}
    records = record_payload.get("records") or []
    if records and isinstance(records[0], dict):
        return records[0].get("compiledRelease") or records[0]
    return record_payload


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _supplier_ruc(supplier_id: str) -> str:
    """Devuelve el RUC solo si es válido (11 dígitos).

    Los consorcios no tienen RUC propio: SEACE les asigna un código interno corto
    (p. ej. 'PE-RUC-165567'). Devolver ese código como si fuera un RUC engaña al
    usuario, así que solo aceptamos RUCs reales de 11 dígitos; para consorcios el
    RUC queda vacío y el ganador se identifica por su nombre.
    """
    candidate = supplier_id.replace("PE-RUC-", "").strip()
    if len(candidate) == 11 and candidate.isdigit():
        return candidate
    return ""


def _stage_and_outcome(tender: dict[str, Any], awards: list[dict[str, Any]], contracts: list[dict[str, Any]]) -> tuple[str, str]:
    item_statuses = " ".join(str(item.get("statusDetails") or "") for item in tender.get("items", []))
    normalized = f"{tender.get('status', '')} {item_statuses}".upper()

    if contracts:
        return "contrato_suscrito", "contratado"
    if awards:
        return "buena_pro_otorgada", "adjudicado"
    if "DESIERTO" in normalized:
        return "desierto", "desierto"
    if "CANCEL" in normalized:
        return "cancelado", "cancelado"
    if "NUL" in normalized:
        return "nulo", "nulo"
    return "convocado", "activo"


def snapshot_from_record(record_payload: dict[str, Any]) -> OpportunitySnapshot:
    compiled = _compiled_release(record_payload)
    tender = compiled.get("tender") or {}
    awards = compiled.get("awards") or []
    contracts = compiled.get("contracts") or []
    value = tender.get("value") or {}
    period = tender.get("tenderPeriod") or {}
    first_award = awards[0] if awards else {}
    first_contract = contracts[0] if contracts else {}
    first_supplier = (first_award.get("suppliers") or [{}])[0]
    award_value = first_award.get("value") or {}
    contract_period = first_contract.get("period") or {}
    stage, outcome = _stage_and_outcome(tender, awards, contracts)

    return OpportunitySnapshot(
        ocid=str(compiled.get("ocid") or ""),
        process_code=str(tender.get("title") or tender.get("id") or ""),
        entity_name=str(_dig(tender, "procuringEntity", "name")),
        description=str(tender.get("description") or ""),
        amount=_float_or_none(value.get("amount")),
        currency=str(value.get("currency") or award_value.get("currency") or ""),
        tender_status=str(tender.get("status") or ""),
        stage=stage,
        next_critical_date=str(period.get("endDate") or ""),
        winner_name=str(first_supplier.get("name") or ""),
        winner_ruc=_supplier_ruc(str(first_supplier.get("id") or "")),
        awarded_amount=_float_or_none(award_value.get("amount")),
        award_date=str(first_award.get("date") or ""),
        contract_id=str(first_contract.get("id") or ""),
        contract_date_signed=str(first_contract.get("dateSigned") or ""),
        contract_start_date=str(contract_period.get("startDate") or ""),
        contract_end_date=str(contract_period.get("endDate") or ""),
        outcome=outcome,
        raw=compiled,
    )


def _event_time(snapshot: OpportunitySnapshot, preferred: str = "") -> str:
    return preferred or str(snapshot.raw.get("date") or "")


def diff_snapshots(previous: OpportunitySnapshot | None, current: OpportunitySnapshot) -> list[TrackingEvent]:
    events: list[TrackingEvent] = []

    if previous is None:
        events.append(
            TrackingEvent(
                ocid=current.ocid,
                event_type="nueva_oportunidad",
                title="Nueva oportunidad detectada",
                message=f"Nueva oportunidad {current.process_code} de {current.entity_name}.",
                severity="medium",
                occurred_at=_event_time(current),
                payload=current.to_row(),
            )
        )
        return events

    if previous.stage != "buena_pro_otorgada" and current.stage == "buena_pro_otorgada":
        amount_text = f" por S/ {current.awarded_amount:,.2f}" if current.awarded_amount is not None else ""
        winner_text = current.winner_name or "proveedor por confirmar"
        events.append(
            TrackingEvent(
                ocid=current.ocid,
                event_type="buena_pro_otorgada",
                title="Buena pro otorgada",
                message=f"Buena pro otorgada a {winner_text}{amount_text} en {current.process_code}.",
                severity="high",
                occurred_at=_event_time(current, current.award_date),
                payload={
                    "winner_name": current.winner_name,
                    "winner_ruc": current.winner_ruc,
                    "awarded_amount": current.awarded_amount,
                    "award_date": current.award_date,
                    "source_url": _official_source_url(current.raw),
                    # Datos para apuntar la captura de ficha a la obra EXACTA (alerta_ficha)
                    "process_code": current.process_code,
                    "entity_name": current.entity_name,
                    "description": current.description,
                },
            )
        )

    if previous.stage != "contrato_suscrito" and current.stage == "contrato_suscrito":
        events.append(
            TrackingEvent(
                ocid=current.ocid,
                event_type="contrato_suscrito",
                title="Contrato suscrito",
                message=f"Contrato {current.contract_id} suscrito para {current.process_code}.",
                severity="high",
                occurred_at=_event_time(current, current.contract_date_signed),
                payload={
                    "contract_id": current.contract_id,
                    "contract_date_signed": current.contract_date_signed,
                    "contract_start_date": current.contract_start_date,
                    "contract_end_date": current.contract_end_date,
                    "source_url": _official_source_url(current.raw),
                },
            )
        )

    if previous.outcome == "activo" and current.outcome in {"desierto", "cancelado", "nulo", "perdida_buena_pro", "no_suscripcion"}:
        events.append(
            TrackingEvent(
                ocid=current.ocid,
                event_type="proceso_caido",
                title="Proceso caído o interrumpido",
                message=f"El proceso {current.process_code} cambió a estado {current.outcome}.",
                severity="high",
                occurred_at=_event_time(current),
                payload={"outcome": current.outcome, "stage": current.stage},
            )
        )

    if (
        previous.next_critical_date
        and current.next_critical_date
        and previous.next_critical_date != current.next_critical_date
        and current.outcome == "activo"
    ):
        events.append(
            TrackingEvent(
                ocid=current.ocid,
                event_type="fecha_critica_actualizada",
                title="Fecha crítica actualizada",
                message=f"La próxima fecha crítica de {current.process_code} cambió a {current.next_critical_date}.",
                severity="medium",
                occurred_at=_event_time(current),
                payload={
                    "previous_next_critical_date": previous.next_critical_date,
                    "next_critical_date": current.next_critical_date,
                },
            )
        )

    return events


class TrackingStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.connection.executescript(
            """
            create table if not exists opportunities (
                ocid text primary key,
                process_code text not null,
                entity_name text not null,
                description text not null,
                amount real,
                currency text not null,
                tender_status text not null,
                stage text not null,
                next_critical_date text not null,
                winner_name text not null,
                winner_ruc text not null,
                awarded_amount real,
                award_date text not null,
                contract_id text not null,
                contract_date_signed text not null,
                contract_start_date text not null,
                contract_end_date text not null,
                outcome text not null,
                raw_json text not null,
                updated_at text not null default current_timestamp
            );

            create table if not exists opportunity_events (
                id integer primary key autoincrement,
                ocid text not null,
                event_type text not null,
                title text not null,
                message text not null,
                severity text not null,
                occurred_at text not null,
                payload_json text not null,
                created_at text not null default current_timestamp,
                foreign key (ocid) references opportunities(ocid)
            );

            create index if not exists idx_opportunity_events_ocid
                on opportunity_events(ocid, occurred_at, id);

            create table if not exists subscribers (
                id integer primary key autoincrement,
                name text not null,
                telegram_chat_id text not null unique,
                keywords_json text not null default '[]',
                negative_keywords_json text not null default '[]',
                min_amount real,
                active integer not null default 1,
                created_at text not null default current_timestamp,
                updated_at text not null default current_timestamp
            );
            """
        )
        self.connection.commit()

    def upsert_snapshot(self, snapshot: OpportunitySnapshot) -> None:
        row = snapshot.to_row()
        columns = list(row.keys())
        placeholders = ", ".join([f":{column}" for column in columns])
        update_clause = ", ".join([f"{column}=excluded.{column}" for column in columns if column != "ocid"])
        self.connection.execute(
            f"""
            insert into opportunities ({', '.join(columns)})
            values ({placeholders})
            on conflict(ocid) do update set
                {update_clause},
                updated_at=current_timestamp
            """,
            row,
        )
        self.connection.commit()

    def get_snapshot(self, ocid: str) -> OpportunitySnapshot | None:
        row = self.connection.execute("select * from opportunities where ocid = ?", (ocid,)).fetchone()
        if row is None:
            return None
        return OpportunitySnapshot.from_row(row)

    def add_event(self, event: TrackingEvent) -> None:
        row = event.to_row()
        columns = list(row.keys())
        placeholders = ", ".join([f":{column}" for column in columns])
        self.connection.execute(
            f"insert into opportunity_events ({', '.join(columns)}) values ({placeholders})",
            row,
        )
        self.connection.commit()

    def list_events(self, ocid: str) -> list[TrackingEvent]:
        rows = self.connection.execute(
            "select id, ocid, event_type, title, message, severity, occurred_at, payload_json "
            "from opportunity_events where ocid = ? order by occurred_at, id",
            (ocid,),
        ).fetchall()
        return [TrackingEvent.from_row(row) for row in rows]

    def list_all_events(self, limit: int = 50) -> list[TrackingEvent]:
        rows = self.connection.execute(
            "select id, ocid, event_type, title, message, severity, occurred_at, payload_json "
            "from opportunity_events order by created_at desc, id desc limit ?",
            (limit,),
        ).fetchall()
        return [TrackingEvent.from_row(row) for row in rows]

    def list_active_ocids(self) -> list[str]:
        placeholders = ", ".join("?" for _ in TERMINAL_OUTCOMES)
        rows = self.connection.execute(
            f"""
            select ocid from opportunities
            where outcome not in ({placeholders})
              and lower(tender_status) not in ('complete', 'completed', 'cancelled', 'canceled')
            order by ocid
            """,
            tuple(sorted(TERMINAL_OUTCOMES)),
        ).fetchall()
        return [row["ocid"] for row in rows]

    def list_snapshots(self) -> list[OpportunitySnapshot]:
        rows = self.connection.execute("select * from opportunities order by ocid").fetchall()
        return [OpportunitySnapshot.from_row(row) for row in rows]

    def list_all_ocids(self) -> list[str]:
        """Todos los OCID en seguimiento, sin importar etapa/outcome.

        A diferencia de ``list_active_ocids`` (que excluye los terminales para el
        worker), esto devuelve TODO lo que el usuario agregó a la bandeja. La
        búsqueda lo usa para no volver a mostrar obras ya seguidas.
        """
        rows = self.connection.execute(
            "select ocid from opportunities order by ocid"
        ).fetchall()
        return [row["ocid"] for row in rows]

    def delete_snapshot(self, ocid: str) -> bool:
        """Quita una obra del seguimiento (y sus eventos). Devuelve True si existía."""
        clean_ocid = str(ocid)
        self.connection.execute(
            "delete from opportunity_events where ocid = ?", (clean_ocid,)
        )
        cursor = self.connection.execute(
            "delete from opportunities where ocid = ?", (clean_ocid,)
        )
        self.connection.commit()
        return cursor.rowcount > 0

    # --- Suscriptores (alertas por cliente) -------------------------------

    def upsert_subscriber(self, subscriber: Subscriber) -> Subscriber:
        """Crea o actualiza un suscriptor identificado por su ``telegram_chat_id``.

        El chat de Telegram es la identidad del cliente (columna única): volver a
        dar de alta el mismo chat actualiza sus criterios en vez de duplicarlo.
        Devuelve el registro persistido, ya con su ``id`` asignado.
        """
        self.connection.execute(
            """
            insert into subscribers
                (name, telegram_chat_id, keywords_json, negative_keywords_json, min_amount, active)
            values
                (:name, :telegram_chat_id, :keywords_json, :negative_keywords_json, :min_amount, :active)
            on conflict(telegram_chat_id) do update set
                name=excluded.name,
                keywords_json=excluded.keywords_json,
                negative_keywords_json=excluded.negative_keywords_json,
                min_amount=excluded.min_amount,
                active=excluded.active,
                updated_at=current_timestamp
            """,
            subscriber.to_row(),
        )
        self.connection.commit()
        saved = self.get_subscriber(subscriber.telegram_chat_id)
        assert saved is not None  # acabamos de insertarlo/actualizarlo
        return saved

    def get_subscriber(self, telegram_chat_id: str) -> Subscriber | None:
        row = self.connection.execute(
            "select * from subscribers where telegram_chat_id = ?",
            (str(telegram_chat_id),),
        ).fetchone()
        if row is None:
            return None
        return Subscriber.from_row(row)

    def list_subscribers(self, active_only: bool = False) -> list[Subscriber]:
        query = "select * from subscribers"
        if active_only:
            query += " where active = 1"
        query += " order by id"
        rows = self.connection.execute(query).fetchall()
        return [Subscriber.from_row(row) for row in rows]

    def set_subscriber_active(self, telegram_chat_id: str, active: bool) -> bool:
        """Activa/desactiva un suscriptor. Devuelve True si existía."""
        cursor = self.connection.execute(
            "update subscribers set active = ?, updated_at = current_timestamp "
            "where telegram_chat_id = ?",
            (1 if active else 0, str(telegram_chat_id)),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def delete_subscriber(self, telegram_chat_id: str) -> bool:
        """Elimina un suscriptor. Devuelve True si existía."""
        cursor = self.connection.execute(
            "delete from subscribers where telegram_chat_id = ?",
            (str(telegram_chat_id),),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def close(self) -> None:
        self.connection.close()


def track_record_payload(store: TrackingStore, record_payload: dict[str, Any]) -> list[TrackingEvent]:
    current = snapshot_from_record(record_payload)
    previous = store.get_snapshot(current.ocid)
    events = diff_snapshots(previous, current)
    store.upsert_snapshot(current)
    for event in events:
        store.add_event(event)
    return events


def _official_documents(raw: dict[str, Any]) -> list[dict[str, str]]:
    tender = raw.get("tender") if isinstance(raw, dict) else {}
    documents = tender.get("documents") if isinstance(tender, dict) else []
    cleaned: list[dict[str, str]] = []
    for document in documents or []:
        if not isinstance(document, dict):
            continue
        url = str(document.get("url") or "").strip()
        title = str(document.get("title") or document.get("id") or "Documento oficial").strip()
        if not url:
            continue
        cleaned.append(
            {
                "id": str(document.get("id") or ""),
                "title": title,
                "document_type": str(document.get("documentType") or ""),
                "format": str(document.get("format") or ""),
                "download_url": url,
                "date_published": str(document.get("datePublished") or ""),
                "language": str(document.get("language") or ""),
            }
        )
    cleaned.sort(key=lambda item: (0 if "base" in item["title"].lower() else 1, item["title"]))
    return cleaned


def _official_source_url(raw: dict[str, Any]) -> str:
    sources = raw.get("sources") if isinstance(raw, dict) else []
    for source in sources or []:
        if isinstance(source, dict) and source.get("url"):
            return str(source["url"])
    return "https://prodapp2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"


def _snapshot_dashboard_row(snapshot: OpportunitySnapshot) -> dict[str, Any]:
    row = asdict(snapshot)
    row["official_documents"] = _official_documents(snapshot.raw)
    row["official_source_url"] = _official_source_url(snapshot.raw)
    row.pop("raw", None)
    return enrich_opportunity(row)


def _event_dashboard_row(event: TrackingEvent) -> dict[str, Any]:
    row = asdict(event)
    if isinstance(row.get("payload"), dict):
        row["payload"].pop("raw_json", None)
    return row


def export_dashboard_json(store: TrackingStore, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots = store.list_snapshots()
    recent_events = store.list_all_events(limit=50)
    counts_by_stage: dict[str, int] = {}
    counts_by_outcome: dict[str, int] = {}
    for snapshot in snapshots:
        counts_by_stage[snapshot.stage] = counts_by_stage.get(snapshot.stage, 0) + 1
        counts_by_outcome[snapshot.outcome] = counts_by_outcome.get(snapshot.outcome, 0) + 1

    payload = {
        "counts_by_stage": counts_by_stage,
        "counts_by_outcome": counts_by_outcome,
        "opportunities": [_snapshot_dashboard_row(snapshot) for snapshot in snapshots],
        "recent_events": [_event_dashboard_row(event) for event in recent_events],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
