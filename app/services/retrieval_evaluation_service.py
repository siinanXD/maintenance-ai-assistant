"""Golden-query evaluation harness for permission-aware RAG retrieval."""

from dataclasses import dataclass, field

from app.services.golden_retrieval_question_service import runtime_golden_questions
from app.services.query_understanding_service import classify_query
from app.services.retrieval_evaluation_common import (
    RETRIEVAL_MODE_FULL,
    RETRIEVAL_MODE_VECTOR,
    average_metric,
    bool_value,
    clamped_metric,
    nonnegative_int,
    normalize_retrieval_mode,
    normalized_ints,
    normalized_source_pairs,
    normalized_strings,
    positive_int,
    rate,
    serializable_context,
)
from app.services.retrieval_evaluation_history import (
    evaluation_quality_gate,
    history_privacy_payload,
    persist_retrieval_evaluation_result,
    safe_chunk_metadata_coverage,
    safe_source_metadata_coverage,
)
from app.services.retrieval_evaluation_metrics import (
    build_expected_units,
    build_matched_keywords,
    build_missing_keywords,
    chunk_metadata_coverage,
    forbidden_source_hit_count,
    keyword_hit_rate,
    mean_reciprocal_rank,
    ndcg_at_k,
    permission_leak_count,
    recall_at_k,
    relevance_by_rank,
    retrieved_source_metadata_coverage,
    source_chunk_metadata_coverage,
    source_metadata_coverage,
)
from app.services.retrieval_evaluation_sources import build_retrieved_sources
from app.services.text_normalization_service import normalize_query


@dataclass(frozen=True)
class GoldenRetrievalQuery:
    """Describe one measurable retrieval expectation."""

    query: str
    expected_source_ids: tuple[int, ...] = ()
    expected_source_types: tuple[str, ...] = ()
    expected_sources: tuple[tuple[str, str], ...] = ()
    expected_keywords: tuple[str, ...] = ()
    forbidden_source_ids: tuple[int, ...] = ()
    forbidden_source_types: tuple[str, ...] = ()
    forbidden_sources: tuple[tuple[str, str], ...] = ()
    allowed_source_types: tuple[str, ...] = ()
    expected_no_result: bool = False
    min_source_count: int = 1
    required_permission_context: dict = field(default_factory=dict)
    expected_query_type: str = ""
    top_k: int = 4


def evaluate_golden_queries(golden_queries, user, retrieval_mode=RETRIEVAL_MODE_VECTOR):
    """Evaluate golden retrieval queries and return aggregate quality metrics."""
    mode = normalize_retrieval_mode(retrieval_mode)
    query_results = [
        _evaluate_query(_coerce_golden_query(item), user, mode) for item in golden_queries
    ]
    metric_results = [item for item in query_results if item["expected_count"] > 0]
    keyword_results = [item for item in query_results if item["expected_keyword_count"] > 0]
    keyword_miss_count = sum(len(item.get("missing_keywords") or []) for item in keyword_results)
    no_result_count = sum(1 for item in query_results if item["no_result"])
    expected_no_result_count = sum(1 for item in query_results if item["expected_no_result"])
    expected_no_result_success_count = sum(
        1 for item in query_results if item["expected_no_result_success"]
    )
    unexpected_no_result_count = sum(1 for item in query_results if item["unexpected_no_result"])
    min_source_count_fail_count = sum(
        1 for item in query_results if not item["min_source_count_met"]
    )
    query_type_expected_count = sum(1 for item in query_results if item["expected_query_type"])
    query_type_match_count = sum(1 for item in query_results if item["query_type_match"])
    return {
        "query_count": len(query_results),
        "metric_query_count": len(metric_results),
        "recall_at_k": average_metric(metric_results, "recall_at_k"),
        "mrr": average_metric(metric_results, "mrr"),
        "ndcg_at_k": average_metric(metric_results, "ndcg_at_k"),
        "keyword_query_count": len(keyword_results),
        "keyword_hit_rate": average_metric(keyword_results, "keyword_hit_rate"),
        "keyword_miss_count": keyword_miss_count,
        "permission_leak_count": sum(item["permission_leak_count"] for item in query_results),
        "forbidden_source_hit_count": sum(
            item["forbidden_source_hit_count"] for item in query_results
        ),
        "no_result_count": no_result_count,
        "no_result_rate": rate(no_result_count, len(query_results)),
        "expected_no_result_count": expected_no_result_count,
        "expected_no_result_success_count": expected_no_result_success_count,
        "expected_no_result_success_rate": rate(
            expected_no_result_success_count,
            expected_no_result_count,
        ),
        "unexpected_no_result_count": unexpected_no_result_count,
        "unexpected_no_result_rate": rate(
            unexpected_no_result_count,
            len(query_results) - expected_no_result_count,
        ),
        "min_source_count_fail_count": min_source_count_fail_count,
        "min_source_count_pass_rate": rate(
            len(query_results) - min_source_count_fail_count,
            len(query_results),
        ),
        "query_type_expected_count": query_type_expected_count,
        "query_type_match_count": query_type_match_count,
        "query_type_accuracy": rate(query_type_match_count, query_type_expected_count),
        "chunk_metadata_coverage": chunk_metadata_coverage(query_results),
        "source_metadata_coverage": source_metadata_coverage(query_results),
        "queries": query_results,
    }


