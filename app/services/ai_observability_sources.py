"""Retrieval source rows for AI observability: hits, scores, freshness, actions."""

from __future__ import annotations

from collections import Counter

from app.services.ai_observability_common import (
    LOW_SCORE_THRESHOLD,
    LOW_SIMILARITY_THRESHOLD,
    NEGATIVE_RATINGS,
    average,
    bounded,
    counter_rows,
    knowledge_title,
    optional_float,
    optional_int,
    rate,
    source_age_days,
)
from app.services.knowledge_aging_service import knowledge_aging_policy


def build_retrieval_monitoring(events, feedback_entries, limit):
    """Return retrieval hit, score, chunk, and document usage details."""
    source_rows = build_source_rows(events)
    source_freshness = source_freshness_summary(source_rows)
    stale_sources = stale_source_rows(source_rows, limit)
    undated_sources = undated_source_rows(source_rows, limit)
    chunk_counter = Counter()
    document_counter = Counter()
    for row in source_rows:
        if row.get("chunk_id") is not None:
            chunk_counter[(row["source_id"], row["chunk_id"], row["source_type"])] += 1
        if row.get("source_id") is not None:
            document_counter[(row["source_type"], row["source_id"])] += 1
    negative_feedback_ids = negative_feedback_event_ids(feedback_entries)
    poor_hits = poor_hit_rows(source_rows, negative_feedback_ids, limit)
    score_summary = build_score_summary(source_rows)
    retrieval_quality_actions = build_retrieval_quality_actions(
        poor_hits,
        score_summary,
    )
    metadata_quality_actions = source_metadata_quality_actions(
        source_freshness,
        stale_sources,
        undated_sources,
    )
    return {
        "top_hits": _top_hit_rows(source_rows, limit),
        "poor_hits": poor_hits,
        "score_summary": score_summary,
        "retrieval_quality_actions": retrieval_quality_actions,
        "source_freshness": source_freshness,
        "stale_sources": stale_sources,
        "undated_sources": undated_sources,
        "metadata_quality_actions": metadata_quality_actions,
        "action_summary": _retrieval_action_summary(
            retrieval_quality_actions + metadata_quality_actions,
        ),
        "chunk_usage": _chunk_usage_rows(chunk_counter, limit),
        "frequently_used_documents": document_usage_rows(document_counter, limit),
    }


def build_reranking_metrics(events):
    """Return aggregate prompt-safe reranking diagnostics from audit metadata."""
    rows = []
    for event in events:
        explainability = event.retrieval_explainability()
        debug = explainability.get("retrieval_debug") if isinstance(explainability, dict) else {}
        reranking = debug.get("reranking") if isinstance(debug, dict) else {}
        if not isinstance(reranking, dict):
            continue
        rows.append(
            {
                "candidate_limit": optional_int(reranking.get("candidate_limit")),
                "candidate_count": optional_int(reranking.get("candidate_count")),
                "final_top_k": optional_int(reranking.get("final_top_k")),
                "final_source_count": optional_int(reranking.get("final_source_count")),
                "reduction_rate": optional_float(reranking.get("reduction_rate")),
            }
        )
    return {
        "request_count": len(rows),
        "average_candidate_limit": average(
            row["candidate_limit"] for row in rows if row["candidate_limit"] is not None
        ),
        "average_candidate_count": average(
            row["candidate_count"] for row in rows if row["candidate_count"] is not None
        ),
        "average_final_top_k": average(
            row["final_top_k"] for row in rows if row["final_top_k"] is not None
        ),
        "average_final_source_count": average(
            row["final_source_count"] for row in rows if row["final_source_count"] is not None
        ),
        "average_reduction_rate": average(
            row["reduction_rate"] for row in rows if row["reduction_rate"] is not None
        ),
    }


