"""Consolidated read model for the automated knowledge lifecycle."""

from collections import Counter

from app.models import AIFeedback, KnowledgeDocument, KnowledgeGap
from app.services.knowledge_aging_service import (
    knowledge_aging_summary,
)
from app.services.knowledge_quality_service import (
    KNOWLEDGE_QUALITY_STATUSES,
    retrieval_quality_gate_for_document,
)

INDEXED_STATUS = "indexed"
APPROVED_QUALITY_STATUS = "admin_approved"
DRAFT_QUALITY_STATUSES = {"draft", "ai_suggested"}
WEAK_QUALITY_STATUSES = {"low_quality", "duplicate", "outdated"}
PROBLEM_INDEX_STATUSES = {"error", "no_text", "pending", "stale"}

LIFECYCLE_STEP_DEFINITIONS = (
    {
        "key": "source_capture",
        "label": "Quelle entsteht",
        "status": "available",
        "services": [
            "knowledge_service",
            "document_knowledge_processing_service",
        ],
        "notes": (
            "Tasks, Fehler, Dokumente, Maschinen, Handovers und Trainings "
            "koennen als KnowledgeDocument registriert werden."
        ),
    },
    {
        "key": "draft_creation",
        "label": "Knowledge-Draft",
        "status": "available",
        "services": [
            "knowledge_service",
            "assistant_training_service",
            "document_knowledge_processing_service",
        ],
        "notes": "Neue KnowledgeDocument-Zeilen starten mit draft oder ai_suggested.",
    },
    {
        "key": "similarity_detection",
        "label": "Aehnliche Eintraege",
        "status": "partial",
        "services": ["error_service", "recurring_issue_service", "vector_store_service"],
        "notes": (
            "Fehleraehnlichkeit und RAG-Suche existieren; ein generischer "
            "Knowledge-Draft-Similarity-Endpunkt ist noch nicht zentralisiert."
        ),
    },
    {
        "key": "missing_information",
        "label": "Rueckfragen",
        "status": "available",
        "services": ["missing_information_service"],
        "notes": "Fehler- und manuelle Knowledge-Eingaben erhalten strukturierte Rueckfragen.",
    },
    {
        "key": "technician_review",
        "label": "Techniker bestaetigt",
        "status": "available",
        "services": ["knowledge_quality_service"],
        "notes": (
            "Techniker duerfen abteilungsbezogen technician_confirmed, "
            "low_quality, duplicate oder outdated setzen."
        ),
    },
    {
        "key": "admin_approval",
        "label": "Admin gibt frei",
        "status": "available",
        "services": ["knowledge_quality_service"],
        "notes": "Nur Master Admins duerfen admin_approved setzen.",
    },
    {
        "key": "rag_usage",
        "label": "RAG nutzt Wissen",
        "status": "available",
        "services": ["knowledge_service", "retrieval_service", "vector_store_service"],
        "notes": (
            "RAG nutzt indexierte und sichtbare Quellen mit zentralem " "Quality-Gate im Retrieval."
        ),
    },
    {
        "key": "feedback",
        "label": "Feedback verbessert Qualitaet",
        "status": "available",
        "services": ["ai_feedback_service", "ai_audit_service"],
        "notes": (
            "AI-Antwortfeedback wird mit Frage, Antwort, Quellen und " "Review-Status gespeichert."
        ),
    },
    {
        "key": "aging_review",
        "label": "Aging-Review",
        "status": "available",
        "services": ["knowledge_aging_service", "background_job_service"],
        "notes": (
            "Alte oder lange nicht bestaetigte KnowledgeDocuments koennen "
            "als outdated markiert und im Retrieval schwaecher gewichtet werden."
        ),
    },
    {
        "key": "knowledge_gaps",
        "label": "Wissensluecken",
        "status": "available",
        "services": ["knowledge_gap_service"],
        "notes": (
            "Unbeantwortete oder niedrig-konfidente AI-Fragen erzeugen "
            "deduplizierte KnowledgeGap-Eintraege."
        ),
    },
)


def knowledge_lifecycle_steps():
    """Return stable descriptors for the supported knowledge lifecycle steps."""
    return [dict(step) for step in LIFECYCLE_STEP_DEFINITIONS]


