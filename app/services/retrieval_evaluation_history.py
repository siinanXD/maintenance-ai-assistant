"""Persisted evaluation runs: history, regression detection and the quality gate."""

from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import RetrievalEvaluationRun
from app.services.retrieval_evaluation_common import (
    DEFAULT_HISTORY_LIMIT,
    QUALITY_WARNING_THRESHOLDS,
    REGRESSION_COUNT_INCREASE_THRESHOLD,
    REGRESSION_DROP_THRESHOLD,
    SAFE_SOURCE_METADATA_FIELDS,
    clamped_metric,
    history_limit,
    nonnegative_float,
    nonnegative_int,
    safe_string_int_mapping,
)


def persist_retrieval_evaluation_result(evaluation_result, commit=True):
    """Persist aggregate retrieval evaluation metrics without query or source details."""
    if not isinstance(evaluation_result, dict):
        raise TypeError("evaluation_result must be a dictionary")
    source_metadata = safe_source_metadata_coverage(
        evaluation_result.get("source_metadata_coverage")
    )
    run = RetrievalEvaluationRun(
        query_count=nonnegative_int(evaluation_result.get("query_count")),
        recall_at_k=clamped_metric(evaluation_result.get("recall_at_k")),
        mrr=clamped_metric(evaluation_result.get("mrr")),
        ndcg_at_k=clamped_metric(evaluation_result.get("ndcg_at_k")),
        keyword_query_count=nonnegative_int(evaluation_result.get("keyword_query_count")),
        keyword_hit_rate=clamped_metric(evaluation_result.get("keyword_hit_rate")),
        permission_leak_count=nonnegative_int(evaluation_result.get("permission_leak_count")),
        forbidden_source_hit_count=nonnegative_int(
            evaluation_result.get("forbidden_source_hit_count")
        ),
        no_result_count=nonnegative_int(evaluation_result.get("no_result_count")),
        no_result_rate=clamped_metric(evaluation_result.get("no_result_rate")),
        expected_no_result_count=nonnegative_int(evaluation_result.get("expected_no_result_count")),
        expected_no_result_success_count=nonnegative_int(
            evaluation_result.get("expected_no_result_success_count")
        ),
        expected_no_result_success_rate=clamped_metric(
            evaluation_result.get("expected_no_result_success_rate")
        ),
        unexpected_no_result_count=nonnegative_int(
            evaluation_result.get("unexpected_no_result_count")
        ),
        unexpected_no_result_rate=clamped_metric(
            evaluation_result.get("unexpected_no_result_rate")
        ),
        min_source_count_fail_count=nonnegative_int(
            evaluation_result.get("min_source_count_fail_count")
        ),
        min_source_count_pass_rate=clamped_metric(
            evaluation_result.get("min_source_count_pass_rate")
        ),
        query_type_expected_count=nonnegative_int(
            evaluation_result.get("query_type_expected_count")
        ),
        query_type_match_count=nonnegative_int(evaluation_result.get("query_type_match_count")),
        query_type_accuracy=clamped_metric(evaluation_result.get("query_type_accuracy")),
        source_metadata_count=source_metadata["retrieved_source_count"],
        source_id_coverage_rate=source_metadata["source_id_coverage_rate"],
        source_type_coverage_rate=source_metadata["source_type_coverage_rate"],
        source_pair_coverage_rate=source_metadata["source_pair_coverage_rate"],
        metadata_pair_coverage_rate=source_metadata["metadata_pair_coverage_rate"],
    )
    db.session.add(run)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def retrieval_evaluation_history(limit=DEFAULT_HISTORY_LIMIT):
    """Return recent prompt-safe golden retrieval evaluation runs and regression signals."""
    try:
        runs = (
            RetrievalEvaluationRun.query.order_by(
                RetrievalEvaluationRun.created_at.desc(),
                RetrievalEvaluationRun.id.desc(),
            )
            .limit(history_limit(limit))
            .all()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        return {
            "runs": [],
            "latest": None,
            "previous": None,
            "regression": detect_retrieval_regression(None, None),
            "unavailable": True,
            "error": exc.__class__.__name__,
            "privacy": history_privacy_payload(),
        }
    payloads = [run.to_dict() for run in runs]
    payloads = [_with_evaluation_quality_gate(payload) for payload in payloads]
    latest = payloads[0] if payloads else None
    previous = payloads[1] if len(payloads) > 1 else None
    return {
        "runs": payloads,
        "latest": latest,
        "previous": previous,
        "regression": detect_retrieval_regression(latest, previous),
        "unavailable": False,
        "privacy": history_privacy_payload(),
    }


def detect_retrieval_regression(current_run, previous_run):
    """Return regression signals between two prompt-safe evaluation run payloads."""
    current = _run_metrics(current_run)
    previous = _run_metrics(previous_run)
    if not current or not previous:
        return {"regressed": False, "signals": []}

    signals = []
    for metric in (
        "recall_at_k",
        "mrr",
        "ndcg_at_k",
        "keyword_hit_rate",
        "min_source_count_pass_rate",
        "query_type_accuracy",
        "source_id_coverage_rate",
        "source_type_coverage_rate",
        "source_pair_coverage_rate",
        "metadata_pair_coverage_rate",
    ):
        delta = round(current[metric] - previous[metric], 4)
        if delta <= -REGRESSION_DROP_THRESHOLD:
            signals.append(_regression_signal(metric, current[metric], previous[metric], delta))

    for metric in (
        "permission_leak_count",
        "forbidden_source_hit_count",
        "no_result_count",
        "unexpected_no_result_count",
        "min_source_count_fail_count",
    ):
        delta = current[metric] - previous[metric]
        if delta >= REGRESSION_COUNT_INCREASE_THRESHOLD:
            signals.append(_regression_signal(metric, current[metric], previous[metric], delta))

    delta = round(current["no_result_rate"] - previous["no_result_rate"], 4)
    if delta >= REGRESSION_DROP_THRESHOLD:
        signals.append(
            _regression_signal(
                "no_result_rate",
                current["no_result_rate"],
                previous["no_result_rate"],
                delta,
            )
        )

    delta = round(current["unexpected_no_result_rate"] - previous["unexpected_no_result_rate"], 4)
    if delta >= REGRESSION_DROP_THRESHOLD:
        signals.append(
            _regression_signal(
                "unexpected_no_result_rate",
                current["unexpected_no_result_rate"],
                previous["unexpected_no_result_rate"],
                delta,
            )
        )

    delta = round(
        current["expected_no_result_success_rate"] - previous["expected_no_result_success_rate"],
        4,
    )
    if delta <= -REGRESSION_DROP_THRESHOLD:
        signals.append(
            _regression_signal(
                "expected_no_result_success_rate",
                current["expected_no_result_success_rate"],
                previous["expected_no_result_success_rate"],
                delta,
            )
        )

    return {"regressed": bool(signals), "signals": signals}


def evaluation_quality_gate(run):
    """Return a compact quality gate from prompt-safe retrieval evaluation metrics."""
    metrics = _run_metrics(run)
    if not metrics:
        return {
            "status": "unknown",
            "passed": False,
            "blocking": [],
            "warnings": [],
            "summary": "Keine Retrieval-Evaluation vorhanden.",
        }

    blocking = _quality_gate_blocking_signals(metrics)
    warnings = _quality_gate_warning_signals(metrics)
    if blocking:
        status = "fail"
    elif warnings:
        status = "warning"
    else:
        status = "pass"
    return {
        "status": status,
        "passed": status == "pass",
        "blocking": blocking,
        "warnings": warnings,
        "summary": _quality_gate_summary(status, blocking, warnings),
    }


def safe_chunk_metadata_coverage(value):
    """Return bounded prompt-safe chunk metadata coverage metrics."""
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "retrieved_chunk_count": nonnegative_int(payload.get("retrieved_chunk_count")),
        "measured_chunk_count": nonnegative_int(payload.get("measured_chunk_count")),
        "coverage_rate": clamped_metric(payload.get("coverage_rate")),
        "average_char_count": nonnegative_float(payload.get("average_char_count")),
        "average_token_count": nonnegative_float(payload.get("average_token_count")),
        "block_metadata_count": nonnegative_int(payload.get("block_metadata_count")),
        "block_metadata_coverage_rate": clamped_metric(payload.get("block_metadata_coverage_rate")),
        "average_block_count": nonnegative_float(payload.get("average_block_count")),
        "block_kind_distribution": safe_string_int_mapping(payload.get("block_kind_distribution")),
    }