def build_source_rows(events):
    """Return flattened source rows from audit events."""
    rows = []
    for event in events:
        if not event:
            continue
        explainability = event.retrieval_explainability()
        sources = explainability.get("sources") if isinstance(explainability, dict) else []
        for rank, source in enumerate(sources or [], start=1):
            score = _source_score(source)
            similarity = _source_similarity(source)
            source_type = source.get("type") or "knowledge"
            source_id = optional_int(source.get("id"))
            source_created_at = bounded(source.get("created_at"), 40)
            rows.append(
                {
                    "audit_event_id": event.id,
                    "workflow": event.workflow,
                    "rank": rank,
                    "source_type": source_type,
                    "source_id": source_id,
                    "source_record_id": optional_int(source.get("source_record_id")),
                    "title": _source_title(source, source_type, source_id),
                    "source_kind": bounded(source.get("source_kind"), 80),
                    "knowledge_source_type": bounded(source.get("knowledge_source_type"), 80),
                    "module": bounded(source.get("module"), 80),
                    "machine_id": optional_int(source.get("machine_id")),
                    "role_visibility": bounded(source.get("role_visibility"), 140),
                    "role": bounded(source.get("role"), 80),
                    "employee_access_level": bounded(
                        source.get("employee_access_level"),
                        40,
                    ),
                    "chunk_id": optional_int(source.get("chunk_id")),
                    "section_title": bounded(
                        source.get("section_title") or source.get("source_section"),
                        160,
                    ),
                    "score": score,
                    "similarity": similarity,
                    "quality_status": _source_quality(source),
                    "source_created_at": source_created_at,
                    "source_age_days": source_age_days(source_created_at),
                    "retrieved_at": event.created_at.isoformat(),
                    "created_at": event.created_at.isoformat(),
                }
            )
    return rows


def build_source_distribution(events):
    """Return source usage counts by source type."""
    counter = Counter()
    for event in events:
        for row in build_source_rows([event]):
            counter[row["source_type"]] += 1
    return dict(counter)


def build_source_kind_distribution(events):
    """Return source usage counts by retrieval source kind."""
    counter = Counter()
    for event in events:
        for row in build_source_rows([event]):
            counter[row.get("source_kind") or "unknown"] += 1
    return dict(counter)


def _top_hit_rows(source_rows, limit):
    """Return top retrieval hits by rank and score."""
    rows = sorted(
        source_rows,
        key=lambda row: (
            0 if row["rank"] == 1 else -row["rank"],
            row["score"] if row["score"] is not None else -1,
            row["similarity"] if row["similarity"] is not None else -1,
        ),
        reverse=True,
    )
    return [_source_hit_payload(row) for row in rows[:limit]]


def poor_hit_rows(source_rows, negative_feedback_ids, limit):
    """Return low-quality retrieval hits for monitoring."""
    poor_rows = [
        row
        for row in source_rows
        if row["audit_event_id"] in negative_feedback_ids
        or (row["score"] is not None and row["score"] <= LOW_SCORE_THRESHOLD)
        or (row["similarity"] is not None and row["similarity"] <= LOW_SIMILARITY_THRESHOLD)
    ]
    poor_rows.sort(
        key=lambda row: (
            row["audit_event_id"] in negative_feedback_ids,
            -(row["score"] if row["score"] is not None else 1000),
            -(row["similarity"] if row["similarity"] is not None else 1),
        ),
        reverse=True,
    )
    return [_source_hit_payload(row) for row in poor_rows[:limit]]


def _source_hit_payload(row):
    """Return one retrieval-hit payload."""
    payload = dict(row)
    payload["label"] = _source_row_label(row)
    return payload


def build_score_summary(source_rows):
    """Return aggregate retrieval score metrics."""
    scores = [row["score"] for row in source_rows if row.get("score") is not None]
    similarities = [row["similarity"] for row in source_rows if row.get("similarity") is not None]
    return {
        "source_count": len(source_rows),
        "average_score": average(scores),
        "average_similarity": average(similarities),
        "low_score_count": sum(1 for score in scores if score <= LOW_SCORE_THRESHOLD),
        "low_similarity_count": sum(
            1 for similarity in similarities if similarity <= LOW_SIMILARITY_THRESHOLD
        ),
    }