def evaluate_and_persist_golden_queries(
    golden_queries,
    user,
    commit=True,
    retrieval_mode=RETRIEVAL_MODE_VECTOR,
):
    """Evaluate golden retrieval queries and persist the prompt-safe aggregate run."""
    result = evaluate_golden_queries(
        golden_queries,
        user,
        retrieval_mode=retrieval_mode,
    )
    run = persist_retrieval_evaluation_result(result, commit=commit)
    result["evaluation_run"] = run.to_dict()
    return result


def run_admin_golden_retrieval_evaluation(user, limit=20, commit=True):
    """Run the bounded admin golden evaluation against the full retrieval pipeline."""
    runtime_set = runtime_golden_questions(user=user, limit=limit)
    queries = [
        golden_retrieval_query_from_question(question) for question in runtime_set["questions"]
    ]
    result = evaluate_and_persist_golden_queries(
        queries,
        user,
        commit=commit,
        retrieval_mode=RETRIEVAL_MODE_FULL,
    )
    return _admin_evaluation_payload(
        result,
        question_set=runtime_set["question_set"],
    )


def golden_retrieval_query_from_question(question):
    """Return an evaluation query from a public golden question definition."""
    return GoldenRetrievalQuery(
        query=question.question,
        expected_source_types=tuple(question.expected_source_types),
        expected_sources=tuple(question.expected_sources),
        expected_keywords=tuple(question.expected_keywords),
        forbidden_sources=tuple(question.forbidden_sources),
        allowed_source_types=tuple(question.allowed_source_types),
        expected_no_result=bool(question.expected_no_result),
        min_source_count=positive_int(question.min_source_count, default=1),
        required_permission_context=dict(question.required_permission_context or {}),
        expected_query_type=str(question.expected_query_type or ""),
        top_k=positive_int(question.top_k, default=4),
    )


def _evaluate_query(golden_query, user, retrieval_mode):
    """Evaluate one golden query against the active retrieval stack."""
    top_k = positive_int(golden_query.top_k, default=4)
    min_source_count = positive_int(golden_query.min_source_count, default=1)
    retrieved_sources = build_retrieved_sources(golden_query, user, top_k, retrieval_mode)
    retrieved_source_count = len(retrieved_sources)
    expected_units = build_expected_units(golden_query)
    relevances, covered_units = relevance_by_rank(retrieved_sources, expected_units)
    expected_keywords = normalized_strings(golden_query.expected_keywords)
    matched_keywords = build_matched_keywords(retrieved_sources, expected_keywords)
    missing_keywords = build_missing_keywords(matched_keywords, expected_keywords)
    no_result = not retrieved_sources
    expected_no_result = bool(golden_query.expected_no_result)
    expected_query_type = str(golden_query.expected_query_type or "").strip()
    query_understanding = classify_query(golden_query.query)
    actual_query_type = str(query_understanding.query_type or "")
    return {
        "query": golden_query.query,
        "normalized_query": normalize_query(golden_query.query),
        "top_k": top_k,
        "min_source_count": min_source_count,
        "retrieved_source_count": retrieved_source_count,
        "min_source_count_met": (
            (expected_no_result and no_result) or retrieved_source_count >= min_source_count
        ),
        "retrieval_mode": retrieval_mode,
        "expected_count": len(expected_units),
        "expected_no_result": expected_no_result,
        "expected_no_result_success": expected_no_result and no_result,
        "unexpected_no_result": no_result and not expected_no_result,
        "expected_hit_count": len(covered_units),
        "expected_keyword_count": len(expected_keywords),
        "expected_keyword_hit_count": len(matched_keywords),
        "keyword_hit_rate": keyword_hit_rate(matched_keywords, expected_keywords),
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "expected_query_type": expected_query_type,
        "actual_query_type": actual_query_type,
        "query_type_match": (
            bool(expected_query_type) and actual_query_type == expected_query_type
        ),
        "query_type_confidence": round(float(query_understanding.confidence), 4),
        "recall_at_k": recall_at_k(covered_units, expected_units),
        "mrr": mean_reciprocal_rank(relevances),
        "ndcg_at_k": ndcg_at_k(relevances, expected_units, top_k),
        "permission_leak_count": permission_leak_count(
            golden_query.required_permission_context,
            retrieved_sources,
        ),
        "forbidden_source_hit_count": forbidden_source_hit_count(
            golden_query,
            retrieved_sources,
        ),
        "chunk_metadata_coverage": source_chunk_metadata_coverage(retrieved_sources),
        "source_metadata_coverage": retrieved_source_metadata_coverage(retrieved_sources),
        "no_result": no_result,
        "retrieved_sources": retrieved_sources,
        "required_permission_context": serializable_context(
            golden_query.required_permission_context,
        ),
    }


