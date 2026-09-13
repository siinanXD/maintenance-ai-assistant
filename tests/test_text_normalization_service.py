"""Tests for central retrieval text normalization."""

from app.services.text_normalization_service import (
    expand_german_synonyms,
    normalize_query,
    normalize_text,
    tokenize_text,
)


def test_normalize_text_folds_german_umlauts_and_case():
    """Verify German characters are normalized for retrieval matching."""
    assert normalize_text("  ÄÖÜ Straße  ") == "aeoeue strasse"
    assert normalize_text("Fällig Öl prüfen") == "faellig oel pruefen"


def test_normalize_query_handles_dash_variants_and_synonyms():
    """Verify query normalization expands spelling variants for technical terms."""
    normalized = normalize_query("FU am Not–Aus prüfen")

    assert "fu" in normalized
    assert "frequenzumrichter" in normalized
    assert "notaus" in normalized
    assert "emergency stop" in normalized


def test_expand_german_synonyms_returns_known_technical_variants():
    """Verify technical synonym expansion is deterministic and compact."""
    sps_synonyms = expand_german_synonyms("SPS")
    sensor_synonyms = expand_german_synonyms("Naeherungsschalter")

    assert "sps" in sps_synonyms
    assert "plc" in sps_synonyms
    assert "sensor" in sensor_synonyms
    assert "naeherungsschalter" in sensor_synonyms


def test_tokenize_text_normalizes_hyphens_and_short_technical_tokens():
    """Verify tokenization keeps retrieval-relevant technical variants."""
    tokens = tokenize_text("FU, SPS/PLC, Sensor und Not-Aus am Motor-Antrieb")

    assert {"fu", "frequenzumrichter", "sps", "plc"} <= tokens
    assert {"sensor", "naeherungsschalter"} <= tokens
    assert {"not-aus", "notaus", "motor", "antrieb"} <= tokens
    assert "motor-antrieb" in tokens
    assert "motorantrieb" in tokens
