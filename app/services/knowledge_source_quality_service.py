"""Quality helpers for AI knowledge source chunks."""

import re
from dataclasses import dataclass

from app.services.text_normalization_service import normalize_text, tokenize_text

MIN_CHUNK_CHARACTERS = 24
MIN_CHUNK_TOKENS = 3
BAD_OCR_MIN_CHARACTERS = 40
BAD_OCR_MAX_ALPHA_RATIO = 0.35
BAD_OCR_MIN_SYMBOL_RATIO = 0.25
BAD_OCR_REPLACEMENT_LIMIT = 2
BOILERPLATE_TOKENS = {
    "copyright",
    "seite",
    "page",
    "confidential",
    "vertraulich",
    "all",
    "rights",
    "reserved",
}

_LAST_CHUNK_QUALITY_REPORTS = {}


@dataclass
class ChunkQualityReport:
    """Track prompt-safe quality decisions made during chunk rebuilding."""

    accepted_chunks: int = 0
    total_chunks_seen: int = 0
    skipped_empty_chunks: int = 0
    skipped_short_chunks: int = 0
    skipped_duplicate_chunks: int = 0
    skipped_low_quality_chunks: int = 0
    skipped_bad_ocr_chunks: int = 0
    affected_documents: int = 0

    def to_dict(self):
        """Return a JSON-serializable quality report."""
        return {
            "accepted_chunks": self.accepted_chunks,
            "total_chunks_seen": self.total_chunks_seen,
            "skipped_empty_chunks": self.skipped_empty_chunks,
            "skipped_short_chunks": self.skipped_short_chunks,
            "skipped_duplicate_chunks": self.skipped_duplicate_chunks,
            "skipped_low_quality_chunks": self.skipped_low_quality_chunks,
            "skipped_bad_ocr_chunks": self.skipped_bad_ocr_chunks,
            "affected_documents": self.affected_documents,
        }


def chunk_payload_text(chunk_payload):
    """Return text from a chunk payload or raw chunk value."""
    if isinstance(chunk_payload, dict):
        return str(chunk_payload.get("text") or "")
    return str(chunk_payload or "")


def normalize_chunk_text(value):
    """Return normalized text used for source-quality checks."""
    return normalize_text(value, lowercase=True, fold_german=True)


def chunk_fingerprint(value):
    """Return a stable fingerprint for duplicate detection within one source."""
    normalized = normalize_chunk_text(value)
    return " ".join(sorted(tokenize_text(normalized, min_length=2, expand_synonyms=False)))


def chunk_quality_reasons(value):
    """Return concrete quality rejection reasons for a chunk."""
    normalized = normalize_chunk_text(value)
    if not normalized:
        return {"empty"}
    reasons = set()
    if has_bad_ocr_signature(value):
        reasons.add("bad_ocr")
    tokens = tokenize_text(normalized, min_length=2, expand_synonyms=False)
    if _has_technical_signal(normalized):
        return reasons
    if len(normalized) < MIN_CHUNK_CHARACTERS:
        reasons.add("too_short")
    if len(tokens) < MIN_CHUNK_TOKENS:
        reasons.add("too_few_tokens")
    if tokens and tokens.issubset(BOILERPLATE_TOKENS):
        reasons.add("boilerplate")
    return reasons


def has_bad_ocr_signature(value):
    """Return whether text looks like unusable OCR noise."""
    text = str(value or "").strip()
    if not text:
        return False
    compact_text = re.sub(r"\s+", "", text)
    if len(compact_text) < BAD_OCR_MIN_CHARACTERS:
        return False
    replacement_count = text.count("\ufffd")
    if replacement_count >= BAD_OCR_REPLACEMENT_LIMIT:
        return True
    alpha_count = sum(1 for char in compact_text if char.isalpha())
    symbol_count = sum(1 for char in compact_text if not char.isalnum())
    total_count = max(len(compact_text), 1)
    alpha_ratio = alpha_count / total_count
    symbol_ratio = symbol_count / total_count
    if alpha_ratio <= BAD_OCR_MAX_ALPHA_RATIO and symbol_ratio >= BAD_OCR_MIN_SYMBOL_RATIO:
        return True
    return bool(symbol_ratio >= 0.42 and re.search(r"[^A-Za-z0-9\s]{5,}", text))