def safe_source_metadata_coverage(value):
    """Return bounded prompt-safe source metadata coverage metrics."""
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return {
        "retrieved_source_count": nonnegative_int(payload.get("retrieved_source_count")),
        "with_source_id_count": nonnegative_int(payload.get("with_source_id_count")),
        "with_source_type_count": nonnegative_int(payload.get("with_source_type_count")),
        "with_source_pair_count": nonnegative_int(payload.get("with_source_pair_count")),
        "with_metadata_pair_count": nonnegative_int(payload.get("with_metadata_pair_count")),
        "source_id_coverage_rate": clamped_metric(payload.get("source_id_coverage_rate")),
        "source_type_coverage_rate": clamped_metric(payload.get("source_type_coverage_rate")),
        "source_pair_coverage_rate": clamped_metric(payload.get("source_pair_coverage_rate")),
        "metadata_pair_coverage_rate": clamped_metric(payload.get("metadata_pair_coverage_rate")),
        "field_coverage": _safe_field_coverage_payload(payload.get("field_coverage")),
    }


def _safe_field_coverage_payload(value):
    """Return bounded per-field source metadata coverage metrics."""
    payload = dict(value or {}) if isinstance(value, dict) else {}
    return {
        field: {
            "with_value_count": nonnegative_int(
                (payload.get(field) or {}).get("with_value_count")
                if isinstance(payload.get(field), dict)
                else 0
            ),
            "coverage_rate": clamped_metric(
                (payload.get(field) or {}).get("coverage_rate")
                if isinstance(payload.get(field), dict)
                else 0.0
            ),
        }
        for field in SAFE_SOURCE_METADATA_FIELDS
    }


