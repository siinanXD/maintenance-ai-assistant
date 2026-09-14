"""Recommended actions for the AI admin: provider, retrieval and evaluation gates."""

from __future__ import annotations

from app.services.ai_observability_common import (
    DEFAULT_OBSERVABILITY_LIMIT,
    bounded_rate,
    optional_float,
)
from app.services.ai_observability_sources import (
    action_summary,
    build_retrieval_quality_actions,
    build_score_summary,
    negative_feedback_event_ids,
    poor_hit_rows,
    source_freshness_summary,
    source_metadata_quality_actions,
    stale_source_rows,
    undated_source_rows,
)


def build_action_summaries(source_rows, feedback_entries, telemetry):
    """Return retrieval and evaluation action summaries for top-level metrics."""
    negative_feedback_ids = negative_feedback_event_ids(feedback_entries)
    poor_hits = poor_hit_rows(
        source_rows,
        negative_feedback_ids,
        DEFAULT_OBSERVABILITY_LIMIT,
    )
    score_summary = build_score_summary(source_rows)
    source_freshness = source_freshness_summary(source_rows)
    metadata_actions = source_metadata_quality_actions(
        source_freshness,
        stale_source_rows(source_rows, DEFAULT_OBSERVABILITY_LIMIT),
        undated_source_rows(source_rows, DEFAULT_OBSERVABILITY_LIMIT),
    )
    retrieval_actions = build_retrieval_quality_actions(poor_hits, score_summary)
    evaluation = telemetry.get("retrieval_evaluation_history") or {}
    latest_eval = evaluation.get("latest") or {}
    source_metadata_gaps = build_source_metadata_gaps(latest_eval)
    quality_gate = latest_eval.get("quality_gate") or empty_evaluation_quality_gate()
    evaluation_actions = evaluation_quality_actions(
        latest_eval,
        quality_gate,
        source_metadata_gaps,
    )
    return {
        "retrieval": action_summary(retrieval_actions + metadata_actions),
        "evaluation": action_summary(evaluation_actions),
    }


def observability_recommended_actions(
    metrics,
    retrieval_monitoring,
    quality_metrics,
    provider_readiness,
    limit,
):
    """Return prioritized AI admin actions across evaluation, retrieval, and gaps."""
    actions = []
    provider_action = _provider_readiness_action(provider_readiness)
    if provider_action:
        actions.append(provider_action)
    _extend_recommended_actions(
        actions,
        quality_metrics.get("evaluation_actions") or [],
        "evaluation",
    )
    _extend_recommended_actions(
        actions,
        retrieval_monitoring.get("retrieval_quality_actions") or [],
        "retrieval_quality",
    )
    _extend_recommended_actions(
        actions,
        retrieval_monitoring.get("metadata_quality_actions") or [],
        "source_metadata",
    )
    knowledge_gaps = metrics.get("knowledge_gaps") or {}
    _extend_recommended_actions(
        actions,
        knowledge_gaps.get("recommended_actions") or [],
        "knowledge_gap",
    )
    actions.sort(
        key=lambda action: (
            _priority_rank(action.get("priority")),
            _action_source_rank(action.get("action_source")),
            str(action.get("type") or ""),
        )
    )
    ranked_actions = actions[:limit]
    for index, action in enumerate(ranked_actions, start=1):
        action["rank"] = index
        action["rank_label"] = f"P{index}"
    return ranked_actions


