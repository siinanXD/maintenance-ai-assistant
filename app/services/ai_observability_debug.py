"""Prompt-safe debug views of one chat request for the AI admin."""

from __future__ import annotations

from app.services.ai_answer_quality_service import answer_quality_from_history_item
from app.services.ai_observability_chats import answer_uncertainty, confidence_payload
from app.services.ai_observability_common import bounded
from app.services.ai_observability_sources import (
    build_score_summary,
    build_source_rows,
    retrieval_duration_ms,
    source_label,
    source_reference,
)
from app.services.ai_prompting import text_system_prompt


def debug_tools(chats, chat_message_id):
    """Return selected request details for step-by-step debugging."""
    selected = _selected_chat(chats, chat_message_id)
    if not selected:
        return {
            "selected_chat_message_id": None,
            "request_analysis": None,
            "prompt_blueprint": None,
            "available_requests": [],
        }
    return {
        "selected_chat_message_id": selected.id,
        "request_analysis": _request_analysis(selected),
        "prompt_blueprint": _prompt_blueprint(selected),
        "available_requests": [
            {
                "answer_uncertainty": answer_uncertainty(chat),
                "chat_message_id": chat.id,
                "confidence": confidence_payload(chat),
                "created_at": chat.created_at.isoformat(),
                "question": bounded(chat.message, 160),
                "confidence_level": chat.confidence_level,
                "source_count": chat.source_count,
            }
            for chat in chats[:20]
        ],
    }


def _selected_chat(chats, chat_message_id):
    """Return the requested chat or the newest available chat."""
    if not chats:
        return None
    if chat_message_id is None:
        return chats[0]
    for chat in chats:
        if chat.id == chat_message_id:
            return chat
    return chats[0]


def _request_analysis(chat):
    """Return one request analysis with retrieval, confidence, and safety signals."""
    diagnostics = chat.diagnostics()
    event = chat.audit_event
    explainability = (
        event.retrieval_explainability()
        if event
        else (diagnostics.get("retrieval_explainability") or {})
    )
    context_builder = (
        explainability.get("context_builder") if isinstance(explainability, dict) else {}
    )
    query_understanding = (
        (explainability.get("query_understanding") if isinstance(explainability, dict) else {})
        or diagnostics.get("query_understanding")
        or {}
    )
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    answer_quality = answer_quality_from_history_item(chat.to_dict())
    return {
        "question": bounded(chat.message, 500),
        "answer_preview": bounded(chat.response, 700),
        "answer_quality": answer_quality,
        "query_understanding": query_understanding,
        "retrieval": {
            "source_count": chat.source_count,
            "retrieval_duration_ms": retrieval_duration_ms(event) if event else 0,
            "sources": [source_reference(source) for source in (sources or [])[:10]],
            "score_summary": build_score_summary(build_source_rows([event]) if event else []),
        },
        "context_builder": {
            "stats": (context_builder or {}).get("stats", {}),
            "sections": _context_sections(context_builder),
            "explainability": (context_builder or {}).get("explainability", {}),
        },
        "confidence": confidence_payload(chat, answer_quality),
        "quality_warnings": diagnostics.get("quality_warnings") or [],
        "safety": (explainability or {}).get("safety", {}),
        "post_generation_safety": (explainability or {}).get("post_generation_safety", {}),
    }


def _prompt_blueprint(chat):
    """Return a bounded prompt blueprint without raw chunk text."""
    diagnostics = chat.diagnostics()
    event = chat.audit_event
    explainability = (
        event.retrieval_explainability()
        if event
        else (diagnostics.get("retrieval_explainability") or {})
    )
    context_builder = (
        explainability.get("context_builder") if isinstance(explainability, dict) else {}
    )
    sources = explainability.get("sources") if isinstance(explainability, dict) else []
    return {
        "system_prompt": text_system_prompt(),
        "user_question": bounded(chat.message, 1000),
        "context_visibility": "source references and context-builder sections only",
        "context_sections": _context_sections(context_builder),
        "source_references": [source_reference(source) for source in (sources or [])[:10]],
        "prompt_preview": (
            "Kontext: "
            + bounded(_context_preview(context_builder, sources), 1200)
            + "\n\nFrage: "
            + bounded(chat.message, 500)
        ),
    }


def _context_sections(context_builder):
    """Return context-builder sections without full context text."""
    if not isinstance(context_builder, dict):
        return []
    sections = context_builder.get("sections") or []
    return [
        {
            "label": bounded(section.get("label") or section.get("type"), 120),
            "source_count": section.get("source_count"),
            "used_chars": section.get("used_chars"),
            "truncated": bool(section.get("truncated")),
        }
        for section in sections[:12]
        if isinstance(section, dict)
    ]


def _context_preview(context_builder, sources):
    """Return a compact context preview based on section and source metadata."""
    sections = _context_sections(context_builder)
    section_labels = [section["label"] for section in sections if section.get("label")]
    source_labels = [source_label(source) for source in (sources or [])[:8]]
    parts = []
    if section_labels:
        parts.append("Sections: " + ", ".join(section_labels))
    if source_labels:
        parts.append("Sources: " + ", ".join(source_labels))
    return " | ".join(parts) if parts else "Keine gespeicherten Kontext-Metadaten."
