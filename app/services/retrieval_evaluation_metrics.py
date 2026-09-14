"""Recall, MRR, NDCG, keyword hits, permission leaks and metadata coverage per golden query."""

from math import log2

from app.services.retrieval_evaluation_common import (
    SAFE_SOURCE_METADATA_FIELDS,
    average_values,
    has_metadata_value,
    normalized_ints,
    normalized_source_pairs,
    normalized_strings,
    rate,
)
from app.services.retrieval_evaluation_sources import (
    collect_source_ids,
    collect_source_types,
    source_role_visibility,
)
from app.services.text_normalization_service import normalize_query


def chunk_metadata_coverage(query_results):
    """Return aggregate prompt-safe chunk metadata coverage for an evaluation run."""
    sources = [
        source
        for query_result in query_results
        for source in query_result.get("retrieved_sources", [])
    ]
    return source_chunk_metadata_coverage(sources)


def source_chunk_metadata_coverage(retrieved_sources):
    """Return prompt-safe chunk metadata coverage for retrieved sources."""
    chunk_sources = [source for source in retrieved_sources if source.get("chunk_id") is not None]
    measured_sources = [
        source for source in chunk_sources if source.get("chunk_char_count") is not None
    ]
    char_counts = [
        source.get("chunk_char_count")
        for source in measured_sources
        if source.get("chunk_char_count") is not None
    ]
    token_counts = [
        source.get("chunk_token_count")
        for source in measured_sources
        if source.get("chunk_token_count") is not None
    ]
    block_counts = [
        source.get("chunk_block_count")
        for source in chunk_sources
        if source.get("chunk_block_count") is not None
    ]
    block_kind_counter = {}
    for source in chunk_sources:
        for block_kind in source.get("chunk_block_kinds") or []:
            block_key = str(block_kind)
            block_kind_counter[block_key] = block_kind_counter.get(block_key, 0) + 1
    return {
        "retrieved_chunk_count": len(chunk_sources),
        "measured_chunk_count": len(measured_sources),
        "coverage_rate": rate(len(measured_sources), len(chunk_sources)),
        "average_char_count": average_values(char_counts),
        "average_token_count": average_values(token_counts),
        "block_metadata_count": len(block_counts),
        "block_metadata_coverage_rate": rate(len(block_counts), len(chunk_sources)),
        "average_block_count": average_values(block_counts),
        "block_kind_distribution": block_kind_counter,
    }


def source_metadata_coverage(query_results):
    """Return aggregate safe source metadata coverage for an evaluation run."""
    sources = [
        source
        for query_result in query_results
        for source in query_result.get("retrieved_sources", [])
    ]
    return retrieved_source_metadata_coverage(sources)


def retrieved_source_metadata_coverage(retrieved_sources):
    """Return coverage of safe source IDs and types used for evaluation matching."""
    sources = list(retrieved_sources or [])
    with_source_id = [source for source in sources if collect_source_ids(source)]
    with_source_type = [source for source in sources if collect_source_types(source)]
    with_metadata_pair = [
        source
        for source in sources
        if source.get("metadata_source_type") and source.get("metadata_source_id") is not None
    ]
    with_any_pair = [
        source for source in sources if collect_source_ids(source) and collect_source_types(source)
    ]
    return {
        "retrieved_source_count": len(sources),
        "with_source_id_count": len(with_source_id),
        "with_source_type_count": len(with_source_type),
        "with_source_pair_count": len(with_any_pair),
        "with_metadata_pair_count": len(with_metadata_pair),
        "source_id_coverage_rate": rate(len(with_source_id), len(sources)),
        "source_type_coverage_rate": rate(len(with_source_type), len(sources)),
        "source_pair_coverage_rate": rate(len(with_any_pair), len(sources)),
        "metadata_pair_coverage_rate": rate(len(with_metadata_pair), len(sources)),
        "field_coverage": _safe_source_field_coverage(sources),
    }


def _safe_source_field_coverage(sources):
    """Return per-field coverage for safe public source metadata."""
    source_count = len(sources)
    return {
        field: {
            "with_value_count": sum(
                1 for source in sources if has_metadata_value(source.get(field))
            ),
            "coverage_rate": rate(
                sum(1 for source in sources if has_metadata_value(source.get(field))),
                source_count,
            ),
        }
        for field in SAFE_SOURCE_METADATA_FIELDS
    }


def build_expected_units(golden_query):
    """Return normalized expectation units for matching retrieved sources."""
    expected = {
        ("source_id", source_id) for source_id in normalized_ints(golden_query.expected_source_ids)
    }
    expected.update(
        ("source_type", source_type)
        for source_type in normalized_strings(golden_query.expected_source_types)
    )
    expected.update(
        ("source_pair", source_type, source_id)
        for source_type, source_id in normalized_source_pairs(golden_query.expected_sources)
    )
    return expected


def _source_units(source):
    """Return normalized units represented by one retrieved source."""
    units = set()
    if source["source_id"] is not None:
        units.add(("source_id", source["source_id"]))
    if source["source_type"]:
        units.add(("source_type", source["source_type"]))
    if source.get("metadata_source_id") is not None:
        units.add(("source_id", source["metadata_source_id"]))
    if source.get("metadata_source_type"):
        units.add(("source_type", source["metadata_source_type"]))
    for source_type in collect_source_types(source):
        for source_id in collect_source_ids(source):
            units.add(("source_pair", source_type, str(source_id)))
    return units