def knowledge_lifecycle_overview(documents=None):
    """Return admin-facing lifecycle counters built from existing services and models."""
    document_items = _document_items(documents)
    status_counts = _counter_for_field(document_items, "status")
    quality_status_counts = _quality_status_counts(document_items)
    indexed_documents = [
        document for document in document_items if document.status == INDEXED_STATUS
    ]
    admin_approved_indexed = [
        document
        for document in indexed_documents
        if document.quality_status == APPROVED_QUALITY_STATUS
    ]
    quality_allowed_indexed = [
        document
        for document in indexed_documents
        if retrieval_quality_gate_for_document(document).allowed
    ]
    quality_weighted_indexed = [
        document
        for document in quality_allowed_indexed
        if retrieval_quality_gate_for_document(document).score_multiplier < 1
    ]
    quality_blocked_indexed = [
        document
        for document in indexed_documents
        if not retrieval_quality_gate_for_document(document).allowed
    ]
    full_strength_indexed = [
        document
        for document in indexed_documents
        if retrieval_quality_gate_for_document(document).score_multiplier == 1
    ]
    non_approved_indexed = len(indexed_documents) - len(admin_approved_indexed)
    problem_count = sum(
        1 for document in document_items if document.status in PROBLEM_INDEX_STATUSES
    )
    aging_summary = knowledge_aging_summary(document_items)
    return {
        "documents": len(document_items),
        "indexed_documents": len(indexed_documents),
        "drafts": _draft_count(quality_status_counts),
        "technician_confirmed": quality_status_counts.get("technician_confirmed", 0),
        "admin_approved": quality_status_counts.get(APPROVED_QUALITY_STATUS, 0),
        "low_quality": quality_status_counts.get("low_quality", 0),
        "duplicate": quality_status_counts.get("duplicate", 0),
        "outdated": quality_status_counts.get("outdated", 0),
        "rejected": quality_status_counts.get("rejected", 0),
        "problem_documents": problem_count,
        "feedback_open": _open_feedback_count(),
        "knowledge_gaps_open": _open_gap_count(),
        "status_counts": status_counts,
        "quality_status_counts": quality_status_counts,
        "review_queue": _review_queue(quality_status_counts, aging_summary),
        "aging": aging_summary,
        "rag_quality_gate": {
            "enabled": True,
            "approved_indexed_documents": len(full_strength_indexed),
            "admin_approved_indexed_documents": len(admin_approved_indexed),
            "non_approved_indexed_documents": non_approved_indexed,
            "quality_allowed_indexed_documents": len(quality_allowed_indexed),
            "quality_weighted_indexed_documents": len(quality_weighted_indexed),
            "quality_blocked_indexed_documents": len(quality_blocked_indexed),
            "reason": (
                "RAG blockiert rejected, verwendet admin_approved und "
                "technician_confirmed mit voller Staerke und gewichtet "
                "ai_suggested, draft, low_quality, duplicate sowie "
                "outdated niedriger."
            ),
        },
        "steps": knowledge_lifecycle_steps(),
        "next_actions": _next_actions(
            quality_status_counts,
            problem_count,
            non_approved_indexed,
            aging_summary,
        ),
    }


def _document_items(documents):
    """Return a list of knowledge documents, querying when no list is provided."""
    if documents is None:
        return KnowledgeDocument.query.order_by(KnowledgeDocument.id.asc()).all()
    return list(documents)


def _counter_for_field(documents, field_name):
    """Return a plain counter for a document attribute."""
    return dict(Counter(str(getattr(document, field_name) or "") for document in documents))


def _quality_status_counts(documents):
    """Return quality-status counts with known statuses always present."""
    counts = Counter(str(document.quality_status or "draft") for document in documents)
    for status in KNOWLEDGE_QUALITY_STATUSES:
        counts.setdefault(status, 0)
    return dict(sorted(counts.items()))


def _draft_count(quality_status_counts):
    """Return how many documents still need first editorial review."""
    return sum(quality_status_counts.get(status, 0) for status in DRAFT_QUALITY_STATUSES)


def _review_queue(quality_status_counts, aging_summary=None):
    """Return counts for the editorial review handoff."""
    aging_summary = aging_summary or {}
    return {
        "needs_technician_review": _draft_count(quality_status_counts),
        "needs_admin_approval": quality_status_counts.get("technician_confirmed", 0),
        "needs_quality_review": sum(
            quality_status_counts.get(status, 0) for status in WEAK_QUALITY_STATUSES
        ),
        "needs_refresh": quality_status_counts.get("outdated", 0),
        "needs_aging_review": int(aging_summary.get("stale_candidates") or 0),
        "low_quality": quality_status_counts.get("low_quality", 0),
        "duplicate": quality_status_counts.get("duplicate", 0),
        "rejected": quality_status_counts.get("rejected", 0),
    }


def _open_feedback_count():
    """Return the count of AI feedback items waiting for review."""
    return AIFeedback.query.filter(AIFeedback.review_status == "open").count()


def _open_gap_count():
    """Return the count of open knowledge gaps."""
    return KnowledgeGap.query.filter(KnowledgeGap.status == "open").count()


def _next_actions(quality_status_counts, problem_count, non_approved_indexed, aging_summary):
    """Return compact admin actions derived from the lifecycle counters."""
    actions = []
    if aging_summary.get("stale_candidates"):
        actions.append("Aging-Review ausfuehren und alte Eintraege neu bestaetigen.")
    if problem_count:
        actions.append("Indexprobleme in Knowledge-Dokumenten pruefen.")
    if _draft_count(quality_status_counts):
        actions.append("Drafts durch Techniker reviewen lassen.")
    if quality_status_counts.get("technician_confirmed", 0):
        actions.append("Technikerbestaetigte Eintraege als Admin freigeben oder ablehnen.")
    if quality_status_counts.get("outdated", 0):
        actions.append("Veraltete Eintraege aktualisieren und neu indexieren.")
    if quality_status_counts.get("low_quality", 0):
        actions.append("Low-Quality Quellen pruefen, neu extrahieren oder ablehnen.")
    if quality_status_counts.get("duplicate", 0):
        actions.append("Doppelte Quellen zusammenfuehren oder blockieren.")
    if non_approved_indexed:
        actions.append("Nicht admin-freigegebene RAG-Quellen fachlich reviewen.")
    if not actions:
        actions.append("Lifecycle ist aktuell ohne offene Review- oder Indexsignale.")
    return actions
