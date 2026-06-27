"""Commercial scoring for SEACE opportunities.

This module converts normalized opportunity rows into product-facing signals:
priority, urgency, recommended action and reasons. Keeping this pure makes it
safe to test and reuse from dashboard export, API and future alert workers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

FAILED_OUTCOMES = {
    "desierto": "Proceso desierto",
    "cancelado": "Proceso cancelado",
    "nulo": "Proceso nulo",
    "perdida_buena_pro": "Pérdida de buena pro",
    "no_suscripcion": "No suscripción de contrato",
}
HIGH_VALUE_THRESHOLD = 500_000
VERY_HIGH_VALUE_THRESHOLD = 1_000_000


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _days_to(value: Any, today: date) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return (parsed - today).days


def _base_urgency(days: int | None) -> tuple[str, str]:
    if days is None:
        return "low", "Sin fecha crítica"
    if days < 0:
        return "high", f"Venció hace {abs(days)} días"
    if days == 0:
        return "high", "Vence hoy"
    if days == 1:
        return "medium", "Vence mañana"
    if days <= 5:
        return "medium", f"Faltan {days} días"
    return "low", f"Faltan {days} días"


def _priority(score: int, outcome: str, urgency_level: str) -> str:
    if outcome in FAILED_OUTCOMES:
        return "Baja"
    if urgency_level == "high" or score >= 70:
        return "Alta"
    if score >= 35:
        return "Media"
    return "Baja"


def enrich_opportunity(opportunity: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Return a copy of an opportunity with commercial scoring fields."""
    today = today or date.today()
    row = dict(opportunity)
    stage = str(row.get("stage") or "")
    outcome = str(row.get("outcome") or "")
    amount = float(row.get("amount") or 0)
    has_winner = bool(row.get("winner_name"))
    has_contract = stage == "contrato_suscrito" or bool(row.get("contract_id") or row.get("contract_date_signed"))
    days = _days_to(row.get("next_critical_date"), today)
    urgency_level, urgency_label = _base_urgency(days)
    score = 0
    reasons: list[str] = []

    if outcome in FAILED_OUTCOMES:
        row.update(
            {
                "commercial_score": 10,
                "priority_label": "Baja",
                "urgency_level": "inactive",
                "urgency_label": "Proceso caído",
                "days_to_critical_date": days,
                "recommended_action": "Esperar reinicio o nueva convocatoria; no invertir gestión comercial ahora",
                "commercial_reasons": [FAILED_OUTCOMES[outcome]],
            }
        )
        return row

    if has_contract:
        score += 45
        reasons.append("Contrato suscrito")
        urgency_label = "Ganador/contrato detectado"
        urgency_level = "high"
    elif stage == "buena_pro_otorgada":
        score += 40
        reasons.append("Buena pro otorgada")
        urgency_label = "Ganador/contrato detectado"
        urgency_level = "high"

    if has_winner:
        score += 25
        reasons.append("Ganador identificado")

    if days is not None:
        if days <= 0:
            score += 35
            reasons.append("Fecha crítica vence hoy" if days == 0 else "Fecha crítica vencida")
        elif days <= 5:
            score += 25
            reasons.append("Fecha crítica próxima")

    if amount >= VERY_HIGH_VALUE_THRESHOLD:
        score += 25
        reasons.append("Monto referencial alto")
    elif amount >= HIGH_VALUE_THRESHOLD:
        score += 15
        reasons.append("Monto referencial relevante")

    if stage == "convocado" and outcome == "activo":
        score += 20
        if not reasons:
            reasons.append("Oportunidad activa")

    score = min(score, 100)
    priority = _priority(score, outcome, urgency_level)
    if has_contract or has_winner:
        recommended = "Registrar ganador, monto adjudicado y alimentar inteligencia competitiva"
    elif urgency_level in {"high", "medium"}:
        recommended = "Revisar hoy y decidir seguimiento antes de la fecha crítica"
    elif amount >= HIGH_VALUE_THRESHOLD:
        recommended = "Calificar encaje técnico y decidir si entra a seguimiento comercial"
    else:
        recommended = "Revisar si aplica al rubro del cliente"

    row.update(
        {
            "commercial_score": score,
            "priority_label": priority,
            "urgency_level": urgency_level,
            "urgency_label": urgency_label,
            "days_to_critical_date": days,
            "recommended_action": recommended,
            "commercial_reasons": reasons,
        }
    )
    return row
