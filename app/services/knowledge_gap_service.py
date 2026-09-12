"""Knowledge-gap tracking for unanswered or low-confidence AI responses."""

import hashlib
import logging
import re
from collections import Counter, defaultdict
from datetime import timedelta

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import ErrorEntry, KnowledgeDocument, KnowledgeGap, Machine
from app.services.text_normalization_service import tokenize_text

logger = logging.getLogger(__name__)

TRACKED_RESPONSE_TYPES = {"agent"}
# Only retrieval-backed answers can reveal missing knowledge; general model
# answers and structured data lists never create gap entries.
TRACKED_ANSWER_CATEGORIES = {"rag"}
GAP_STATUSES = {"api_key_missing", "openai_error", "fallback_used"}
DEFAULT_DEDUP_HOURS = 24
DEFAULT_LOW_CONFIDENCE_SCORE = 35
HIGH_IMPACT_MACHINE_CRITICALITIES = {"critical", "high"}
HIGH_IMPACT_MACHINE_STATUSES = {"down", "failed", "fault", "maintenance", "offline", "stopped"}
MACHINE_DOCUMENT_SOURCE_TYPES = {"machine", "machine_manual", "manual", "manual_training"}


def maybe_track_knowledge_gap(question, user, result):
    """Persist a knowledge gap when an AI result has no reliable source context."""
    if not should_track_gap(result):
        return None

    try:
        gap, created = upsert_knowledge_gap(question, user, result)
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        logger.exception("knowledge_gap_persist_failed user_id=%s", getattr(user, "id", None))
        return None

    payload = gap.to_dict()
    payload["created"] = created
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["knowledge_gap_id"] = gap.id
    diagnostics["knowledge_gap_created"] = created
    result["knowledge_gap"] = payload
    return payload


def should_track_gap(result):
    """Return whether a chat result should create a knowledge-gap entry."""
    if not isinstance(result, dict):
        return False
    if result.get("type") not in TRACKED_RESPONSE_TYPES:
        return False

    diagnostics = result.get("diagnostics") or {}
    sources = result.get("sources") or []
    if diagnostics.get("status") in GAP_STATUSES or diagnostics.get("fallback_used"):
        return True
    answer_category = result.get("answer_category") or diagnostics.get("answer_category")
    if answer_category not in TRACKED_ANSWER_CATEGORIES:
        return False
    if not sources:
        return True

    knowledge_sources = [source for source in sources if source.get("type") == "knowledge"]
    if not knowledge_sources:
        return False

    scores = [_numeric_score(source.get("score")) for source in knowledge_sources]
    known_scores = [score for score in scores if score is not None]
    if not known_scores:
        return False
    return max(known_scores) < low_confidence_score()


def upsert_knowledge_gap(question, user, result):
    """Create or update a recent open knowledge gap for the same normalized question."""
    normalized = normalize_question(question)
    question_hash = hash_question(normalized)
    now = utc_now()
    department = department_name(user)
    existing = recent_open_gap(question_hash, department, now)
    context_text = build_gap_context(result)
    machine = detect_machine(question)

    if existing:
        existing.last_seen_at = now
        existing.updated_at = now
        existing.occurrence_count = (existing.occurrence_count or 1) + 1
        existing.context_text = context_text or existing.context_text
        existing.machine = machine or existing.machine
        existing.audit_event_id = (result.get("diagnostics") or {}).get("audit_event_id")
        db.session.commit()
        return existing, False

    gap = KnowledgeGap(
        question=str(question or "").strip()[:4000],
        question_hash=question_hash,
        context_text=context_text,
        machine=machine,
        department=department,
        status="open",
        occurrence_count=1,
        user_id=getattr(user, "id", None),
        audit_event_id=(result.get("diagnostics") or {}).get("audit_event_id"),
        created_at=now,
        last_seen_at=now,
        updated_at=now,
    )
    db.session.add(gap)
    db.session.commit()
    return gap, True


