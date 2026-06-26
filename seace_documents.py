"""Official SEACE/OECE document extraction, verification, and light technical analysis."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import re
import zipfile

ALLOWED_DOCUMENT_HOST_SUFFIXES = (
    ".seace.gob.pe",
    ".oece.gob.pe",
    ".gob.pe",
)

TECHNICAL_SIGNAL_TERMS = {
    "pilotes": ["pilote", "pilotes", "pilotaje"],
    "zapatas": ["zapata", "zapatas"],
    "estribos": ["estribo", "estribos"],
    "tablero": ["tablero", "losa de tablero"],
    "vigas": ["viga", "vigas", "viga-losa", "viga losa"],
    "planos": ["plano", "planos"],
    "metrados": ["metrado", "metrados"],
    "presupuesto": ["presupuesto", "presupuesto de obra"],
    "analisis_precios": ["análisis de precios", "analisis de precios", "precios unitarios"],
    "estudios_tecnicos": ["estudios técnicos", "estudios tecnicos", "estudio de suelos", "hidrología", "hidrologia"],
    "memoria_descriptiva": ["memoria descriptiva"],
    "expediente_tecnico": ["expediente técnico", "expediente tecnico"],
    "cimentacion": ["cimentación", "cimentacion", "cimentaciones"],
}

ETO_SECTIONS = [
    {
        "id": "section_1",
        "title": "Sección 1: Datos de aprobación",
        "official_components": [
            "Datos de aprobación del Expediente Técnico de Obra",
            "Funcionario que aprueba el ETO",
            "Formulación del ETO",
            "Plazo de ejecución de obra",
        ],
    },
    {
        "id": "section_2",
        "title": "Sección 2: Documentos técnicos base",
        "official_components": [
            "Índice del Expediente Técnico de Obra",
            "Memoria descriptiva",
            "Especificaciones técnicas",
            "Plazos de ejecución de obra",
            "Metrados",
        ],
    },
    {
        "id": "section_3",
        "title": "Sección 3: Presupuesto y estudios",
        "official_components": [
            "Presupuesto de obra",
            "Análisis de precios",
            "Relación de precios y cantidades de recursos",
            "Calendario de avance",
            "Fórmulas polinómicas",
            "Estudios técnicos",
            "Gestión de riesgos",
            "Gastos generales fijos y variables",
        ],
    },
    {
        "id": "section_4",
        "title": "Sección 4: Complementarios, terreno y otros",
        "official_components": [
            "Equipamiento",
            "Disponibilidad física del terreno",
            "Licencias, autorizaciones y permisos",
            "Otros documentos del expediente técnico",
            "Especificaciones técnicas del equipamiento",
            "Términos de referencia",
        ],
    },
]

ETO_COMPONENT_TERMS = {
    "planos": ["plano", "planos", "dwg"],
    "metrados": ["metrado", "metrados"],
    "memoria_descriptiva": ["memoria descriptiva"],
    "especificaciones_tecnicas": ["especificaciones técnicas", "especificaciones tecnicas"],
    "presupuesto": ["presupuesto"],
    "analisis_precios": ["análisis de precios", "analisis de precios", "precios unitarios", "apu"],
    "estudios_tecnicos": ["estudios técnicos", "estudios tecnicos", "estudio de suelos", "hidrolog"],
    "expediente_tecnico": ["expediente técnico", "expediente tecnico", "eto"],
}

MAX_ANALYSIS_BYTES = 12 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024


@dataclass(frozen=True)
class VerifiedDownload:
    filename: str
    content_type: str
    content: bytes


class DocumentAccessError(ValueError):
    """Raised when a document URL cannot be safely accessed."""


def _compiled_release(record_payload: dict[str, Any]) -> dict[str, Any]:
    if "compiledRelease" in record_payload:
        return record_payload.get("compiledRelease") or {}
    records = record_payload.get("records") or []
    if records and isinstance(records[0], dict):
        return records[0].get("compiledRelease") or records[0]
    return record_payload


def _safe_document_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and any(host == suffix[1:] or host.endswith(suffix) for suffix in ALLOWED_DOCUMENT_HOST_SUFFIXES)


def _safe_filename(value: str, fallback: str = "documento-oficial") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value or "").strip("-._")
    return cleaned[:120] or fallback


def _collect_documents_from_section(section: str, documents: list[Any], cleaned: list[dict[str, Any]]) -> None:
    for index, document in enumerate(documents or []):
        if not isinstance(document, dict):
            continue
        url = str(document.get("url") or "").strip()
        if not url:
            continue
        title = str(document.get("title") or document.get("id") or "Documento oficial").strip()
        fmt = str(document.get("format") or "").lower().strip()
        filename = _safe_filename(f"{section}-{index + 1}-{title}.{fmt or 'bin'}")
        cleaned.append(
            {
                "id": str(document.get("id") or f"{section}-{index + 1}"),
                "section": section,
                "title": title,
                "document_type": str(document.get("documentType") or ""),
                "format": fmt,
                "download_url": url,
                "date_published": str(document.get("datePublished") or document.get("dateModified") or ""),
                "language": str(document.get("language") or ""),
                "safe_to_proxy": _safe_document_url(url),
                "suggested_filename": filename,
            }
        )


def extract_official_documents(record_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract tender, award, and contract documents from an OCDS record."""
    compiled = _compiled_release(record_payload)
    tender = compiled.get("tender") or {}
    cleaned: list[dict[str, Any]] = []
    _collect_documents_from_section("tender", tender.get("documents") or [], cleaned)
    for award_index, award in enumerate(compiled.get("awards") or [], start=1):
        if isinstance(award, dict):
            _collect_documents_from_section(f"award-{award_index}", award.get("documents") or [], cleaned)
    for contract_index, contract in enumerate(compiled.get("contracts") or [], start=1):
        if isinstance(contract, dict):
            _collect_documents_from_section(f"contract-{contract_index}", contract.get("documents") or [], cleaned)
    cleaned.sort(key=lambda item: (0 if "base" in item["title"].lower() else 1, item["section"], item["title"]))
    return cleaned