def relevance_by_rank(retrieved_sources, expected_units):
    """Return binary relevance per rank and covered expectation units."""
    covered_units = set()
    relevances = []
    for source in retrieved_sources:
        new_hits = (_source_units(source) & expected_units) - covered_units
        relevances.append(1 if new_hits else 0)
        covered_units.update(new_hits)
    return relevances, covered_units


def recall_at_k(covered_units, expected_units):
    """Return Recall@K for one evaluated query."""
    if not expected_units:
        return 0.0
    return round(len(covered_units) / len(expected_units), 4)


def mean_reciprocal_rank(relevances):
    """Return reciprocal rank for the first relevant result."""
    for index, relevance in enumerate(relevances, start=1):
        if relevance:
            return round(1 / index, 4)
    return 0.0


def ndcg_at_k(relevances, expected_units, top_k):
    """Return a simple binary nDCG@K for one query."""
    if not expected_units:
        return 0.0
    dcg = sum(
        relevance / log2(index + 1)
        for index, relevance in enumerate(relevances[:top_k], start=1)
        if relevance
    )
    ideal_relevance_count = min(len(expected_units), top_k)
    idcg = sum(1 / log2(index + 1) for index in range(1, ideal_relevance_count + 1))
    if idcg <= 0:
        return 0.0
    return round(min(dcg / idcg, 1.0), 4)


def build_matched_keywords(retrieved_sources, expected_keywords):
    """Return expected keywords found in retrieved title or content text."""
    if not expected_keywords:
        return []
    search_text = normalize_query(
        " ".join(
            " ".join(
                str(source.get(key) or "")
                for key in (
                    "title",
                    "source_type",
                    "metadata_source_type",
                    "quality_status",
                    "content",
                )
            )
            for source in retrieved_sources
        )
    )
    return [
        keyword
        for keyword in expected_keywords
        if normalize_query(keyword) and normalize_query(keyword) in search_text
    ]


def keyword_hit_rate(matched_keywords, expected_keywords):
    """Return how many expected keywords appeared in retrieved source text."""
    if not expected_keywords:
        return 0.0
    return round(len(set(matched_keywords)) / len(set(expected_keywords)), 4)


def build_missing_keywords(matched_keywords, expected_keywords):
    """Return expected keywords that were absent from retrieved source text."""
    matched = {normalize_query(keyword) for keyword in matched_keywords}
    return [
        keyword
        for keyword in expected_keywords
        if normalize_query(keyword) and normalize_query(keyword) not in matched
    ]


def permission_leak_count(permission_context, retrieved_sources):
    """Return how many retrieved sources violate the expected permission context."""
    context = dict(permission_context or {})
    forbidden_ids = set(normalized_ints(context.get("forbidden_source_ids")))
    forbidden_types = set(normalized_strings(context.get("forbidden_source_types")))
    forbidden_visibility = set(normalized_strings(context.get("forbidden_role_visibility")))
    allowed_ids = set(normalized_ints(context.get("allowed_source_ids")))
    allowed_types = set(normalized_strings(context.get("allowed_source_types")))
    allowed_visibility = set(normalized_strings(context.get("allowed_role_visibility")))
    leaks = 0
    for source in retrieved_sources:
        source_types = collect_source_types(source)
        role_visibility = source_role_visibility(source)
        if _source_id_hit(source, forbidden_ids) or source_types & forbidden_types:
            leaks += 1
            continue
        if role_visibility & forbidden_visibility:
            leaks += 1
            continue
        if allowed_ids and not _source_id_hit(source, allowed_ids):
            leaks += 1
            continue
        if allowed_types and not (source_types & allowed_types):
            leaks += 1
            continue
        if allowed_visibility and not (role_visibility & allowed_visibility):
            leaks += 1
    return leaks


def forbidden_source_hit_count(golden_query, retrieved_sources):
    """Return how many forbidden sources appeared in retrieval results."""
    forbidden_ids = set(normalized_ints(golden_query.forbidden_source_ids))
    forbidden_types = set(normalized_strings(golden_query.forbidden_source_types))
    forbidden_sources = set(normalized_source_pairs(golden_query.forbidden_sources))
    allowed_types = set(normalized_strings(golden_query.allowed_source_types))
    return sum(
        1
        for source in retrieved_sources
        if _source_id_hit(source, forbidden_ids)
        or (collect_source_types(source) & forbidden_types)
        or _source_pair_hit(source, forbidden_sources)
        or (allowed_types and not (collect_source_types(source) & allowed_types))
    )


def _source_pair_hit(source, source_pairs):
    """Return whether a retrieved source matches any source type/id pair."""
    source_types = collect_source_types(source)
    if not source_types:
        return False
    candidate_ids = collect_source_ids(source)
    return any(
        (source_type, str(candidate_id)) in source_pairs
        for source_type in source_types
        for candidate_id in candidate_ids
    )


def _source_id_hit(source, source_ids):
    """Return whether a retrieved source matches any public or record id."""
    candidate_ids = collect_source_ids(source)
    return bool(candidate_ids & source_ids)