def recent_open_gap(question_hash, department, now):
    """Return a recent open gap with the same question hash and department."""
    cutoff = now - timedelta(hours=dedup_hours())
    query = KnowledgeGap.query.filter(
        KnowledgeGap.question_hash == question_hash,
        KnowledgeGap.status == "open",
        KnowledgeGap.last_seen_at >= cutoff,
    )
    if department:
        query = query.filter(KnowledgeGap.department == department)
    return query.order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc()).first()


def list_knowledge_gaps(args):
    """Return filtered knowledge-gap entries for admin views."""
    query = KnowledgeGap.query
    status = str(args.get("status") or "").strip()
    q = str(args.get("q") or "").strip()
    if status:
        query = query.filter(KnowledgeGap.status == status)
    if q:
        pattern = f"%{q}%"
        query = query.filter(
            (KnowledgeGap.question.ilike(pattern))
            | (KnowledgeGap.context_text.ilike(pattern))
            | (KnowledgeGap.machine.ilike(pattern))
            | (KnowledgeGap.department.ilike(pattern))
        )
    return query.order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc())


def knowledge_gap_detection(args=None):
    """Return structured knowledge-gap clusters and coverage recommendations."""
    args = args or {}
    limit = _bounded_int(args.get("limit"), 20, 1, 100)
    gaps = (
        list_knowledge_gaps({**args, "status": args.get("status") or "open"})
        .limit(
            limit,
        )
        .all()
    )
    documents = KnowledgeDocument.query.filter(
        KnowledgeDocument.status.in_(("indexed", "ready", "processed")),
    ).all()
    error_gaps = _error_gap_rows(gaps, documents)
    uncovered_error_gaps = _uncovered_error_gap_rows(documents)
    uncovered_machine_gaps = _uncovered_machine_gap_rows(documents)
    return {
        "summary": _gap_detection_summary(
            gaps,
            error_gaps,
            uncovered_error_gaps,
            uncovered_machine_gaps,
        ),
        "machine_gaps": _machine_gap_rows(gaps, documents),
        "uncovered_machine_gaps": uncovered_machine_gaps,
        "error_gaps": error_gaps,
        "uncovered_error_gaps": uncovered_error_gaps,
        "department_gaps": _department_gap_rows(gaps),
        "frequent_terms": _gap_terms(gaps),
        "knowledge_gap_actions": _knowledge_gap_actions(
            gaps,
            documents,
            error_gaps,
            uncovered_error_gaps,
            uncovered_machine_gaps,
        ),
    }


def build_gap_context(result):
    """Build a compact admin-facing context string for a low-confidence answer."""
    diagnostics = result.get("diagnostics") or {}
    sources = result.get("sources") or []
    source_titles = ", ".join(str(source.get("title") or "") for source in sources[:3])
    parts = [
        f"Antworttyp: {result.get('type') or 'assistant'}",
        f"Diagnostics: {diagnostics.get('status') or 'unknown'}",
        f"Fallback: {bool(diagnostics.get('fallback_used'))}",
        f"Quellen: {len(sources)}",
    ]
    if source_titles:
        parts.append(f"Beste Quellen: {source_titles}")
    return " | ".join(parts)[:4000]


