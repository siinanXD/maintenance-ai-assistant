"""Error assistant service.

Provides structured cause-and-fix lookup from the error catalog based
on free-text machine fault descriptions.

Local implementation
    Uses token-similarity ranking plus exact error-code fallback.
    No external AI call is made in this mode.

Future AI integration hook
    When a non-mock AI provider is configured, ``_try_ai_enhance()``
    calls ``BaseAIProvider.error_assistant_query()``, which can return
    richer causes, fixes, and a plain-language summary.  The service
    merges those into the response and sets ``diagnostics.ai_enhanced``
    to ``True``.  No code change is needed in this file to activate it —
    just configure a real provider via ``OPENAI_API_KEY`` in ``.env``.
"""

import logging
import re

from app.security import has_dashboard_permission
from app.services.error_service import (
    parse_similarity_limit,
    search_errors,
    suggest_similar_errors,
)
from app.services.retrieval_service import knowledge_context_for_chat
from app.services.text_normalization_service import normalize_text, tokenize_text

logger = logging.getLogger(__name__)

_MAX_QUERY_LENGTH = 1000
_DEFAULT_LIMIT = 5
_MAX_AGGREGATION = 5
_HIGH_CONFIDENCE_SCORE = 75
_MEDIUM_CONFIDENCE_SCORE = 45


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------


def _extract_error_code(text):
    """Return the first probable error code (e.g. E42, F001, 4711) from text."""
    match = re.search(r"\b([A-Z]{0,2}\d{2,5})\b", text.upper())
    return match.group(1) if match else None


def _extract_machine_name(text):
    """Return a machine or plant label extracted from text, or empty string."""
    match = re.search(
        r"(maschine|anlage|machine|unit|linie|presse)\s+[\w-]+",
        text,
        re.IGNORECASE,
    )
    return match.group(0).strip() if match else ""


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


def _aggregate_causes_and_fixes(matches):
    """Return deduplicated causes and fixes from a list of scored match dicts."""
    causes = []
    fixes = []
    seen_causes = set()
    seen_fixes = set()

    for match in matches:
        entry = match["entry"]

        cause = (entry.get("possible_causes") or "").strip()
        if cause and cause not in seen_causes:
            causes.append(cause)
            seen_causes.add(cause)

        fix = (entry.get("solution") or "").strip()
        if fix and fix not in seen_fixes:
            fixes.append(fix)
            seen_fixes.add(fix)

    return causes[:_MAX_AGGREGATION], fixes[:_MAX_AGGREGATION]


def _root_cause_analysis(query, matches, causes, fixes, rag_sources, history_evidence=None):
    """Return a structured root-cause-analysis payload from visible evidence."""
    history = history_evidence or _empty_history_evidence()
    confidence = _rca_confidence(matches, causes, rag_sources, history)
    possible_causes = _rca_possible_causes(matches, causes)
    similar_cases = _rca_similar_cases(matches)
    next_steps = _rca_next_steps(fixes, confidence, history, matches)
    insufficient_evidence = not possible_causes and not similar_cases
    return {
        "summary": _rca_summary(
            query,
            possible_causes,
            similar_cases,
            confidence,
            history,
        ),
        "possible_causes": possible_causes,
        "similar_cases": similar_cases,
        "next_steps": next_steps,
        "confidence": confidence,
        "insufficient_evidence": insufficient_evidence,
        "evidence": {
            "catalog_match_count": len(matches),
            "rag_source_count": len(rag_sources or []),
            "history_source_count": history["source_count"],
            "uses_only_visible_sources": True,
            "similar_case_sources": _rca_similar_case_sources(matches),
            "rag_sources": _rca_rag_source_references(rag_sources),
            "history": history,
        },
    }


def _rca_possible_causes(matches, causes):
    """Return ranked possible causes with confidence and source references."""
    cause_rows = []
    seen = set()
    for match in matches:
        entry = match.get("entry") or {}
        cause = str(entry.get("possible_causes") or "").strip()
        if not cause or cause in seen:
            continue
        seen.add(cause)
        cause_rows.append(
            {
                "cause": cause,
                "confidence": _confidence_level(_safe_score(match.get("score"))),
                "score": _safe_score(match.get("score")),
                "evidence": str(match.get("reason") or "Aehnlicher Fehlerfall")[:240],
                "source": _match_source_reference(entry),
            }
        )
        if len(cause_rows) >= _MAX_AGGREGATION:
            return cause_rows

    for cause in causes:
        cause_text = str(cause or "").strip()
        if cause_text and cause_text not in seen:
            seen.add(cause_text)
            cause_rows.append(
                {
                    "cause": cause_text,
                    "confidence": "low",
                    "score": 25,
                    "evidence": "Aus sichtbaren Ursachen aggregiert",
                    "source": {},
                }
            )
        if len(cause_rows) >= _MAX_AGGREGATION:
            break
    return cause_rows


