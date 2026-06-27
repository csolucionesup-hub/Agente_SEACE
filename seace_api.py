"""Official SEACE/OECE API client and opportunity exporters.

The public portal "Contrataciones Abiertas" exposes SEACE data through OCDS
(Open Contracting Data Standard) endpoints. This module makes that source the
primary data feed for Agente SEACE; browser automation remains useful only for
visual evidence and edge cases.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import csv
import json


DEFAULT_OCDS_BASE_URL = "https://contratacionesabiertas.oece.gob.pe"


class JsonHttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return parsed JSON for a GET request."""
        ...


class UrlLibJsonHttpClient:
    """Small stdlib HTTP client to avoid adding runtime dependencies."""

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Agente-SEACE/1.0 (+https://github.com/csolucionesup-hub/Agente_SEACE)",
            },
        )
        with urlopen(request, timeout=60) as response:  # noqa: S310 - official public HTTPS API
            return json.loads(response.read().decode("utf-8"))


@dataclass(frozen=True)
class Opportunity:
    keyword: str
    ocid: str
    tender_id: str
    process_code: str
    entity_name: str
    entity_id: str
    description: str
    category: str
    procurement_method: str
    amount: float | None
    currency: str
    date: str
    tender_start_date: str
    tender_end_date: str
    source: str
    api_url: str

    @property
    def record_url(self) -> str:
        return self.api_url

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["record_url"] = self.record_url
        return row


class SeaceApiClient:
    """Client for the official OECE Contrataciones Abiertas API."""

    def __init__(self, base_url: str = DEFAULT_OCDS_BASE_URL, http: JsonHttpClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or UrlLibJsonHttpClient()

    def search_opportunities(self, keyword: str, page: int = 1, paginate_by: int = 50) -> list[Opportunity]:
        payload = self.http.get_json(
            f"{self.base_url}/api/v1/search",
            params={"q": keyword, "page": page, "paginateBy": paginate_by, "format": "json"},
        )
        return [normalize_search_result(result, keyword=keyword, base_url=self.base_url) for result in payload.get("results", [])]

    def list_monthly_files(
        self,
        source: str | None = None,
        year: str | int | None = None,
        month: str | int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"format": "json"}
        if source:
            params["source"] = source
        if year:
            params["year"] = str(year)
        if month:
            params["month"] = f"{int(month):02d}" if str(month).isdigit() else str(month)
        payload = self.http.get_json(f"{self.base_url}/api/v1/files", params=params)
        return payload.get("results", [])

    def get_record(self, ocid: str) -> dict[str, Any]:
        return self.http.get_json(f"{self.base_url}/api/v1/record/{ocid}", params={"format": "json"})

    def get_release(self, release_id: str) -> dict[str, Any]:
        return self.http.get_json(f"{self.base_url}/api/v1/release/{release_id}", params={"format": "json"})


def _dig(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current if current is not None else default


def normalize_search_result(result: dict[str, Any], keyword: str, base_url: str = DEFAULT_OCDS_BASE_URL) -> Opportunity:
    compiled = result.get("compiledRelease") or result.get("release") or result
    tender = compiled.get("tender", {})
    value = tender.get("value", {})
    period = tender.get("tenderPeriod", {})
    source_items = compiled.get("sources") or []
    first_source = source_items[0].get("name", "") if source_items and isinstance(source_items[0], dict) else ""
    ocid = str(compiled.get("ocid") or "")

    amount: float | None
    raw_amount = value.get("amount")
    try:
        amount = float(raw_amount) if raw_amount not in (None, "") else None
    except (TypeError, ValueError):
        amount = None

    return Opportunity(
        keyword=keyword.upper(),
        ocid=ocid,
        tender_id=str(tender.get("id") or ""),
        process_code=str(tender.get("title") or ""),
        entity_name=str(_dig(tender, "procuringEntity", "name")),
        entity_id=str(_dig(tender, "procuringEntity", "id")),
        description=str(tender.get("description") or ""),
        category=str(tender.get("mainProcurementCategory") or ""),
        procurement_method=str(tender.get("procurementMethodDetails") or tender.get("procurementMethod") or ""),
        amount=amount,
        currency=str(value.get("currency") or value.get("currencyName") or ""),
        date=str(compiled.get("date") or ""),
        tender_start_date=str(period.get("startDate") or ""),
        tender_end_date=str(period.get("endDate") or ""),
        source=first_source,
        api_url=f"{base_url.rstrip('/')}/api/v1/record/{ocid}?format=json" if ocid else "",
    )


def export_opportunities_csv(opportunities: list[Opportunity], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [field.name for field in fields(Opportunity)] + ["record_url"]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for opportunity in opportunities:
            writer.writerow(opportunity.to_row())
    return output_path


def export_opportunities_json(opportunities: list[Opportunity], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([opportunity.to_row() for opportunity in opportunities], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