def detect_machine(question):
    """Return a machine name detected from known machines or simple wording."""
    text = str(question or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for machine in Machine.query.order_by(Machine.name.asc()).limit(200).all():
        if machine.name and machine.name.lower() in lowered:
            return machine.name[:160]
    match = re.search(r"\b(?:maschine|anlage)\s+([a-zA-Z0-9_-]+)", text, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0)[:160]


def department_name(user):
    """Return the user's department name when available."""
    department = getattr(user, "department", None)
    return (department.name if department else "")[:120]


def normalize_question(question):
    """Return a normalized question string for duplicate detection."""
    return re.sub(r"[^a-zA-Z0-9äöüÄÖÜß]+", " ", str(question or "").lower()).strip()


def hash_question(normalized_question):
    """Return a stable short hash for a normalized question."""
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


def dedup_hours():
    """Return the duplicate detection window in hours."""
    if not has_app_context():
        return DEFAULT_DEDUP_HOURS
    try:
        value = int(current_app.config.get("KNOWLEDGE_GAP_DEDUP_HOURS", DEFAULT_DEDUP_HOURS))
    except (TypeError, ValueError):
        return DEFAULT_DEDUP_HOURS
    return max(1, value)


def low_confidence_score():
    """Return the minimum acceptable source score before tracking a gap."""
    if not has_app_context():
        return DEFAULT_LOW_CONFIDENCE_SCORE
    try:
        value = int(
            current_app.config.get(
                "KNOWLEDGE_GAP_LOW_CONFIDENCE_SCORE",
                DEFAULT_LOW_CONFIDENCE_SCORE,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_LOW_CONFIDENCE_SCORE
    return max(0, value)


def _gap_detection_summary(
    gaps,
    error_gaps=None,
    uncovered_error_gaps=None,
    uncovered_machine_gaps=None,
):
    """Return compact counters for the selected knowledge-gap window."""
    error_gaps = error_gaps or []
    uncovered_error_gaps = uncovered_error_gaps or []
    uncovered_machine_gaps = uncovered_machine_gaps or []
    recurring_count = sum(1 for gap in gaps if int(gap.occurrence_count or 0) > 1)
    machine_count = len({gap.machine for gap in gaps if gap.machine})
    department_count = len({gap.department for gap in gaps if gap.department})
    return {
        "open_gap_count": len(gaps),
        "recurring_gap_count": recurring_count,
        "machine_gap_count": machine_count,
        "error_gap_count": len(error_gaps),
        "uncovered_error_gap_count": len(uncovered_error_gaps),
        "critical_uncovered_error_gap_count": sum(
            1 for row in uncovered_error_gaps if row.get("priority") == "high"
        ),
        "uncovered_machine_gap_count": len(uncovered_machine_gaps),
        "critical_uncovered_machine_gap_count": sum(
            1 for row in uncovered_machine_gaps if row.get("priority") == "high"
        ),
        "department_gap_count": department_count,
    }


def _machine_gap_rows(gaps, documents):
    """Return gap clusters by machine with rough document coverage."""
    grouped = defaultdict(list)
    for gap in gaps:
        if gap.machine:
            grouped[gap.machine].append(gap)

    rows = []
    for machine, machine_gaps in grouped.items():
        matching_documents = _documents_matching_machine(documents, machine)
        related_errors = _related_errors_for_machine(machine)
        rows.append(
            {
                "machine": machine,
                "open_gap_count": len(machine_gaps),
                "occurrence_count": sum(gap.occurrence_count or 0 for gap in machine_gaps),
                "document_count": len(matching_documents),
                "related_error_count": related_errors,
                "coverage": _coverage_label(len(matching_documents), machine_gaps),
                "latest_gap_at": max(gap.last_seen_at for gap in machine_gaps).isoformat(),
                "example_questions": [_bounded_gap_question(gap) for gap in machine_gaps[:3]],
                "machine_id": _machine_id_for_name(machine),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["coverage"] == "missing",
            row["occurrence_count"],
            row["latest_gap_at"],
        ),
        reverse=True,
    )


def _department_gap_rows(gaps):
    """Return gap clusters by department."""
    counter = Counter()
    latest = {}
    for gap in gaps:
        department = gap.department or "Unbekannt"
        counter[department] += gap.occurrence_count or 1
        latest[department] = max(gap.last_seen_at, latest.get(department, gap.last_seen_at))
    return [
        {
            "department": department,
            "occurrence_count": count,
            "latest_gap_at": latest[department].isoformat(),
        }
        for department, count in counter.most_common(10)
    ]


def _error_gap_rows(gaps, documents):
    """Return gap clusters by known error entry with rough document coverage."""
    if not gaps:
        return []

    error_entries = ErrorEntry.query.order_by(ErrorEntry.created_at.desc()).limit(300).all()
    grouped = defaultdict(list)
    for gap in gaps:
        for error_entry in error_entries:
            if _gap_matches_error(gap, error_entry):
                grouped[error_entry.id].append((error_entry, gap))

    rows = []
    for grouped_items in grouped.values():
        error_entry = grouped_items[0][0]
        matching_gaps = [item[1] for item in grouped_items]
        matching_documents = _documents_matching_error(documents, error_entry)
        rows.append(
            {
                "error_id": error_entry.id,
                "error_code": error_entry.error_code,
                "title": error_entry.title,
                "machine": error_entry.machine,
                "severity": error_entry.severity,
                "repeat_count": error_entry.repeat_count,
                "downtime_minutes": error_entry.downtime_minutes,
                "open_gap_count": len(matching_gaps),
                "occurrence_count": sum(gap.occurrence_count or 0 for gap in matching_gaps),
                "document_count": len(matching_documents),
                "coverage": _coverage_label(len(matching_documents), matching_gaps),
                "latest_gap_at": max(gap.last_seen_at for gap in matching_gaps).isoformat(),
                "example_questions": [_bounded_gap_question(gap) for gap in matching_gaps[:3]],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["coverage"] == "missing",
            row["occurrence_count"],
            row["latest_gap_at"],
        ),
        reverse=True,
    )[:10]


def _uncovered_error_gap_rows(documents):
    """Return high-impact error entries missing error-specific knowledge coverage."""
    error_entries = ErrorEntry.query.order_by(ErrorEntry.created_at.desc()).limit(300).all()
    rows = []
    for error_entry in error_entries:
        if not _is_high_impact_error(error_entry):
            continue
        matching_documents = _documents_matching_error(
            documents,
            error_entry,
            require_error_specific=True,
        )
        if matching_documents:
            continue
        rows.append(
            {
                "error_id": error_entry.id,
                "error_code": error_entry.error_code,
                "title": error_entry.title,
                "machine": error_entry.machine,
                "severity": error_entry.severity,
                "status": error_entry.status,
                "repeat_count": error_entry.repeat_count,
                "downtime_minutes": error_entry.downtime_minutes,
                "production_loss_minutes": error_entry.production_loss_minutes,
                "document_count": 0,
                "coverage": "missing",
                "priority": _uncovered_error_priority(error_entry),
                "impact_score": _error_impact_score(error_entry),
                "reason": _uncovered_error_reason(error_entry),
                "latest_seen_at": (
                    error_entry.last_seen_at.isoformat()
                    if error_entry.last_seen_at
                    else error_entry.created_at.isoformat()
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["priority"] == "high",
            row["impact_score"],
            row["latest_seen_at"],
        ),
        reverse=True,
    )[:10]


def _uncovered_machine_gap_rows(documents):
    """Return high-impact machines missing machine-specific knowledge coverage."""
    machines = Machine.query.order_by(Machine.created_at.desc(), Machine.id.desc()).limit(300).all()
    rows = []
    for machine in machines:
        if not _is_high_impact_machine(machine):
            continue
        matching_documents = _documents_matching_machine_record(documents, machine)
        if matching_documents:
            continue
        rows.append(
            {
                "machine_id": machine.id,
                "machine": machine.name,
                "criticality": machine.criticality,
                "status": machine.status,
                "last_downtime_at": (
                    machine.last_downtime_at.isoformat() if machine.last_downtime_at else None
                ),
                "document_count": 0,
                "coverage": "missing",
                "priority": _uncovered_machine_priority(machine),
                "impact_score": _machine_impact_score(machine),
                "reason": _uncovered_machine_reason(machine),
                "latest_seen_at": (
                    machine.last_downtime_at.isoformat()
                    if machine.last_downtime_at
                    else machine.created_at.isoformat()
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["priority"] == "high",
            row["impact_score"],
            row["latest_seen_at"],
        ),
        reverse=True,
    )[:10]


def _gap_terms(gaps):
    """Return frequent non-sensitive search terms from knowledge-gap questions."""
    stopwords = {
        "bitte",
        "das",
        "der",
        "die",
        "eine",
        "fuer",
        "fur",
        "ich",
        "ist",
        "mit",
        "und",
        "was",
        "welche",
        "wie",
        "zu",
    }
    counter = Counter()
    for gap in gaps:
        for token in tokenize_text(gap.question):
            if len(token) < 3 or token in stopwords:
                continue
            counter[token] += gap.occurrence_count or 1
    return [{"term": term, "count": count} for term, count in counter.most_common(12)]


def _knowledge_gap_actions(
    gaps,
    documents,
    error_gaps=None,
    uncovered_error_gaps=None,
    uncovered_machine_gaps=None,
):
    """Return actionable next steps for admins based on gap clusters."""
    actions = []
    for row in _machine_gap_rows(gaps, documents):
        if row["coverage"] == "missing":
            actions.append(
                {
                    "type": "missing_machine_documentation",
                    "priority": "high" if row["occurrence_count"] > 1 else "medium",
                    "target_type": "machine",
                    "target_id": row.get("machine_id"),
                    "target": row["machine"],
                    "machine": row["machine"],
                    "reason": (
                        f"{row['open_gap_count']} offene Gap(s), "
                        f"{row['document_count']} passende Dokumente"
                    ),
                    "recommended_action": (
                        "Maschinendokumentation oder FAQ aus bestaetigtem Wissen ergaenzen."
                    ),
                    "next_steps": _machine_gap_next_steps(row),
                    "success_criteria": _machine_gap_success_criteria(row),
                }
            )
        elif row["coverage"] == "thin":
            actions.append(
                {
                    "type": "thin_machine_documentation",
                    "priority": "medium",
                    "target_type": "machine",
                    "target_id": row.get("machine_id"),
                    "target": row["machine"],
                    "machine": row["machine"],
                    "reason": "Wiederkehrende Fragen trotz geringer Dokumentabdeckung.",
                    "recommended_action": (
                        "Bestehende Dokumente pruefen und konkrete Stoerungsfaelle ergaenzen."
                    ),
                    "next_steps": _machine_gap_next_steps(row),
                    "success_criteria": _machine_gap_success_criteria(row),
                }
            )
    for row in error_gaps or []:
        if row["coverage"] != "missing":
            continue
        actions.append(
            {
                "type": "missing_error_documentation",
                "priority": _error_gap_priority(row),
                "target_type": "error_entry",
                "target_id": row.get("error_id"),
                "target": row["error_code"],
                "error_id": row.get("error_id"),
                "error_code": row["error_code"],
                "machine": row.get("machine"),
                "title": row.get("title"),
                "reason": (
                    f"{row['open_gap_count']} offene Gap(s), "
                    f"{row['document_count']} passende Fehlerdokumente"
                ),
                "recommended_action": (
                    "Fehlercode, Ursachen, Symptome und bestaetigte Loesung "
                    "als Knowledge-Quelle dokumentieren."
                ),
                "next_steps": _error_gap_next_steps(row),
                "success_criteria": _error_gap_success_criteria(row),
            }
        )
    for row in uncovered_error_gaps or []:
        actions.append(
            {
                "type": "missing_high_impact_error_documentation",
                "priority": row["priority"],
                "target_type": "error_entry",
                "target_id": row.get("error_id"),
                "target": row["error_code"],
                "error_id": row.get("error_id"),
                "error_code": row["error_code"],
                "machine": row.get("machine"),
                "title": row.get("title"),
                "reason": row["reason"],
                "recommended_action": (
                    "Fehlercode, Symptome, Ursachen und bestaetigte Abhilfe "
                    "als Error-Knowledge-Dokument ergaenzen."
                ),
                "next_steps": _uncovered_error_next_steps(row),
                "success_criteria": _error_gap_success_criteria(row),
            }
        )
    for row in uncovered_machine_gaps or []:
        actions.append(
            {
                "type": "missing_high_impact_machine_documentation",
                "priority": row["priority"],
                "target_type": "machine",
                "target_id": row.get("machine_id"),
                "target": row["machine"],
                "machine": row["machine"],
                "reason": row["reason"],
                "recommended_action": (
                    "Kritische Maschine mit Betriebszustand, Wartungshistorie, "
                    "Stoerbildern und Wiederanlaufhinweisen als Knowledge-Quelle abdecken."
                ),
                "next_steps": _uncovered_machine_next_steps(row),
                "success_criteria": _machine_gap_success_criteria(row),
            }
        )
    if not actions and gaps:
        actions.append(
            {
                "type": "review_open_gaps",
                "priority": "low",
                "target": "knowledge_gaps",
                "reason": "Offene Gaps vorhanden, aber keine klare Maschinenluecke erkannt.",
                "recommended_action": (
                    "Top-Fragen pruefen und passende FAQ- oder RAG-Quelle anlegen."
                ),
                "next_steps": [
                    "Top-Fragen nach Wiederholung und Abteilung priorisieren.",
                    "Fehlende Antwort als freigegebenes Knowledge-Dokument erfassen.",
                    "RAG-Testfrage mit erwarteter Quelle fuer die neue Antwort anlegen.",
                ],
                "success_criteria": [
                    "Wiederholte Frage liefert mindestens eine belastbare Quelle.",
                    "Knowledge-Gap-Status kann nach fachlicher Pruefung geschlossen werden.",
                ],
            }
        )
    return actions[:10]


def _machine_gap_next_steps(row):
    """Return concrete remediation steps for a machine documentation gap."""
    machine = row.get("machine") or "die betroffene Maschine"
    steps = [
        f"Offene Fragen zu {machine} mit Instandhaltung und Produktion clustern.",
        "Bestaetigte Symptome, Ursachen und Abhilfen aus Tickets/Fehlern extrahieren.",
        "Maschinen-FAQ oder Handbuchauszug als freigegebene Knowledge-Quelle indexieren.",
    ]
    if row.get("related_error_count"):
        steps.insert(
            1,
            "Verknuepfte Fehlerhistorie pruefen und haeufige Fehlercodes priorisieren.",
        )
    return steps


def _machine_gap_success_criteria(row):
    """Return completion criteria for machine-gap remediation."""
    return [
        "Mindestens ein freigegebenes Dokument deckt Maschine und haeufige Frage ab.",
        "Top-Fragen liefern Quellen mit passender Maschinen-Metadatenabdeckung.",
        f"Offene Gap-Anzahl fuer {row.get('machine') or 'die Maschine'} sinkt im Review.",
    ]


def _error_gap_next_steps(row):
    """Return concrete remediation steps for a known error-code gap."""
    error_code = row.get("error_code") or "den Fehlercode"
    steps = [
        f"Fehler {error_code} mit bestaetigter Ursache und Abhilfe dokumentieren.",
        "Symptome, moegliche Ursachen, Sicherheitscheck und naechste Pruefschritte erfassen.",
        "Dokument mit Fehlercode, Maschine und Abteilung als Metadaten indexieren.",
        "Golden Test Question mit erwarteter Quelle fuer diesen Fehler ergaenzen.",
    ]
    if row.get("downtime_minutes"):
        steps.insert(1, "Stillstandsrelevante Eskalations- und Wiederanlaufhinweise aufnehmen.")
    return steps


def _uncovered_error_next_steps(row):
    """Return remediation steps for high-impact errors without knowledge coverage."""
    steps = _error_gap_next_steps(row)
    steps.insert(0, "High-Impact-Fehler wegen fehlender AI-Abdeckung priorisiert bearbeiten.")
    return steps


def _uncovered_machine_next_steps(row):
    """Return remediation steps for high-impact machines without knowledge coverage."""
    machine = row.get("machine") or "die kritische Maschine"
    return [
        f"Betriebs- und Wartungswissen zu {machine} aus Handbuch, Tasks und Fehlern sammeln.",
        "Typische Stoerbilder, Sicherheitspruefungen und Wiederanlaufhinweise dokumentieren.",
        "Maschinenquelle mit source_type=machine oder machine_manual indexieren.",
        "Golden Test Question mit erwarteter Maschinenquelle fuer diese Abdeckung ergaenzen.",
    ]


def _error_gap_success_criteria(row):
    """Return completion criteria for error-gap remediation."""
    error_code = row.get("error_code") or "der Fehler"
    return [
        f"{error_code} hat eine error-spezifische Knowledge-Quelle.",
        "RAG-Antwort nennt Ursache, naechste Schritte und Quelle statt No-Answer.",
        "Recall-Test findet die erwartete Quelle unter den Top-K Ergebnissen.",
    ]


def _documents_matching_machine(documents, machine):
    """Return documents whose metadata likely covers a machine."""
    machine_text = str(machine or "").strip().lower()
    if not machine_text:
        return []
    return [
        document
        for document in documents
        if machine_text
        in " ".join(
            [
                document.title or "",
                document.original_filename or "",
                document.department or "",
                document.source_type or "",
            ]
        ).lower()
    ]


def _documents_matching_machine_record(documents, machine):
    """Return documents whose metadata specifically covers one machine record."""
    if not machine:
        return []
    machine_name = str(machine.name or "").strip().lower()
    return [
        document
        for document in documents
        if _document_covers_machine(document, machine, machine_name)
    ]


def _document_covers_machine(document, machine, machine_name):
    """Return whether a document appears to cover a machine record."""
    source_type = str(document.source_type or "").strip().lower()
    if document.source_id == machine.id and source_type in MACHINE_DOCUMENT_SOURCE_TYPES:
        return True
    if not machine_name:
        return False
    return machine_name in _document_metadata_text(document)


def _documents_matching_error(documents, error_entry, require_error_specific=False):
    """Return documents whose metadata likely covers a known error entry."""
    needles = {
        str(error_entry.error_code or "").strip().lower(),
        str(error_entry.title or "").strip().lower(),
    }
    if not require_error_specific:
        needles.add(str(error_entry.machine or "").strip().lower())
    needles = {needle for needle in needles if needle}
    if not needles:
        return []
    return [
        document for document in documents if _document_covers_error(document, error_entry, needles)
    ]


def _document_covers_error(document, error_entry, needles):
    """Return whether a document appears to cover a specific error entry."""
    if document.source_id == error_entry.id and str(document.source_type or "").lower() in {
        "error",
        "error_entry",
        "error_catalog",
    }:
        return True
    metadata_text = _document_metadata_text(document)
    return any(needle in metadata_text for needle in needles)


def _document_metadata_text(document):
    """Return searchable metadata text for coverage heuristics."""
    return " ".join(
        [
            document.title or "",
            document.original_filename or "",
            document.department or "",
            document.source_type or "",
        ]
    ).lower()


def _gap_matches_error(gap, error_entry):
    """Return whether a knowledge gap points at a known error entry."""
    if gap.machine and error_entry.machine:
        if gap.machine.strip().lower() == error_entry.machine.strip().lower():
            return True

    haystack = " ".join(
        [
            gap.question or "",
            gap.context_text or "",
            gap.machine or "",
        ]
    ).lower()
    if error_entry.error_code and error_entry.error_code.lower() in haystack:
        return True

    gap_tokens = set(tokenize_text(haystack))
    error_tokens = set(
        tokenize_text(
            " ".join(
                [
                    error_entry.error_code or "",
                    error_entry.title or "",
                    error_entry.description or "",
                    error_entry.symptoms or "",
                    error_entry.possible_causes or "",
                ]
            )
        )
    )
    relevant_tokens = {token for token in gap_tokens & error_tokens if len(token) >= 4}
    return len(relevant_tokens) >= 2


def _related_errors_for_machine(machine):
    """Return count of error entries that mention the machine."""
    if not machine:
        return 0
    pattern = f"%{machine}%"
    return ErrorEntry.query.filter(ErrorEntry.machine.ilike(pattern)).count()


def _machine_id_for_name(machine):
    """Return the machine id for an exact machine-name match when available."""
    if not machine:
        return None
    row = Machine.query.filter(Machine.name.ilike(machine)).first()
    return row.id if row else None


def _coverage_label(document_count, gaps):
    """Return a simple coverage label for a machine gap cluster."""
    occurrence_count = sum(gap.occurrence_count or 0 for gap in gaps)
    if document_count == 0:
        return "missing"
    if document_count < 2 and occurrence_count > 1:
        return "thin"
    return "covered"


def _error_gap_priority(row):
    """Return action priority for an error-code knowledge gap."""
    if row.get("severity") in {"high", "critical"}:
        return "high"
    if (row.get("occurrence_count") or 0) > 1:
        return "high"
    if (row.get("downtime_minutes") or 0) > 0:
        return "medium"
    return "medium"


def _is_high_impact_error(error_entry):
    """Return whether an error entry should be reviewed for missing AI coverage."""
    return (
        error_entry.severity in {"high", "critical"}
        or (error_entry.repeat_count or 0) >= 2
        or (error_entry.downtime_minutes or 0) > 0
        or (error_entry.production_loss_minutes or 0) > 0
    )


def _is_high_impact_machine(machine):
    """Return whether a machine is important enough to require knowledge coverage."""
    criticality = str(machine.criticality or "").strip().lower()
    status = str(machine.status or "").strip().lower()
    return (
        criticality in HIGH_IMPACT_MACHINE_CRITICALITIES
        or status in HIGH_IMPACT_MACHINE_STATUSES
        or bool(machine.last_downtime_at)
    )


def _uncovered_error_priority(error_entry):
    """Return priority for a high-impact error without specific knowledge coverage."""
    if error_entry.severity in {"high", "critical"}:
        return "high"
    if (error_entry.repeat_count or 0) >= 3:
        return "high"
    if (error_entry.downtime_minutes or 0) >= 30:
        return "high"
    return "medium"


def _uncovered_machine_priority(machine):
    """Return action priority for a high-impact machine without knowledge coverage."""
    criticality = str(machine.criticality or "").strip().lower()
    status = str(machine.status or "").strip().lower()
    if criticality in HIGH_IMPACT_MACHINE_CRITICALITIES:
        return "high"
    if status in {"down", "failed", "fault", "offline", "stopped"}:
        return "high"
    return "medium"


def _error_impact_score(error_entry):
    """Return a deterministic impact score for sorting uncovered error gaps."""
    severity_weight = {"critical": 100, "high": 75, "medium": 35, "low": 10}.get(
        error_entry.severity,
        20,
    )
    return (
        severity_weight
        + min(error_entry.repeat_count or 0, 10) * 5
        + min(error_entry.downtime_minutes or 0, 240) / 4
        + min(error_entry.production_loss_minutes or 0, 240) / 6
    )


def _machine_impact_score(machine):
    """Return a deterministic impact score for sorting uncovered machine gaps."""
    criticality_weight = {"critical": 100, "high": 75, "normal": 20, "low": 10}.get(
        str(machine.criticality or "").strip().lower(),
        20,
    )
    status_weight = {
        "down": 80,
        "failed": 80,
        "fault": 70,
        "offline": 60,
        "stopped": 60,
        "maintenance": 35,
        "running": 0,
    }.get(str(machine.status or "").strip().lower(), 0)
    downtime_weight = 20 if machine.last_downtime_at else 0
    return criticality_weight + status_weight + downtime_weight


def _uncovered_error_reason(error_entry):
    """Return a compact admin-facing reason for an uncovered error gap."""
    signals = []
    if error_entry.severity in {"high", "critical"}:
        signals.append(f"Schweregrad {error_entry.severity}")
    if error_entry.repeat_count:
        signals.append(f"{error_entry.repeat_count} Wiederholung(en)")
    if error_entry.downtime_minutes:
        signals.append(f"{error_entry.downtime_minutes} Min. Stillstand")
    if error_entry.production_loss_minutes:
        signals.append(f"{error_entry.production_loss_minutes} Min. Produktionsverlust")
    detail = ", ".join(signals) or "relevanter Fehler"
    return f"{detail}, aber kein passendes Fehler-Knowledge-Dokument gefunden."


def _uncovered_machine_reason(machine):
    """Return a compact admin-facing reason for an uncovered machine gap."""
    signals = []
    if machine.criticality:
        signals.append(f"Kritikalitaet {machine.criticality}")
    if machine.status:
        signals.append(f"Status {machine.status}")
    if machine.last_downtime_at:
        signals.append("Stillstandshistorie vorhanden")
    detail = ", ".join(signals) or "High-Impact-Maschine"
    return f"{detail}, aber keine maschinenspezifische Knowledge-Quelle gefunden."


def _bounded_gap_question(gap):
    """Return a bounded example question for admin review."""
    return str(gap.question or "").strip()[:220]


def _bounded_int(value, default, minimum, maximum):
    """Return an integer constrained to a safe range."""
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _numeric_score(value):
    """Return a numeric score or None when unavailable."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