def _rca_similar_cases(matches):
    """Return compact references to similar visible catalog cases."""
    cases = []
    for match in matches[:_MAX_AGGREGATION]:
        entry = match.get("entry") or {}
        cases.append(
            {
                "id": entry.get("id"),
                "machine": entry.get("machine") or "",
                "error_code": entry.get("error_code") or "",
                "title": entry.get("title") or "",
                "status": entry.get("status") or "",
                "score": _safe_score(match.get("score")),
                "reason": str(match.get("reason") or "")[:240],
                "created_at": entry.get("created_at"),
            }
        )
    return cases


def _rca_similar_case_sources(matches):
    """Return prompt-safe source references for visible similar error cases."""
    sources = []
    for match in matches[:_MAX_AGGREGATION]:
        entry = match.get("entry") or {}
        reference = _match_source_reference(entry)
        reference["score"] = _safe_score(match.get("score"))
        reference["reason"] = str(match.get("reason") or "")[:240]
        sources.append(reference)
    return sources


def _rca_rag_source_references(rag_sources):
    """Return prompt-safe source references for RAG evidence used by RCA."""
    references = []
    for source in (rag_sources or [])[:_MAX_AGGREGATION]:
        references.append(
            {
                "type": source.get("type") or source.get("source_type") or "",
                "id": source.get("id"),
                "source_type": source.get("source_type") or source.get("type") or "",
                "source_id": source.get("source_id") or source.get("id"),
                "chunk_id": source.get("chunk_id"),
                "title": str(source.get("title") or "")[:220],
                "module": source.get("module") or "",
                "machine_id": source.get("machine_id"),
                "role_visibility": source.get("role_visibility") or "",
                "created_at": source.get("created_at") or "",
                "score": _safe_score(source.get("score") or source.get("relevance")),
            }
        )
    return references


def _rca_next_steps(fixes, confidence, history_evidence=None, matches=None):
    """Return practical next steps grounded in fixes and confidence."""
    steps = []
    for fix in fixes[:3]:
        text = str(fix or "").strip()
        if text:
            steps.append(
                _rca_step(
                    text,
                    "high",
                    "similar_case_solution",
                    **_rca_fix_source_metadata(text, matches),
                )
            )
    history = history_evidence or _empty_history_evidence()
    if history["tasks"]:
        task = history["tasks"][0]
        steps.append(
            _rca_step(
                (
                    "Offene oder aktuelle Tasks zur Maschine mit der "
                    "Stoerungsdiagnose abgleichen."
                ),
                "high",
                "visible_task_history",
                source_id=task.get("id"),
                title=task.get("title"),
                due_date=task.get("due_date"),
            )
        )
    if history["shift_handovers"]:
        handover = history["shift_handovers"][0]
        steps.append(
            _rca_step(
                (
                    "Letzte Schichtuebergaben auf wiederkehrende Symptome und "
                    "Folgeaufgaben pruefen."
                ),
                "medium",
                "visible_shift_handover_history",
                source_id=handover.get("id"),
                title=handover.get("title"),
                due_date=handover.get("shift_date"),
            )
        )
    if confidence["level"] == "low":
        steps.append(
            _rca_step(
                (
                    "Stoerungsbild, Fehlercode, Maschine und letzte Arbeiten genauer erfassen, "
                    "bevor eine Ursache festgelegt wird."
                ),
                "high",
                "low_confidence_guardrail",
            )
        )
    steps.append(
        _rca_step(
            "Befund und durchgefuehrte Pruefung im Fehlerkatalog oder Task dokumentieren.",
            "medium",
            "maintenance_workflow",
        )
    )
    return steps[:_MAX_AGGREGATION]


def _rca_step(step, priority, source, **metadata):
    """Return one bounded RCA next-step payload."""
    payload = {
        "step": str(step or "").strip()[:500],
        "priority": str(priority or "medium")[:40],
        "source": str(source or "")[:80],
    }
    for key in ("source_id", "title", "error_code", "due_date"):
        value = metadata.get(key)
        if value not in (None, ""):
            payload[key] = value
    return payload