def build_retrieval_quality_actions(poor_hits, score_summary):
    """Return remediation actions for weak or negatively rated retrieval hits."""
    if not poor_hits:
        return []
    low_score_count = int(score_summary.get("low_score_count") or 0)
    low_similarity_count = int(score_summary.get("low_similarity_count") or 0)
    priority = "high" if low_score_count or low_similarity_count else "medium"
    return [
        {
            "type": "review_low_quality_retrieval_hits",
            "priority": priority,
            "target_type": "retrieval_quality",
            "target": "poor_hits",
            "count": len(poor_hits),
            "low_score_count": low_score_count,
            "low_similarity_count": low_similarity_count,
            "sample_sources": _source_action_samples(poor_hits),
            "reason": (
                f"{len(poor_hits)} Retrieval-Treffer wurden durch negatives Feedback "
                "oder schwache Score-Signale markiert."
            ),
            "recommended_action": (
                "Schlechte Treffer pruefen, Chunk-Zuschnitt und Metadaten verbessern "
                "oder fehlende Golden Test Questions ergaenzen."
            ),
            "next_steps": [
                "Poor-Hit-Beispiele fachlich mit der Nutzerfrage vergleichen.",
                "Chunk-Metadaten, Source-Titel und Maschinenbezug fuer diese Quellen pruefen.",
                "Golden Test Question fuer den betroffenen Fragetyp ergaenzen.",
            ],
            "success_criteria": [
                "Negative Feedback-Hits gehen nach Reindex/Evaluation zurueck.",
                "Recall und MRR bleiben stabil oder verbessern sich.",
            ],
        }
    ]


def source_freshness_summary(source_rows):
    """Return source age metrics for retrieval monitoring."""
    stale_days = knowledge_aging_policy().stale_days
    age_values = []
    undated_count = 0
    for row in source_rows:
        age_days = row.get("source_age_days")
        if age_days is None:
            undated_count += 1
            continue
        age_values.append(age_days)
    stale_count = sum(1 for age_days in age_values if age_days >= stale_days)
    return {
        "stale_threshold_days": stale_days,
        "measured_source_count": len(age_values),
        "undated_source_count": undated_count,
        "average_source_age_days": average(age_values),
        "oldest_source_age_days": max(age_values) if age_values else 0,
        "stale_source_count": stale_count,
        "stale_source_rate": rate(stale_count, len(age_values)),
    }


def stale_source_rows(source_rows, limit):
    """Return bounded stale source rows for admin review."""
    stale_days = knowledge_aging_policy().stale_days
    rows = [
        row
        for row in source_rows
        if row.get("source_age_days") is not None and row["source_age_days"] >= stale_days
    ]
    rows.sort(
        key=lambda row: (
            row.get("source_age_days") or 0,
            str(row.get("retrieved_at") or ""),
        ),
        reverse=True,
    )
    payloads = []
    for row in rows[:limit]:
        payload = _source_hit_payload(row)
        payload["stale_threshold_days"] = stale_days
        payloads.append(payload)
    return payloads


def undated_source_rows(source_rows, limit):
    """Return bounded source rows without parseable source timestamps."""
    rows = [row for row in source_rows if row.get("source_age_days") is None]
    rows.sort(key=lambda row: str(row.get("retrieved_at") or ""), reverse=True)
    return [_source_hit_payload(row) for row in rows[:limit]]