def _coerce_golden_query(value):
    """Return a GoldenRetrievalQuery from a dataclass or dictionary payload."""
    if isinstance(value, GoldenRetrievalQuery):
        return value
    if not isinstance(value, dict):
        raise TypeError("golden query must be a GoldenRetrievalQuery or dict")
    return GoldenRetrievalQuery(
        query=str(value.get("query") or ""),
        expected_source_ids=tuple(normalized_ints(value.get("expected_source_ids"))),
        expected_source_types=tuple(normalized_strings(value.get("expected_source_types"))),
        expected_sources=tuple(normalized_source_pairs(value.get("expected_sources"))),
        expected_keywords=tuple(normalized_strings(value.get("expected_keywords"))),
        forbidden_source_ids=tuple(normalized_ints(value.get("forbidden_source_ids"))),
        forbidden_source_types=tuple(normalized_strings(value.get("forbidden_source_types"))),
        forbidden_sources=tuple(normalized_source_pairs(value.get("forbidden_sources"))),
        allowed_source_types=tuple(normalized_strings(value.get("allowed_source_types"))),
        expected_no_result=bool_value(value.get("expected_no_result")),
        min_source_count=positive_int(value.get("min_source_count"), default=1),
        required_permission_context=dict(value.get("required_permission_context") or {}),
        expected_query_type=str(value.get("expected_query_type") or ""),
        top_k=positive_int(value.get("top_k"), default=4),
    )


def _admin_evaluation_payload(result, question_set):
    """Return prompt-safe admin output for a completed evaluation run."""
    payload = {
        "query_count": nonnegative_int(result.get("query_count")),
        "metric_query_count": nonnegative_int(result.get("metric_query_count")),
        "recall_at_k": clamped_metric(result.get("recall_at_k")),
        "mrr": clamped_metric(result.get("mrr")),
        "ndcg_at_k": clamped_metric(result.get("ndcg_at_k")),
        "keyword_hit_rate": clamped_metric(result.get("keyword_hit_rate")),
        "keyword_query_count": nonnegative_int(result.get("keyword_query_count")),
        "keyword_miss_count": nonnegative_int(result.get("keyword_miss_count")),
        "permission_leak_count": nonnegative_int(result.get("permission_leak_count")),
        "forbidden_source_hit_count": nonnegative_int(result.get("forbidden_source_hit_count")),
        "no_result_count": nonnegative_int(result.get("no_result_count")),
        "no_result_rate": clamped_metric(result.get("no_result_rate")),
        "expected_no_result_count": nonnegative_int(result.get("expected_no_result_count")),
        "expected_no_result_success_count": nonnegative_int(
            result.get("expected_no_result_success_count")
        ),
        "expected_no_result_success_rate": clamped_metric(
            result.get("expected_no_result_success_rate")
        ),
        "unexpected_no_result_count": nonnegative_int(result.get("unexpected_no_result_count")),
        "unexpected_no_result_rate": clamped_metric(result.get("unexpected_no_result_rate")),
        "min_source_count_fail_count": nonnegative_int(result.get("min_source_count_fail_count")),
        "min_source_count_pass_rate": clamped_metric(result.get("min_source_count_pass_rate")),
        "query_type_expected_count": nonnegative_int(result.get("query_type_expected_count")),
        "query_type_match_count": nonnegative_int(result.get("query_type_match_count")),
        "query_type_accuracy": clamped_metric(result.get("query_type_accuracy")),
        "chunk_metadata_coverage": safe_chunk_metadata_coverage(
            result.get("chunk_metadata_coverage")
        ),
        "source_metadata_coverage": safe_source_metadata_coverage(
            result.get("source_metadata_coverage")
        ),
        "evaluation_run": result.get("evaluation_run") or {},
        "question_set": question_set,
        "retrieval_mode": RETRIEVAL_MODE_FULL,
        "privacy": history_privacy_payload(),
    }
    payload["quality_gate"] = evaluation_quality_gate(payload)
    return payload
