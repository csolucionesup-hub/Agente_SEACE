"""Relevance scoring for SEACE opportunities.

Etapa 1 del producto: dada una obra y la lista de palabras clave configuradas,
mide *qué tan cerca* está esa obra de lo que el usuario busca y por qué. Es una
dimensión distinta del ``commercial_score`` (que mide urgencia/valor comercial):
aquí solo importa el encaje con las keywords.

El puntaje es transparente y auditable (sin IA, sin caja negra): cada obra recibe
``relevance_score`` 0-100, la lista de ``matched_keywords`` y ``relevance_reasons``
que explican dónde matcheó cada término. El reporte se ordena por este puntaje.

Se necesita scoring del lado del cliente porque la API OECE solo filtra por el
título oficial del proceso (un código burocrático); la señal real de relevancia
vive en la *descripción*, que la API no indexa para búsqueda.
"""

from __future__ import annotations

from typing import Any
import re
import unicodedata

# Campos donde un match pesa como "título" (señal fuerte y corta) vs "cuerpo".
TITLE_FIELDS = ("process_code",)
BODY_FIELDS = ("description", "entity_name", "category", "procurement_method")

# Tiers de match, de más fuerte a más débil (fracción 0..1 del match perfecto).
TIER_PHRASE_IN_TITLE = 1.0      # frase exacta en el título oficial
TIER_PHRASE_IN_BODY = 0.85      # frase exacta en la descripción
TIER_ALL_TOKENS = 0.6          # todas las palabras del término, no adyacentes
TIER_PARTIAL = 0.4             # fracción de las palabras del término

# Mezcla del puntaje: fuerza del mejor match + amplitud (cuántas keywords distintas).
BEST_MATCH_WEIGHT = 85
BREADTH_BONUS_PER_KEYWORD = 5
BREADTH_BONUS_CAP = 15

# Penalización por cada término del anti-diccionario que matchee. Demota fuerte
# (no elimina): una obra con ruido cae al fondo del reporte pero sigue visible,
# coherente con "mostrar todo". Dos coincidencias negativas la llevan a 0.
NEGATIVE_PENALTY = 50


def _normalize(text: Any) -> str:
    """Lowercase + sin tildes para comparar 'Construcción' con 'construccion'."""
    raw = str(text or "")
    decomposed = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.lower()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    """True si ``phrase`` aparece en ``haystack``, tolerando plurales/inflexiones.

    Cada palabra del término matchea por prefijo (``\\w*`` al final) para que
    'PILOTE' encuentre 'pilotes' y 'CARRETERA' encuentre 'carreteras', tal como
    aparecen en las descripciones reales del SEACE.
    """
    if not phrase:
        return False
    words = [word for word in phrase.split() if word]
    if not words:
        return False
    pattern = r"\b" + r"\w*\s+".join(re.escape(word) for word in words) + r"\w*\b"
    return re.search(pattern, haystack) is not None


def _keyword_match(keyword: str, title_text: str, body_text: str) -> tuple[float, str]:
    """Devuelve (tier 0..1, dónde) del mejor match de una keyword en los textos."""
    normalized = _normalize(keyword).strip()
    if not normalized:
        return 0.0, ""
    tokens = [token for token in normalized.split() if token]

    if _contains_phrase(title_text, normalized):
        return TIER_PHRASE_IN_TITLE, "título"
    if _contains_phrase(body_text, normalized):
        return TIER_PHRASE_IN_BODY, "descripción"

    combined = f"{title_text} {body_text}"
    present = [token for token in tokens if _contains_phrase(combined, token)]
    if not present:
        return 0.0, ""
    if len(present) == len(tokens):
        return TIER_ALL_TOKENS, "términos dispersos"
    fraction = len(present) / len(tokens)
    return round(TIER_PARTIAL * fraction, 3), "parcial"


def score_relevance(
    row: dict[str, Any],
    keywords: list[str] | tuple[str, ...],
    negative_keywords: list[str] | tuple[str, ...] | None = None,
    *,
    title_fields: tuple[str, ...] = TITLE_FIELDS,
    body_fields: tuple[str, ...] = BODY_FIELDS,
) -> dict[str, Any]:
    """Copia de ``row`` con ``relevance_score``, ``matched_keywords`` y razones.

    ``negative_keywords`` es un anti-diccionario: cada término que matchee penaliza
    el puntaje (demota, no elimina) para combatir keywords ambiguas — p. ej. 'MUELLE'
    (embarcadero) jala 'hoja de muelle' (ballesta de camión); agregar 'hoja de muelle'
    a los negativos manda ese ruido al fondo. No filtra ni descarta: solo puntúa.
    """
    enriched = dict(row)
    title_text = _normalize(" ".join(str(enriched.get(field) or "") for field in title_fields))
    body_text = _normalize(" ".join(str(enriched.get(field) or "") for field in body_fields))

    best_tier = 0.0
    matched: list[str] = []
    reasons: list[str] = []
    for keyword in keywords:
        clean = str(keyword or "").strip()
        if not clean:
            continue
        tier, where = _keyword_match(clean, title_text, body_text)
        if tier <= 0:
            continue
        best_tier = max(best_tier, tier)
        upper = clean.upper()
        if upper not in matched:
            matched.append(upper)
            reasons.append(f"'{upper}' en {where}")

    breadth_bonus = min(max(len(matched) - 1, 0) * BREADTH_BONUS_PER_KEYWORD, BREADTH_BONUS_CAP)
    score = round(best_tier * BEST_MATCH_WEIGHT + breadth_bonus)

    excluded_by: list[str] = []
    combined_text = f"{title_text} {body_text}"
    for negative in negative_keywords or []:
        clean = str(negative or "").strip()
        if not clean:
            continue
        # Las negativas exigen la frase completa (adyacente) para no penalizar por
        # stopwords sueltos como "de"; el anti-diccionario debe ser preciso.
        if not _contains_phrase(combined_text, _normalize(clean)):
            continue
        upper = clean.upper()
        if upper not in excluded_by:
            excluded_by.append(upper)
            reasons.append(f"Penalizado por término excluido: '{upper}'")
    score -= NEGATIVE_PENALTY * len(excluded_by)

    enriched["relevance_score"] = max(0, min(100, score))
    enriched["matched_keywords"] = matched
    enriched["excluded_by"] = excluded_by
    enriched["relevance_reasons"] = reasons
    return enriched