def source_metadata_quality_actions(source_freshness, stale_sources, undated_sources):
    """Return source metadata remediation actions for AI admin dashboards."""
    actions = []
    stale_count = int(source_freshness.get("stale_source_count") or 0)
    undated_count = int(source_freshness.get("undated_source_count") or 0)
    stale_days = int(source_freshness.get("stale_threshold_days") or 0)
    if stale_count:
        actions.append(
            {
                "type": "review_stale_sources",
                "priority": "high" if stale_count >= 3 else "medium",
                "target_type": "retrieval_source_metadata",
                "target": "stale_sources",
                "count": stale_count,
                "stale_threshold_days": stale_days,
                "sample_sources": _source_action_samples(stale_sources),
                "reason": (
                    f"{stale_count} abgerufene Quelle(n) sind aelter als " f"{stale_days} Tage."
                ),
                "recommended_action": (
                    "Quellen fachlich pruefen, veraltete Inhalte aktualisieren "
                    "oder als ueberholt markieren."
                ),
                "next_steps": [
                    "Stale Source-Liste nach haeufig genutzten Dokumenten priorisieren.",
                    "Fachverantwortliche Aktualitaet und Gueltigkeit pruefen lassen.",
                    "Aktualisierte Dokumente neu indexieren und Retrieval-Evaluation wiederholen.",
                ],
                "success_criteria": [
                    "Stale-Source-Rate sinkt im Observability-Dashboard.",
                    "Antworten nutzen aktualisierte Quellen mit sichtbaren Zeitstempeln.",
                ],
            }
        )
    if undated_count:
        actions.append(
            {
                "type": "complete_source_dates",
                "priority": "medium",
                "target_type": "retrieval_source_metadata",
                "target": "undated_sources",
                "count": undated_count,
                "sample_sources": _source_action_samples(undated_sources),
                "reason": (
                    f"{undated_count} abgerufene Quelle(n) haben kein auswertbares " "Source-Datum."
                ),
                "recommended_action": (
                    "Fehlende created_at/source_created_at Metadaten ergaenzen, "
                    "damit RAG-Frische und Recency-Ranking belastbar werden."
                ),
                "next_steps": [
                    "Undatierte Quellen auf Import- oder Dokument-Metadaten pruefen.",
                    "Erstell- oder Gueltigkeitsdatum in der Knowledge-Quelle nachpflegen.",
                    "Quelle neu indexieren und Source-Freshness erneut kontrollieren.",
                ],
                "success_criteria": [
                    "Undated-Source-Count faellt auf null oder ist fachlich begruendet.",
                    "Recency- und Aging-Signale koennen die Quelle bewerten.",
                ],
            }
        )
    return actions


def _source_action_samples(rows, limit=3):
    """Return compact source labels for metadata action previews."""
    samples = []
    for row in rows[:limit]:
        samples.append(
            {
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "source_record_id": row.get("source_record_id"),
                "title": row.get("title"),
                "label": row.get("label"),
            }
        )
    return samples


def _retrieval_action_summary(actions):
    """Return aggregate retrieval action counters for admin dashboards."""
    return action_summary(actions)


def action_summary(actions):
    """Return aggregate action counters for admin dashboards."""
    priority_counts = Counter(str(action.get("priority") or "unknown") for action in actions)
    type_counts = Counter(str(action.get("type") or "unknown") for action in actions)
    source_counts = Counter(
        str(action.get("action_source")) for action in actions if action.get("action_source")
    )
    summary = {
        "total": len(actions),
        "critical_priority_count": priority_counts.get("critical", 0),
        "high_priority_count": priority_counts.get("high", 0),
        "medium_priority_count": priority_counts.get("medium", 0),
        "priority_distribution": counter_rows(priority_counts),
        "type_distribution": counter_rows(type_counts),
    }
    if actions:
        next_action = actions[0]
        summary["next_action_type"] = str(next_action.get("type") or "")
        summary["next_action_priority"] = str(next_action.get("priority") or "")
        if next_action.get("action_source"):
            summary["next_action_source"] = str(next_action.get("action_source"))
    if source_counts:
        summary["source_distribution"] = counter_rows(source_counts)
    return summary


def _chunk_usage_rows(counter, limit):
    """Return frequently used chunk references."""
    rows = []
    for (source_id, chunk_id, source_type), count in counter.most_common(limit):
        rows.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "chunk_id": chunk_id,
                "uses": count,
                "label": knowledge_title(source_id) if source_type == "knowledge" else "",
            }
        )
    return rows


def document_usage_rows(counter, limit):
    """Return frequently used document or structured source references."""
    rows = []
    for (source_type, source_id), count in counter.most_common(limit):
        rows.append(
            {
                "source_type": source_type,
                "source_id": source_id,
                "uses": count,
                "label": knowledge_title(source_id) if source_type == "knowledge" else "",
            }
        )
    return rows