def filter_quality_chunks(chunk_payloads):
    """Return chunks that pass quality checks plus a prompt-safe report."""
    accepted_chunks = []
    seen_fingerprints = set()
    report = ChunkQualityReport()
    for chunk_payload in chunk_payloads:
        report.total_chunks_seen += 1
        chunk_text = chunk_payload_text(chunk_payload)
        reasons = chunk_quality_reasons(chunk_text)
        if reasons:
            _record_quality_rejection(report, reasons)
            report.skipped_low_quality_chunks += 1
            continue
        fingerprint = chunk_fingerprint(chunk_text)
        if fingerprint and fingerprint in seen_fingerprints:
            report.skipped_duplicate_chunks += 1
            continue
        if fingerprint:
            seen_fingerprints.add(fingerprint)
        accepted_chunks.append(chunk_payload)
    report.accepted_chunks = len(accepted_chunks)
    if report.skipped_duplicate_chunks or report.skipped_low_quality_chunks:
        report.affected_documents = 1
    return accepted_chunks, report


def reset_chunk_quality_reports():
    """Clear in-process chunk-quality reports before a new reindex run."""
    _LAST_CHUNK_QUALITY_REPORTS.clear()


def remember_chunk_quality_report(document_id, report):
    """Store the latest chunk-quality report for one document."""
    if document_id is None or report is None:
        return
    _LAST_CHUNK_QUALITY_REPORTS[int(document_id)] = report


def chunk_quality_report_for_document(document_id):
    """Return the latest quality report for one document id."""
    return _LAST_CHUNK_QUALITY_REPORTS.get(int(document_id), ChunkQualityReport())


def latest_chunk_quality_summary():
    """Return the latest aggregate chunk-quality summary."""
    return aggregate_chunk_quality_reports(_LAST_CHUNK_QUALITY_REPORTS.values())


def aggregate_chunk_quality_reports(reports):
    """Return a combined prompt-safe quality report for several documents."""
    summary = ChunkQualityReport()
    affected_documents = 0
    for report in reports:
        if not report:
            continue
        summary.accepted_chunks += int(report.accepted_chunks or 0)
        summary.total_chunks_seen += int(report.total_chunks_seen or 0)
        summary.skipped_empty_chunks += int(report.skipped_empty_chunks or 0)
        summary.skipped_short_chunks += int(report.skipped_short_chunks or 0)
        summary.skipped_duplicate_chunks += int(report.skipped_duplicate_chunks or 0)
        summary.skipped_low_quality_chunks += int(report.skipped_low_quality_chunks or 0)
        summary.skipped_bad_ocr_chunks += int(report.skipped_bad_ocr_chunks or 0)
        if report.skipped_duplicate_chunks or report.skipped_low_quality_chunks:
            affected_documents += 1
    summary.affected_documents = affected_documents
    return summary.to_dict()


def _record_quality_rejection(report, reasons):
    """Increment detailed quality counters for rejected chunks."""
    if "empty" in reasons:
        report.skipped_empty_chunks += 1
    if "bad_ocr" in reasons:
        report.skipped_bad_ocr_chunks += 1
    if "bad_ocr" not in reasons and ("too_short" in reasons or "too_few_tokens" in reasons):
        report.skipped_short_chunks += 1


def _has_technical_signal(value):
    """Return whether short text still contains useful technical evidence."""
    tokens = tokenize_text(value, min_length=2, expand_synonyms=False)
    if any(any(char.isdigit() for char in token) for token in tokens):
        return True
    technical_terms = {
        "fehler",
        "fehlercode",
        "task",
        "maschine",
        "wartung",
        "loesung",
        "ursache",
        "sensor",
        "ventil",
        "presse",
    }
    return bool(tokens.intersection(technical_terms))
