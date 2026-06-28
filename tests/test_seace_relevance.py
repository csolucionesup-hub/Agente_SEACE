"""Tests for the keyword relevance scoring (etapa 1)."""

from __future__ import annotations

from seace_relevance import score_relevance


KEYWORDS = ["PILOTE", "CARRETERA", "PILOTE HINCADO", "MICROPILOTE"]


def _row(**overrides):
    base = {
        "process_code": "RES-PROC-456-2026-MTC-1",
        "description": "",
        "entity_name": "MUNICIPALIDAD PROVINCIAL DE LIMA",
        "category": "works",
        "procurement_method": "Licitación Pública",
    }
    base.update(overrides)
    return base


def test_phrase_in_description_scores_high():
    row = score_relevance(
        _row(description="Construcción de pilotes para el puente sobre el río"),
        KEYWORDS,
    )
    assert row["relevance_score"] >= 70
    assert "PILOTE" in row["matched_keywords"]
    assert any("descripción" in reason for reason in row["relevance_reasons"])


def test_phrase_in_title_outranks_description():
    in_title = score_relevance(_row(process_code="PILOTE CFA - obra vial"), KEYWORDS)
    in_body = score_relevance(_row(description="trabajos de pilote en zona costera"), KEYWORDS)
    assert in_title["relevance_score"] > in_body["relevance_score"]


def test_accent_and_case_insensitive():
    row = score_relevance(_row(description="CONSTRUCCIÓN DE CARRETERA Panamericana"), KEYWORDS)
    assert "CARRETERA" in row["matched_keywords"]
    assert row["relevance_score"] > 0


def test_breadth_bonus_for_multiple_keywords():
    one = score_relevance(_row(description="obra de pilote en la zona"), KEYWORDS)
    two = score_relevance(_row(description="pilote y carretera en el mismo expediente"), KEYWORDS)
    assert two["relevance_score"] > one["relevance_score"]


def test_no_match_scores_zero():
    row = score_relevance(_row(description="Adquisición de licencias de software ofimático"), KEYWORDS)
    assert row["relevance_score"] == 0
    assert row["matched_keywords"] == []
    assert row["relevance_reasons"] == []


def test_partial_multiword_match_scores_below_full_phrase():
    partial = score_relevance(_row(description="trabajo de pilote sin hinca"), ["PILOTE HINCADO"])
    full = score_relevance(_row(description="pilote hincado de concreto"), ["PILOTE HINCADO"])
    assert 0 < partial["relevance_score"] < full["relevance_score"]


def test_negative_keyword_demotes_ambiguous_noise():
    # 'MUELLE' (embarcadero) jala 'hoja de muelle' (ballesta de camión).
    noise = _row(description="CAMBIO DE 02 HOJAS DE MUELLE para volquete")
    without = score_relevance(noise, ["MUELLE"])
    with_anti = score_relevance(noise, ["MUELLE"], ["hoja de muelle"])
    assert with_anti["relevance_score"] < without["relevance_score"]
    assert "HOJA DE MUELLE" in with_anti["excluded_by"]
    assert any("excluido" in reason.lower() for reason in with_anti["relevance_reasons"])


def test_negative_keyword_does_not_affect_clean_match():
    clean = _row(description="Construcción de muelle portuario de atraque")
    with_anti = score_relevance(clean, ["MUELLE"], ["hoja de muelle", "abrazadera"])
    assert with_anti["excluded_by"] == []
    assert with_anti["relevance_score"] == score_relevance(clean, ["MUELLE"])["relevance_score"]


def test_two_negative_matches_drive_score_to_zero():
    noise = _row(description="hoja de muelle y abrazadera de repuesto para camion")
    row = score_relevance(noise, ["MUELLE"], ["hoja de muelle", "abrazadera"])
    assert row["relevance_score"] == 0


def test_does_not_mutate_input_row():
    original = _row(description="carretera nueva")
    score_relevance(original, KEYWORDS)
    assert "relevance_score" not in original