def _extend_recommended_actions(actions, rows, action_source):
    """Append prompt-safe action rows with a stable action source label."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        action = dict(row)
        action["action_source"] = action_source
        actions.append(action)


def _provider_readiness_action(provider_readiness):
    """Return one critical admin action for degraded provider readiness."""
    readiness = provider_readiness.get("readiness") or {}
    next_action = readiness.get("next_action") or {}
    if provider_readiness.get("ready") or not isinstance(next_action, dict):
        return None
    component = str(next_action.get("component") or "provider")
    reason = str(next_action.get("reason") or "")
    return {
        "type": str(next_action.get("configuration_action") or "review_provider_configuration"),
        "priority": "critical",
        "target_type": "ai_provider_readiness",
        "target": component,
        "component": component,
        "reason": reason,
        "recommended_action": str(next_action.get("recommended_action") or ""),
        "next_steps": [
            "AI-Provider-Konfiguration im Admin-Status pruefen.",
            "Fehlende Umgebungsvariable setzen oder auf lokalen Fallback wechseln.",
            "Health- und AI-Status nach der Konfigurationsaenderung erneut pruefen.",
        ],
        "success_criteria": [
            "AI provider_readiness.ready ist true.",
            "Readiness enthaelt keine degraded provider components.",
        ],
        "action_source": "provider_readiness",
    }


def _priority_rank(priority):
    """Return sort rank for action priorities."""
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }.get(str(priority or "unknown"), 4)


def _action_source_rank(action_source):
    """Return stable sort rank for action sources."""
    return {
        "provider_readiness": 0,
        "evaluation": 1,
        "retrieval_quality": 2,
        "source_metadata": 3,
        "knowledge_gap": 4,
    }.get(str(action_source or "unknown"), 4)


def build_source_metadata_gaps(latest_eval):
    """Return prompt-safe source metadata coverage gaps from the latest evaluation."""
    labels = {
        "source_id_coverage_rate": "source_id",
        "source_type_coverage_rate": "source_type",
        "source_pair_coverage_rate": "source_pair",
        "metadata_pair_coverage_rate": "metadata_pair",
    }
    gaps = []
    if not latest_eval:
        return gaps
    for metric, field in labels.items():
        rate = latest_eval.get(metric)
        if rate is None:
            continue
        coverage_rate = bounded_rate(rate)
        if coverage_rate < 1.0:
            gaps.append(
                {
                    "field": field,
                    "metric": metric,
                    "coverage_rate": coverage_rate,
                    "missing_rate": round(1.0 - coverage_rate, 4),
                }
            )
    return gaps


def evaluation_quality_actions(latest_eval, quality_gate, source_metadata_gaps):
    """Return remediation actions for failed retrieval evaluation signals."""
    if not latest_eval:
        return [
            {
                "type": "run_retrieval_evaluation",
                "priority": "high",
                "target_type": "retrieval_evaluation",
                "target": "golden_questions",
                "reason": "Es liegt noch kein Retrieval-Evaluation-Lauf vor.",
                "recommended_action": (
                    "Golden Test Questions ausfuehren, damit Recall, MRR, "
                    "No-Result-Rate und Permission-Leaks messbar sind."
                ),
                "next_steps": [
                    "Golden Test Questions pruefen oder anlegen.",
                    "Retrieval-Evaluation ausfuehren.",
                    "Quality-Gate-Ergebnis im AI Admin kontrollieren.",
                ],
            }
        ]
    actions = []
    permission_leak_count = int(latest_eval.get("permission_leak_count") or 0)
    if permission_leak_count:
        actions.append(
            {
                "type": "fix_permission_leaks",
                "priority": "critical",
                "target_type": "retrieval_evaluation",
                "target": "permission_leak_count",
                "count": permission_leak_count,
                "reason": (
                    f"{permission_leak_count} Retrieval-Evaluation-Hit(s) verletzen "
                    "die erwartete Sichtbarkeit."
                ),
                "recommended_action": (
                    "Metadatenfilter, Rollen-/Department-Sichtbarkeit und "
                    "Permission-Leak-Golden-Tests pruefen."
                ),
                "next_steps": [
                    "Forbidden Source Hits aus dem Evaluation-Run analysieren.",
                    "Rollen- und Department-Filter fuer Retrieval-Kandidaten pruefen.",
                    "Evaluation nach Filterkorrektur erneut ausfuehren.",
                ],
            }
        )
    unexpected_no_result_count = int(latest_eval.get("unexpected_no_result_count") or 0)
    min_source_count_fail_count = int(latest_eval.get("min_source_count_fail_count") or 0)
    if unexpected_no_result_count or min_source_count_fail_count:
        actions.append(
            {
                "type": "improve_retrieval_coverage",
                "priority": "high",
                "target_type": "retrieval_evaluation",
                "target": "coverage_failures",
                "unexpected_no_result_count": unexpected_no_result_count,
                "min_source_count_fail_count": min_source_count_fail_count,
                "reason": (
                    "Evaluation zeigt unerwartete No-Result-Faelle oder zu wenige "
                    "Quellen fuer erwartete Antworten."
                ),
                "recommended_action": (
                    "Fehlende Dokumente, Chunking, Hybrid Search und erwartete "
                    "Quellen der Golden Questions pruefen."
                ),
                "next_steps": [
                    "Queries mit unerwartetem No-Result nach Quellenabdeckung sortieren.",
                    "Expected Sources und Keywords in Golden Questions pruefen.",
                    "Nach Reindex Recall@K und MRR vergleichen.",
                ],
            }
        )
    if source_metadata_gaps:
        actions.append(
            {
                "type": "complete_evaluation_source_metadata",
                "priority": "medium",
                "target_type": "retrieval_evaluation",
                "target": "source_metadata_gaps",
                "count": len(source_metadata_gaps),
                "fields": [gap["field"] for gap in source_metadata_gaps],
                "reason": "Evaluation meldet unvollstaendige Source-Metadaten.",
                "recommended_action": (
                    "Source-ID, Source-Type und Metadaten-Paare in Evaluation "
                    "und Retrieval-Ausgabe angleichen."
                ),
                "next_steps": [
                    "Source-Metadata-Gaps nach Feld priorisieren.",
                    "Retriever-Payload und Index-Metadaten fuer diese Felder pruefen.",
                    "Evaluation erneut ausfuehren und Coverage-Raten vergleichen.",
                ],
            }
        )
    warnings = quality_gate_warning_rows((quality_gate or {}).get("warnings") or [])
    if warnings:
        warning_metrics = [warning["metric"] for warning in warnings]
        actions.append(
            {
                "type": "review_evaluation_warnings",
                "priority": "medium",
                "target_type": "retrieval_evaluation",
                "target": "quality_gate_warnings",
                "count": len(warnings),
                "warning_metrics": warning_metrics,
                "focus_areas": _evaluation_warning_focus_areas(warning_metrics),
                "reason": "Das Retrieval Quality Gate meldet Warnungen.",
                "recommended_action": _evaluation_warning_recommended_action(warning_metrics),
                "next_steps": _evaluation_warning_next_steps(warning_metrics),
                "success_criteria": _evaluation_warning_success_criteria(warning_metrics),
            }
        )
    return actions[:5]


def _evaluation_warning_focus_areas(metrics):
    """Return concise focus labels for evaluation quality warning metrics."""
    labels = {
        "block_metadata_coverage_rate": "chunk_structure_metadata",
        "keyword_hit_rate": "expected_keywords",
        "recall_at_k": "expected_sources",
        "mrr": "source_ranking",
        "source_pair_coverage_rate": "source_metadata",
        "metadata_pair_coverage_rate": "source_metadata",
    }
    return sorted({labels.get(str(metric), "retrieval_quality") for metric in metrics})


def _evaluation_warning_recommended_action(metrics):
    """Return a specific admin recommendation for evaluation warnings."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return (
            "Chunk-Strukturmetadaten im Index pruefen und betroffene Dokumente "
            "mit aktuellem Chunking neu indexieren."
        )
    return "Warnmetriken fachlich pruefen und priorisieren."