def _rca_fix_source_metadata(fix, matches):
    """Return source metadata for a fix that came from a visible similar case."""
    normalized_fix = str(fix or "").strip()
    for match in matches or []:
        entry = match.get("entry") or {}
        if str(entry.get("solution") or "").strip() != normalized_fix:
            continue
        return {
            "source_id": entry.get("id"),
            "title": entry.get("title") or "",
            "error_code": entry.get("error_code") or "",
        }
    return {}


def _rca_confidence(matches, causes, rag_sources, history_evidence=None):
    """Return an RCA confidence score from catalog and RAG evidence."""
    top_score = max((_safe_score(match.get("score")) for match in matches), default=0)
    history_count = (history_evidence or _empty_history_evidence())["source_count"]
    score = min(
        100,
        int(top_score * 0.7)
        + min(len(matches), 3) * 8
        + min(len(causes), 3) * 5
        + min(len(rag_sources or []), 3) * 4
        + min(history_count, 3) * 4,
    )
    level = _confidence_level(score)
    if score == 0:
        reason = "Keine sichtbare Fehlerhistorie oder RAG-Quelle gefunden"
    elif level == "high":
        reason = "Starke Uebereinstimmung mit sichtbaren Fehlerfaellen"
    elif level == "medium":
        reason = "Teilweise passende Fehlerhistorie vorhanden"
    else:
        reason = "Schwache Quellenlage; Ergebnis nur als Hypothese verwenden"
    return {
        "score": score,
        "level": level,
        "uncertainty": _rca_uncertainty(level),
        "reason": reason,
    }


def _rca_uncertainty(confidence_level):
    """Return uncertainty aligned with RCA confidence."""
    if confidence_level == "high":
        return "low"
    if confidence_level == "medium":
        return "medium"
    return "high"


def _rca_summary(query, possible_causes, similar_cases, confidence, history_evidence=None):
    """Return a short RCA summary without inventing unsupported details."""
    if not possible_causes:
        return (
            "Keine belastbare Root-Cause-Hypothese aus sichtbarer Historie gefunden. "
            "Weitere Diagnoseinformationen sind erforderlich."
        )
    top_cause = possible_causes[0]["cause"]
    case_count = len(similar_cases)
    history_count = (history_evidence or _empty_history_evidence())["source_count"]
    history_text = f", {history_count} sichtbare Historienquellen" if history_count else ""
    return (
        f"Wahrscheinlichste Hypothese: {top_cause}. "
        f"Basis: {case_count} aehnliche sichtbare Faelle{history_text}, Confidence "
        f"{confidence['level']} ({confidence['score']}/100)."
    )


def _machine_history_evidence(query, user, matches, machine_name):
    """Return visible task and handover history relevant for RCA grounding."""
    machine_hints = _history_machine_hints(query, matches, machine_name)
    query_tokens = set(tokenize_text(" ".join([query, *machine_hints])))
    tasks = _history_task_sources(user, query_tokens, machine_hints)
    handovers = _history_handover_sources(user, query_tokens, machine_hints)
    source_types = []
    if tasks:
        source_types.append("task")
    if handovers:
        source_types.append("shift_handover")
    return {
        "source_count": len(tasks) + len(handovers),
        "source_types": source_types,
        "tasks": tasks,
        "shift_handovers": handovers,
        "uses_only_visible_sources": True,
    }


def _empty_history_evidence():
    """Return a stable empty history-evidence payload."""
    return {
        "source_count": 0,
        "source_types": [],
        "tasks": [],
        "shift_handovers": [],
        "uses_only_visible_sources": True,
    }


def _history_machine_hints(query, matches, machine_name):
    """Return normalized machine hints from the query and visible matches."""
    hints = []
    for value in (machine_name, query):
        extracted = _extract_machine_name(str(value or ""))
        if extracted and extracted not in hints:
            hints.append(extracted)
    for match in matches[:_MAX_AGGREGATION]:
        machine = str((match.get("entry") or {}).get("machine") or "").strip()
        if machine and machine not in hints:
            hints.append(machine)
    return hints[:_MAX_AGGREGATION]


