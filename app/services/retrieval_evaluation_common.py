"""Thresholds, safe field names and value coercion shared by the retrieval evaluation modules."""

REGRESSION_DROP_THRESHOLD = 0.05


REGRESSION_COUNT_INCREASE_THRESHOLD = 1


QUALITY_WARNING_THRESHOLDS = {
    "recall_at_k": 0.75,
    "mrr": 0.5,
    "keyword_hit_rate": 0.6,
    "expected_no_result_success_rate": 0.8,
    "unexpected_no_result_rate": 0.1,
    "min_source_count_pass_rate": 0.8,
    "query_type_accuracy": 0.7,
    "source_pair_coverage_rate": 0.8,
    "metadata_pair_coverage_rate": 0.6,
    "block_metadata_coverage_rate": 0.8,
}


DEFAULT_HISTORY_LIMIT = 10


MAX_HISTORY_LIMIT = 50


RETRIEVAL_MODE_VECTOR = "vector"


RETRIEVAL_MODE_FULL = "full"


SAFE_SOURCE_METADATA_FIELDS = (
    "source_id",
    "source_type",
    "title",
    "module",
    "machine_id",
    "role_visibility",
    "created_at",
)


def has_metadata_value(value):
    """Return whether a metadata value is present without treating zero as missing."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def average_metric(query_results, key):
    """Return the rounded average metric for evaluated queries."""
    if not query_results:
        return 0.0
    return round(sum(item[key] for item in query_results) / len(query_results), 4)


def average_values(values):
    """Return a rounded average for optional numeric evaluation values."""
    numeric_values = [float(value) for value in values if value is not None]
    if not numeric_values:
        return 0.0
    return round(sum(numeric_values) / len(numeric_values), 4)


def rate(count, total):
    """Return a rounded zero-to-one rate."""
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def serializable_context(context):
    """Return a JSON-safe copy of the permission context."""
    payload = {}
    for key, value in dict(context or {}).items():
        if isinstance(value, set | tuple | list):
            payload[str(key)] = list(value)
        else:
            payload[str(key)] = value
    return payload


def normalized_ints(values):
    """Return valid integer values from an optional scalar or sequence."""
    if values in (None, ""):
        return []
    if isinstance(values, int):
        return [values]
    if isinstance(values, str):
        values = [values]
    normalized = []
    for value in values:
        parsed = optional_int(value)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def normalized_strings(values):
    """Return non-empty normalized string values from an optional scalar or sequence."""
    if values in (None, ""):
        return []
    if isinstance(values, str):
        values = [values]
    return [str(value).strip() for value in values if str(value).strip()]


def normalized_source_pairs(values):
    """Return normalized public source type/id pairs."""
    if values in (None, ""):
        return []
    normalized = []
    for value in values:
        if not isinstance(value, list | tuple) or len(value) != 2:
            continue
        source_type = str(value[0] or "").strip()
        source_id = str(value[1] or "").strip()
        if source_type and source_id:
            normalized.append((source_type, source_id))
    return normalized


def optional_int(value):
    """Return an integer when value can be parsed, otherwise None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def bool_value(value):
    """Return a safe boolean for optional dictionary payload values."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def safe_created_at(value):
    """Return a bounded timestamp string for source metadata diagnostics."""
    if value in (None, ""):
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:80]
    return str(value).strip()[:80]


def chunk_block_kinds(value):
    """Return prompt-safe chunk block kind labels from chunk metadata."""
    if value in (None, ""):
        return []
    raw_values = value if isinstance(value, list | tuple | set) else str(value).split(",")
    kinds = []
    for raw_value in raw_values:
        kind = str(raw_value or "").strip()[:80]
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds[:12]


def safe_string_int_mapping(value):
    """Return a bounded string-to-count mapping for diagnostic distributions."""
    if not isinstance(value, dict):
        return {}
    rows = {}
    for key, count in value.items():
        safe_key = str(key or "").strip()[:80]
        if safe_key:
            rows[safe_key] = nonnegative_int(count)
    return rows


def positive_int(value, default):
    """Return a positive integer or a default fallback."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def clamped_metric(value):
    """Return a bounded zero-to-one evaluation metric."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, parsed)), 4)


def nonnegative_int(value):
    """Return a non-negative integer for persisted evaluation counts."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def nonnegative_float(value):
    """Return a non-negative rounded float for prompt-safe diagnostics."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, parsed), 4)


def history_limit(value):
    """Return a bounded history limit."""
    return min(MAX_HISTORY_LIMIT, positive_int(value, default=DEFAULT_HISTORY_LIMIT))


def normalize_retrieval_mode(value):
    """Return a supported retrieval evaluation mode."""
    mode = str(value or RETRIEVAL_MODE_VECTOR).strip().lower()
    if mode in {RETRIEVAL_MODE_VECTOR, RETRIEVAL_MODE_FULL}:
        return mode
    raise ValueError("retrieval_mode must be 'vector' or 'full'")