def _with_evaluation_quality_gate(payload):
    """Return a run payload enriched with an aggregate quality gate."""
    item = dict(payload or {})
    item["quality_gate"] = evaluation_quality_gate(item)
    return item


def _run_metrics(run):
    """Return comparable metrics from a model or dictionary payload."""
    if run is None:
        return {}
    payload = run.to_dict() if hasattr(run, "to_dict") else dict(run)
    return {
        "query_count": nonnegative_int(payload.get("query_count")),
        "recall_at_k": clamped_metric(payload.get("recall_at_k")),
        "mrr": clamped_metric(payload.get("mrr")),
        "ndcg_at_k": clamped_metric(payload.get("ndcg_at_k")),
        "keyword_query_count": nonnegative_int(payload.get("keyword_query_count")),
        "keyword_hit_rate": clamped_metric(payload.get("keyword_hit_rate")),
        "permission_leak_count": nonnegative_int(payload.get("permission_leak_count")),
        "forbidden_source_hit_count": nonnegative_int(payload.get("forbidden_source_hit_count")),
        "no_result_count": nonnegative_int(payload.get("no_result_count")),
        "no_result_rate": clamped_metric(payload.get("no_result_rate")),
        "expected_no_result_count": nonnegative_int(payload.get("expected_no_result_count")),
        "expected_no_result_success_rate": clamped_metric(
            payload.get("expected_no_result_success_rate")
        ),
        "unexpected_no_result_count": nonnegative_int(payload.get("unexpected_no_result_count")),
        "unexpected_no_result_rate": clamped_metric(payload.get("unexpected_no_result_rate")),
        "min_source_count_fail_count": nonnegative_int(payload.get("min_source_count_fail_count")),
        "min_source_count_pass_rate": clamped_metric(payload.get("min_source_count_pass_rate")),
        "query_type_expected_count": nonnegative_int(payload.get("query_type_expected_count")),
        "query_type_accuracy": clamped_metric(payload.get("query_type_accuracy")),
        "source_metadata_count": nonnegative_int(payload.get("source_metadata_count")),
        "source_id_coverage_rate": clamped_metric(payload.get("source_id_coverage_rate")),
        "source_type_coverage_rate": clamped_metric(payload.get("source_type_coverage_rate")),
        "source_pair_coverage_rate": clamped_metric(payload.get("source_pair_coverage_rate")),
        "metadata_pair_coverage_rate": clamped_metric(payload.get("metadata_pair_coverage_rate")),
        "retrieved_chunk_count": nonnegative_int(
            (payload.get("chunk_metadata_coverage") or {}).get("retrieved_chunk_count")
            if isinstance(payload.get("chunk_metadata_coverage"), dict)
            else payload.get("retrieved_chunk_count")
        ),
        "block_metadata_coverage_rate": clamped_metric(
            (payload.get("chunk_metadata_coverage") or {}).get("block_metadata_coverage_rate")
            if isinstance(payload.get("chunk_metadata_coverage"), dict)
            else payload.get("block_metadata_coverage_rate")
        ),
    }