def _evaluation_warning_next_steps(metrics):
    """Return targeted next steps for evaluation warning metrics."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return [
            "Evaluation-Warnungen nach block_metadata_coverage_rate filtern.",
            "Index-Metadaten chunk_block_count und chunk_block_kinds pruefen.",
            "Betroffene Dokumente mit hybrid_semantic Chunking neu indexieren.",
        ]
    return [
        "Quality-Gate-Warnungen nach Metrik gruppieren.",
        "Betroffene Golden Questions reproduzieren.",
        "Schwellwerte und erwartete Quellen fachlich validieren.",
    ]


def _evaluation_warning_success_criteria(metrics):
    """Return success criteria for evaluation warning remediation."""
    metric_set = {str(metric) for metric in metrics}
    if "block_metadata_coverage_rate" in metric_set:
        return [
            "block_metadata_coverage_rate liegt mindestens bei 0.8.",
            "block_kind_distribution zeigt erwartete Chunk-Strukturtypen.",
        ]
    return [
        "Quality-Gate-Warnungen sinken oder sind fachlich begruendet.",
        "Betroffene Golden Questions erreichen die erwarteten Quellen.",
    ]


def quality_gate_warning_rows(warnings):
    """Return prompt-safe quality-gate warning rows."""
    return _quality_gate_issue_rows(warnings)


def quality_gate_blocking_rows(blocking):
    """Return prompt-safe quality-gate blocking rows."""
    return _quality_gate_issue_rows(blocking)


def _quality_gate_issue_rows(issues):
    """Return prompt-safe quality-gate issue rows."""
    rows = []
    for issue in issues[:10]:
        if not isinstance(issue, dict):
            continue
        metric = str(issue.get("metric") or "")[:120]
        if not metric:
            continue
        rows.append(
            {
                "metric": metric,
                "value": optional_float(issue.get("value")),
                "threshold": optional_float(issue.get("threshold")),
                "reason": str(issue.get("reason") or "")[:160],
            }
        )
    return rows


def empty_evaluation_quality_gate():
    """Return the default quality gate payload when no evaluation run exists."""
    return {
        "status": "unknown",
        "passed": False,
        "blocking": [],
        "warnings": [],
        "summary": "Keine Retrieval-Evaluation vorhanden.",
    }


def recommended_action_summary(actions, metrics):
    """Return root action summary plus related action families not in the top list."""
    summary = action_summary(actions)
    answer_quality_actions = metrics.get("answer_quality_actions") or []
    answer_quality_summary = metrics.get("answer_quality_action_summary") or {}
    summary["answer_quality_action_count"] = int(metrics.get("answer_quality_action_count") or 0)
    summary["answer_quality_high_action_count"] = int(
        answer_quality_summary.get("high_priority_count") or 0
    )
    if answer_quality_actions:
        next_action = answer_quality_actions[0]
        summary["answer_quality_next_action_type"] = str(next_action.get("type") or "")
        summary["answer_quality_next_action_priority"] = str(next_action.get("priority") or "")
    return summary