def _history_task_sources(user, query_tokens, machine_hints):
    """Return visible task history rows related to the RCA query."""
    if not has_dashboard_permission(user, "tasks", "view"):
        return []
    from app.models import Task
    from app.services.task_service import visible_tasks_query

    tasks = (
        visible_tasks_query(user).order_by(Task.updated_at.desc(), Task.id.desc()).limit(40).all()
    )
    rows = [
        _task_history_payload(task)
        for task in tasks
        if _history_matches(_task_history_text(task), query_tokens, machine_hints)
    ]
    return rows[:3]


def _history_handover_sources(user, query_tokens, machine_hints):
    """Return visible shift-handover rows related to the RCA query."""
    if not has_dashboard_permission(user, "shiftplans", "view"):
        return []
    from app.handover.services import visible_handovers_query
    from app.models import ShiftHandover

    handovers = (
        visible_handovers_query(user)
        .order_by(ShiftHandover.shift_date.desc(), ShiftHandover.id.desc())
        .limit(40)
        .all()
    )
    rows = [
        _handover_history_payload(handover)
        for handover in handovers
        if _history_matches(_handover_history_text(handover), query_tokens, machine_hints)
    ]
    return rows[:3]


def _history_matches(text, query_tokens, machine_hints):
    """Return whether visible history text is relevant to the RCA query."""
    normalized_text = normalize_text(text)
    normalized_hints = [normalize_text(hint) for hint in machine_hints if hint]
    if any(hint and hint in normalized_text for hint in normalized_hints):
        return True
    overlap = set(tokenize_text(text)) & set(query_tokens or set())
    return len(overlap) >= 3


def _task_history_text(task):
    """Return searchable task history text."""
    return " ".join(
        str(part or "")
        for part in (
            task.title,
            task.description,
            task.blocked_reason,
            task.priority.value if task.priority else "",
            task.status.value if task.status else "",
        )
    )


def _handover_history_text(handover):
    """Return searchable handover history text."""
    return " ".join(
        str(part or "")
        for part in (
            handover.area,
            handover.machine.name if handover.machine else "",
            handover.content,
            handover.open_tasks,
            handover.machine_notes,
            handover.next_notes,
            handover.cause,
            handover.action_taken,
            handover.follow_up_task,
        )
    )


def _task_history_payload(task):
    """Return prompt-safe task history evidence for RCA."""
    return {
        "type": "task",
        "id": task.id,
        "title": task.title,
        "status": task.status.value if task.status else "",
        "priority": task.priority.value if task.priority else "",
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }


def _handover_history_payload(handover):
    """Return prompt-safe shift-handover history evidence for RCA."""
    return {
        "type": "shift_handover",
        "id": handover.id,
        "title": f"Schichtuebergabe {handover.shift_date.isoformat()}",
        "status": handover.status,
        "machine_id": handover.machine_id,
        "shift_date": handover.shift_date.isoformat(),
        "open_tasks": str(handover.open_tasks or "")[:220],
        "next_notes": str(handover.next_notes or "")[:220],
    }


def _match_source_reference(entry):
    """Return a compact source reference for an error-catalog match."""
    return {
        "type": "error",
        "id": entry.get("id"),
        "title": entry.get("title") or "",
        "machine": entry.get("machine") or "",
        "error_code": entry.get("error_code") or "",
    }


def _confidence_level(score):
    """Return low, medium or high for an RCA score."""
    numeric_score = _safe_score(score)
    if numeric_score >= _HIGH_CONFIDENCE_SCORE:
        return "high"
    if numeric_score >= _MEDIUM_CONFIDENCE_SCORE:
        return "medium"
    return "low"


def _safe_score(value):
    """Return a bounded integer score."""
    try:
        score = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 100))


def _exact_code_fallback(error_code, user, limit):
    """Return scored match dicts from a direct error-code catalog search."""
    if not error_code:
        return []
    entries = search_errors(error_code, user)
    return [
        {
            "entry": entry.to_dict(),
            "score": 50,
            "reason": "Fehlercode direkt gefunden",
        }
        for entry in entries[:limit]
    ]


# ---------------------------------------------------------------------------
# AI enhancement hook
# ---------------------------------------------------------------------------


def _try_ai_enhance(query, matches):
    """Call the configured AI provider for enhanced results, or return None.

    The mock provider always returns None.  A real OpenAI provider returns a
    dict with keys ``causes``, ``fixes``, and optionally ``summary``.
    Any exception from the provider is caught so local results remain valid.
    """
    from app.services.ai_service import get_ai_provider

    try:
        provider = get_ai_provider()
        result = provider.error_assistant_query(query, matches)
        if result and isinstance(result, dict):
            return {
                "causes": result.get("causes", []),
                "fixes": result.get("fixes", []),
                "summary": result.get("summary", ""),
                "provider": provider.name,
            }
        return None
    except Exception:
        logger.debug("error_assistant ai_enhance skipped — provider not available")
        return None