def source_reference(source):
    """Return one source reference without chunk body text."""
    source_type = source.get("type") or "knowledge"
    source_id = optional_int(source.get("id"))
    return {
        "type": source_type,
        "id": source_id,
        "title": _source_title(source, source_type, source_id),
        "source_record_id": optional_int(source.get("source_record_id")),
        "source_kind": bounded(source.get("source_kind"), 80),
        "knowledge_source_type": bounded(source.get("knowledge_source_type"), 80),
        "module": bounded(source.get("module"), 80),
        "machine_id": optional_int(source.get("machine_id")),
        "role_visibility": bounded(source.get("role_visibility"), 140),
        "role": bounded(source.get("role"), 80),
        "employee_access_level": bounded(source.get("employee_access_level"), 40),
        "created_at": bounded(source.get("created_at"), 40),
        "chunk_id": optional_int(source.get("chunk_id")),
        "section_title": bounded(
            source.get("section_title") or source.get("source_section"),
            160,
        ),
        "score": _source_score(source),
        "similarity": _source_similarity(source),
        "quality_status": _source_quality(source),
        "label": source_label(source),
    }


def _source_title(source, source_type=None, source_id=None):
    """Return a bounded prompt-safe source title."""
    title = bounded(source.get("title") or source.get("source_title"), 180)
    if title:
        return title
    safe_type = str(source_type or source.get("type") or "knowledge")
    safe_id = source_id if source_id is not None else optional_int(source.get("id"))
    return knowledge_title(safe_id) if safe_type == "knowledge" else ""


def source_label(source):
    """Return a readable source reference label."""
    source_type = str(source.get("type") or "knowledge")
    source_id = optional_int(source.get("id"))
    chunk_id = optional_int(source.get("chunk_id"))
    section = bounded(source.get("section_title") or source.get("source_section"), 80)
    label = source_type
    if source_type == "knowledge" and source_id:
        title = knowledge_title(source_id)
        if title:
            label = title
    elif source_id is not None:
        label = f"{source_type} #{source_id}"
    if chunk_id is not None:
        label = f"{label} / Chunk #{chunk_id}"
    if section:
        label = f"{label} - {section}"
    return label


def _source_row_label(row):
    """Return a source label from a flattened source row."""
    source = {
        "type": row.get("source_type"),
        "id": row.get("source_id"),
        "chunk_id": row.get("chunk_id"),
        "section_title": row.get("section_title"),
    }
    return source_label(source)


def _source_score(source):
    """Return the best score available for a source."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if isinstance(explainability, dict) and explainability.get("final_score") is not None:
        return optional_float(explainability.get("final_score"))
    return optional_float(source.get("score") if isinstance(source, dict) else None)


def _source_similarity(source):
    """Return semantic similarity for one source when available."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if not isinstance(explainability, dict):
        return None
    return optional_float(explainability.get("semantic_similarity"))


def _source_quality(source):
    """Return source quality status."""
    explainability = source.get("explainability") if isinstance(source, dict) else {}
    if isinstance(explainability, dict) and explainability.get("quality_status"):
        return str(explainability.get("quality_status"))
    return str(source.get("quality_status") or "") if isinstance(source, dict) else ""


def retrieval_duration_ms(event):
    """Return retrieval duration from stored explainability."""
    if not event:
        return None
    explainability = event.retrieval_explainability()
    if not isinstance(explainability, dict):
        return None
    return optional_int(explainability.get("retrieval_duration_ms"))


def build_similarity_values(events):
    """Return all semantic similarity samples from audit events."""
    values = []
    for row in build_source_rows(events):
        if row.get("similarity") is not None:
            values.append(row["similarity"])
    return values


def negative_feedback_event_ids(feedback_entries):
    """Return audit event ids with negative feedback ratings."""
    return {
        feedback.audit_event_id
        for feedback in feedback_entries
        if feedback.rating in NEGATIVE_RATINGS
    }