def _quality_gate_blocking_signals(metrics):
    """Return security-relevant quality gate failures."""
    blocking = []
    for metric in ("permission_leak_count", "forbidden_source_hit_count"):
        value = metrics[metric]
        if value > 0:
            blocking.append(
                {
                    "metric": metric,
                    "value": value,
                    "threshold": 0,
                    "reason": "retrieved_forbidden_or_invisible_source",
                }
            )
    return blocking


def _quality_gate_warning_signals(metrics):
    """Return non-blocking retrieval quality warnings for admin dashboards."""
    warnings = []
    for metric, threshold in QUALITY_WARNING_THRESHOLDS.items():
        if not _quality_gate_metric_applies(metric, metrics):
            continue
        value = metrics[metric]
        threshold_missed = (
            value > threshold if metric == "unexpected_no_result_rate" else value < threshold
        )
        if threshold_missed:
            warnings.append(
                {
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "reason": _quality_gate_warning_reason(metric),
                }
            )
    return warnings


def _quality_gate_metric_applies(metric, metrics):
    """Return whether a quality gate metric has enough support to be useful."""
    if metrics["query_count"] <= 0:
        return False
    if metric == "keyword_hit_rate":
        return metrics["keyword_query_count"] > 0
    if metric == "expected_no_result_success_rate":
        return metrics["expected_no_result_count"] > 0
    if metric == "query_type_accuracy":
        return metrics["query_type_expected_count"] > 0
    if metric in {"source_pair_coverage_rate", "metadata_pair_coverage_rate"}:
        return metrics["source_metadata_count"] > 0
    if metric == "block_metadata_coverage_rate":
        return metrics["retrieved_chunk_count"] > 0
    return True


def _quality_gate_warning_reason(metric):
    """Return a prompt-safe reason label for one quality gate warning."""
    labels = {
        "recall_at_k": "expected_sources_not_recalled",
        "mrr": "relevant_source_ranked_too_low",
        "keyword_hit_rate": "expected_keywords_missing",
        "expected_no_result_success_rate": "expected_no_result_not_respected",
        "unexpected_no_result_rate": "unexpected_empty_retrieval",
        "min_source_count_pass_rate": "insufficient_source_count",
        "query_type_accuracy": "query_type_mismatch",
        "source_pair_coverage_rate": "source_metadata_pair_incomplete",
        "metadata_pair_coverage_rate": "structured_metadata_pair_incomplete",
        "block_metadata_coverage_rate": "chunk_structure_metadata_incomplete",
    }
    return labels.get(metric, "quality_threshold_missed")


def _quality_gate_summary(status, blocking, warnings):
    """Return a compact German admin summary for one evaluation gate."""
    if status == "pass":
        return "Retrieval-Evaluation besteht alle Quality-Gate-Regeln."
    if status == "fail":
        return (
            f"Retrieval-Evaluation blockiert wegen {len(blocking)} "
            "sicherheitsrelevanten Treffern."
        )
    return f"Retrieval-Evaluation hat {len(warnings)} Qualitaetswarnungen."


def _regression_signal(metric, current, previous, delta):
    """Return one prompt-safe regression signal payload."""
    return {
        "metric": metric,
        "current": current,
        "previous": previous,
        "delta": round(delta, 4) if isinstance(delta, float) else delta,
        "status": "warning",
    }


def history_privacy_payload():
    """Return privacy guarantees for persisted evaluation history."""
    return {
        "stores_query_text": False,
        "stores_expected_sources": False,
        "stores_expected_keywords": False,
        "stores_retrieved_sources": False,
        "stores_source_ids": False,
        "stores_source_metadata_aggregates": True,
        "stores_chunk_text": False,
        "source": "retrieval_evaluation_run_metrics",
    }