def _task_draft_from_fault(query, user, causes, fixes):
    """Return a read-only task draft for a fault query when permitted."""
    from app.security import has_dashboard_permission
    from app.services.ai_provider_mock import MockAIProvider

    if not has_dashboard_permission(user, "tasks", "write"):
        return None

    enriched_text = "\n".join(
        part
        for part in (
            query,
            f"Moegliche Ursache: {causes[0]}" if causes else "",
            f"Empfohlene Pruefung: {fixes[0]}" if fixes else "",
        )
        if part
    )
    suggestion = MockAIProvider().suggest_task(
        enriched_text,
        {
            "role": user.role.value,
            "department": user.department.name if user.department else "",
        },
    )
    return {
        "type": "task_draft",
        "label": "Task-Entwurf aus Stoerung",
        "target": "tasks",
        "url": "/tasks",
        "payload": suggestion,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_error_assistant(data, user):
    """Return cause-and-fix suggestions for a free-text fault query.

    Steps:
      1. Validate and sanitize the query string.
      2. Extract error-code and machine-name signals.
      3. Run similarity-ranked catalog search (department-scoped).
      4. Fall back to exact code search when similarity yields nothing.
      5. Attempt AI enhancement (no-op when mock provider is active).
      6. Aggregate unique causes and fixes from top matches.

    Returns:
        (result_dict, None, 200)              on success
        (None, {"error": "..."}, 400)         on validation failure

    """
    query = str(data.get("query") or "").strip()
    if not query:
        return None, {"error": "query is required"}, 400
    if len(query) > _MAX_QUERY_LENGTH:
        return (
            None,
            {"error": f"query must not exceed {_MAX_QUERY_LENGTH} characters"},
            400,
        )

    try:
        limit = parse_similarity_limit(data.get("limit", _DEFAULT_LIMIT))
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    error_code = _extract_error_code(query)
    machine_name = _extract_machine_name(query)

    # Primary: token-similarity search across the visible error catalog
    similarity_result, error, status = suggest_similar_errors(
        {"text": query, "machine": machine_name, "limit": limit},
        user,
    )
    if error:
        return None, error, status

    matches = similarity_result["results"]

    # Fallback: exact error-code lookup when similarity returns nothing
    if not matches:
        matches = _exact_code_fallback(error_code, user, limit)

    causes, fixes = _aggregate_causes_and_fixes(matches)
    rag_context, rag_sources = knowledge_context_for_chat(query, user)

    # AI enhancement path — activated automatically when a real provider is configured
    ai_enhanced = False
    ai_provider_name = "local_similarity"
    ai_result = _try_ai_enhance(query, matches)
    if ai_result:
        causes = ai_result["causes"] or causes
        fixes = ai_result["fixes"] or fixes
        ai_enhanced = True
        ai_provider_name = ai_result.get("provider", "openai")

    diagnostics = {
        "status": "local_search" if not ai_enhanced else "ai_enhanced",
        "provider": ai_provider_name,
        "match_count": len(matches),
        "extracted_error_code": error_code,
        "extracted_machine": machine_name or None,
        "ai_enhanced": ai_enhanced,
        "rag_source_count": len(rag_sources),
    }
    history_evidence = _machine_history_evidence(query, user, matches, machine_name)
    diagnostics["history_source_count"] = history_evidence["source_count"]
    root_cause_analysis = _root_cause_analysis(
        query,
        matches,
        causes,
        fixes,
        rag_sources,
        history_evidence,
    )
    diagnostics["root_cause_confidence"] = root_cause_analysis["confidence"]

    logger.info(
        "error_assistant query_len=%s matches=%s ai_enhanced=%s user_id=%s",
        len(query),
        len(matches),
        ai_enhanced,
        getattr(user, "id", "?"),
    )

    return (
        {
            "query": query,
            "matches": matches,
            "causes": causes,
            "fixes": fixes,
            "root_cause_analysis": root_cause_analysis,
            "sources": rag_sources,
            "rag_context": rag_context,
            "action_preview": _task_draft_from_fault(query, user, causes, fixes),
            "diagnostics": diagnostics,
        },
        None,
        200,
    )
