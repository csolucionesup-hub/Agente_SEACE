"""Repartidor de obras a suscriptores (alertas por cliente).

El worker hace UNA sola búsqueda en SEACE con la *unión* de las keywords de todos
los suscriptores activos. Esa unión es plomería interna: nadie recibe la búsqueda
completa. Este módulo es el repartidor que, para cada obra, decide a qué
suscriptores les corresponde — usando el mismo scoring de relevancia y el mismo
anti-diccionario que el reporte general (``seace_relevance``), pero por cliente.

Todo acá es función pura sobre un ``OpportunitySnapshot`` y una lista de
``Subscriber``: sin red, sin DB, sin Telegram. El fan-out real (capturar la ficha
una vez y reenviarla a cada chat) vive en el worker (Fase 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from seace_relevance import score_relevance
from seace_tracking import OpportunitySnapshot, Subscriber


@dataclass(frozen=True)
class RoutingMatch:
    """Un suscriptor al que le toca una obra, con el porqué del match."""

    subscriber: Subscriber
    relevance_score: int
    matched_keywords: list[str]


def _monto_obra(snapshot: OpportunitySnapshot) -> float | None:
    """Monto comparable de la obra: referencial, o adjudicado como fallback."""
    if snapshot.amount is not None:
        return snapshot.amount
    return snapshot.awarded_amount


def _pasa_min_amount(snapshot: OpportunitySnapshot, min_amount: float | None) -> bool:
    if min_amount is None:
        return True
    monto = _monto_obra(snapshot)
    if monto is None:
        # Monto desconocido: no descartamos por las dudas; mejor que el cliente
        # vea una obra de más que perder una relevante por falta de dato.
        return True
    return monto >= min_amount


def evaluar_obra(
    snapshot: OpportunitySnapshot,
    subscribers: Iterable[Subscriber],
    *,
    min_score: int = 1,
) -> list[RoutingMatch]:
    """Devuelve los suscriptores que matchean la obra, con score y keywords.

    Un suscriptor matchea si está activo, su ``relevance_score`` sobre la obra es
    ``>= min_score`` (lo que ya respeta el anti-diccionario: un negativo que
    matchea baja el score y puede dejarlo fuera) y la obra pasa su ``min_amount``.
    """
    row = snapshot.to_row()
    matches: list[RoutingMatch] = []
    for sub in subscribers:
        if not sub.active:
            continue
        scored = score_relevance(row, sub.keywords, sub.negative_keywords)
        if scored["relevance_score"] < min_score:
            continue
        if not _pasa_min_amount(snapshot, sub.min_amount):
            continue
        matches.append(
            RoutingMatch(
                subscriber=sub,
                relevance_score=scored["relevance_score"],
                matched_keywords=scored["matched_keywords"],
            )
        )
    return matches


def suscriptores_para_evento(
    snapshot: OpportunitySnapshot,
    subscribers: Iterable[Subscriber],
    *,
    min_score: int = 1,
) -> list[Subscriber]:
    """Repartidor: los suscriptores cuyo criterio matchea esta obra.

    Conveniencia sobre :func:`evaluar_obra` cuando solo se necesita a quién
    enrutar (Fase 3 del worker). El nombre habla de "evento" porque el worker la
    invoca al procesar un evento de seguimiento (p. ej. buena pro), pero el match
    se hace contra el ``snapshot`` de la obra.
    """
    return [match.subscriber for match in evaluar_obra(snapshot, subscribers, min_score=min_score)]