def _document_eto_component(document: dict[str, Any]) -> str:
    text = " ".join(
        str(document.get(key) or "")
        for key in ("title", "document_type", "format", "suggested_filename")
    ).lower()
    for component, terms in ETO_COMPONENT_TERMS.items():
        if any(term.lower() in text for term in terms):
            return component
    return ""


def _is_work_record(record_payload: dict[str, Any]) -> bool:
    compiled = _compiled_release(record_payload)
    tender = compiled.get("tender") or {}
    text = " ".join(
        str(value or "")
        for value in (
            tender.get("mainProcurementCategory"),
            tender.get("title"),
            tender.get("description"),
            tender.get("procurementMethodDetails"),
        )
    ).lower()
    return "work" in text or "obra" in text or "puente" in text or "construcci" in text or "reparaci" in text


def build_technical_file_response(
    record_payload: dict[str, Any],
    *,
    verify: bool = False,
    analyze: bool = False,
    verifier=None,
    analyzer=None,
) -> dict[str, Any]:
    """Build the separate SEACE Expediente Técnico de Obra layer.

    The official OECE guide says ETO appears only for Obra procedures that have
    the section registered in the public Ficha de Selección, so absence from
    OCDS documents is reported conservatively instead of as a hard negative.
    """
    official_documents = extract_official_documents(record_payload)
    verifier = verifier or verify_document_link
    analyzer = analyzer or analyze_document
    eto_documents: list[dict[str, Any]] = []
    for document in official_documents:
        component = _document_eto_component(document)
        if not component:
            continue
        enriched = dict(document)
        enriched["eto_component"] = component
        enriched["preview_url"] = enriched.get("download_url")
        enriched["download_proxy_url"] = f"/api/documents/download?url={enriched['download_url']}"
        if verify:
            enriched["verification"] = verifier(enriched["download_url"])
        if analyze:
            enriched["analysis"] = analyzer(enriched["download_url"], enriched.get("format", ""))
        eto_documents.append(enriched)

    is_work = _is_work_record(record_payload)
    status = "detected" if eto_documents else ("requires_public_ficha_check" if is_work else "not_applicable")
    message = (
        "ETO detectado en documentos oficiales disponibles."
        if eto_documents
        else "No se detectó ETO en documentos OCDS. Si es Obra, revisar la Ficha de Selección y el ícono ‘Ver Expediente Técnico de Obra’."
        if is_work
        else "El ETO solo aplica a procedimientos cuyo objeto de contratación sea Obra y tengan la sección registrada."
    )

    technical_summary: dict[str, str] = {}
    if analyze:
        for document in eto_documents:
            for signal, payload in (document.get("analysis", {}).get("technical_signals") or {}).items():
                current = technical_summary.get(signal)
                candidate = payload.get("status", "not_detected")
                if current != "detected":
                    technical_summary[signal] = candidate
    for signal in ("pilotes", "zapatas", "estribos", "tablero", "vigas", "planos", "metrados", "presupuesto", "expediente_tecnico", "cimentacion"):
        technical_summary.setdefault(signal, "not_analyzed" if not analyze else "not_detected")

    return {
        "title": "Expediente Técnico de Obra",
        "status": status,
        "message": message,
        "eligibility": {
            "is_work": is_work,
            "reason": "Objeto de contratación = Obra" if is_work else "No se identificó Obra en el registro oficial",
            "official_note": "Según guía OECE, la sección ETO solo se muestra para procedimientos de Obra que tengan registrada esta sección.",
        },
        "sections": ETO_SECTIONS,
        "documents": eto_documents,
        "technical_summary": technical_summary,
        "quota_policy": {
            "viewing_consumes_credit": False,
            "verification_consumes_download": False,
            "analysis_consumes_download": False,
            "download_consumes_only_on_success": True,
            "failed_download_consumes_download": False,
        },
        "official_guides": [
            {
                "title": "Guía OECE: Visualización del Expediente Técnico de Obra en Buscador Público SEACE",
                "url": "https://www.gob.pe/institucion/oece/informes-publicaciones/986939-guia-de-usuario-del-modulo-del-buscador-publico-visualizacion-del-expediente-tecnico-de-obra-eto-vigente",
            }
        ],
    }


def _open_official_url(url: str, *, max_bytes: int, range_probe: bool = False) -> tuple[bytes, Any]:
    if not _safe_document_url(url):
        raise DocumentAccessError("URL no permitida; solo se aceptan documentos oficiales SEACE/OECE/gob.pe por HTTPS")
    headers = {"User-Agent": "LicitaScan/0.1 document verifier"}
    if range_probe:
        headers["Range"] = f"bytes=0-{max_bytes - 1}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=90) as response:  # noqa: S310 - validated official HTTPS document URL
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes and not range_probe:
            raise DocumentAccessError("Documento excede el límite permitido para esta operación")
        if len(content) > max_bytes:
            content = content[:max_bytes]
        return content, response


def verify_document_link(url: str) -> dict[str, Any]:
    """Verify that an official document responds without charging a download quota."""
    try:
        content, response = _open_official_url(url, max_bytes=64 * 1024, range_probe=True)
        content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
        content_length = response.headers.get("Content-Length")
        return {
            "status": "available",
            "ok": True,
            "content_type": content_type,
            "content_length": int(content_length) if str(content_length or "").isdigit() else None,
            "probe_bytes": len(content),
            "message": "Documento verificado. La vista/listado no consume descarga.",
        }
    except Exception as exc:  # noqa: BLE001 - surfaced as user-facing status
        return {
            "status": "unavailable",
            "ok": False,
            "content_type": "",
            "content_length": None,
            "probe_bytes": 0,
            "message": f"No se pudo verificar el documento; no debe consumir descarga. Detalle: {exc}",
        }


def _technical_signal_summary(text: str) -> dict[str, Any]:
    normalized = text.lower()
    signals: dict[str, Any] = {}
    for signal, terms in TECHNICAL_SIGNAL_TERMS.items():
        matches = []
        for term in terms:
            count = normalized.count(term.lower())
            if count:
                matches.append({"term": term, "count": count})
        signals[signal] = {
            "status": "detected" if matches else "not_detected",
            "matches": matches,
        }
    return signals


def _extract_pdf_text(content: bytes) -> tuple[str, int | None]:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise DocumentAccessError(f"pypdf no está disponible para analizar PDF: {exc}") from exc
    reader = PdfReader(BytesIO(content))
    chunks: list[str] = []
    for page in reader.pages[:120]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks), len(reader.pages)


def analyze_document(url: str, fmt: str = "") -> dict[str, Any]:
    """Download a bounded official document and scan for bridge/work technical signals."""
    verification = verify_document_link(url)
    if not verification.get("ok"):
        return {"verification": verification, "analysis_status": "not_analyzed", "technical_signals": {}, "message": verification["message"]}
    try:
        content, response = _open_official_url(url, max_bytes=MAX_ANALYSIS_BYTES)
        content_type = str(response.headers.get("Content-Type") or "")
        detected_format = (fmt or "").lower() or _format_from_headers_or_magic(content_type, content)
        if detected_format == "pdf":
            text, pages = _extract_pdf_text(content)
            signals = _technical_signal_summary(text)
            return {
                "verification": verification,
                "analysis_status": "analyzed",
                "format": "pdf",
                "pages": pages,
                "technical_signals": signals,
                "message": "PDF analizado por texto extraíble; si está escaneado puede requerir OCR.",
            }
        if detected_format == "zip":
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = [
                    {"name": info.filename, "size": info.file_size}
                    for info in archive.infolist()
                    if not info.is_dir()
                ]
            names_text = "\n".join(entry["name"] for entry in entries)
            signals = _technical_signal_summary(names_text)
            return {
                "verification": verification,
                "analysis_status": "analyzed",
                "format": "zip",
                "entries": entries[:200],
                "technical_signals": signals,
                "message": "ZIP analizado por nombres de archivos; para leer PDFs internos se requiere análisis avanzado.",
            }
        return {
            "verification": verification,
            "analysis_status": "not_supported",
            "format": detected_format or fmt or "desconocido",
            "technical_signals": {},
            "message": "Formato no soportado para análisis automático básico.",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "verification": verification,
            "analysis_status": "error",
            "technical_signals": {},
            "message": f"No se pudo analizar; no debe consumir descarga. Detalle: {exc}",
        }


def _format_from_headers_or_magic(content_type: str, content: bytes) -> str:
    lowered = content_type.lower()
    if "pdf" in lowered or content.startswith(b"%PDF"):
        return "pdf"
    if "zip" in lowered or content.startswith(b"PK"):
        return "zip"
    if content.startswith(b"Rar!"):
        return "rar"
    return ""


def download_verified_document(url: str, filename: str = "") -> VerifiedDownload:
    """Fetch a full official document only after URL validation; caller counts quota only on success."""
    content, response = _open_official_url(url, max_bytes=MAX_DOWNLOAD_BYTES)
    content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
    safe_name = _safe_filename(filename or "documento-oficial.bin")
    return VerifiedDownload(filename=safe_name, content_type=content_type, content=content)
