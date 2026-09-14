"""Consistent API response helpers."""

from flask import jsonify
from flask import request as _request


def error_code_from_message(message):
    """Return a short stable error code from a human-readable message."""
    text = str(message or "request failed").strip().lower()
    code = []
    for character in text:
        if character.isalnum():
            code.append(character)
        elif code and code[-1] != "_":
            code.append("_")
    normalized = "".join(code).strip("_")
    return normalized[:80] or "request_failed"


def error_payload(message):
    """Return a consistent API error payload."""
    text = str(message or "Request failed")
    return {
        "success": False,
        "message": text,
        "error": error_code_from_message(text),
    }


def error_response(message, status_code=400):
    """Return a Flask JSON response for an API error."""
    return jsonify(error_payload(message)), status_code


def service_error_response(error, status_code=400):
    """Return a normalized error response from a service error payload."""
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or "Request failed"
        payload = error_payload(message)
        for key, value in error.items():
            if key not in {"error", "message"}:
                payload[key] = value
        return jsonify(payload), status_code
    else:
        message = error or "Request failed"
    return error_response(message, status_code)


def success_payload(data=None, message=None):
    """Return a consistent API success payload.

    A dict is the response body: its keys sit on the root next to ``data``,
    so a result that carries its own ``data`` (agent answers) keeps that shape.
    ``success`` is always true; ``message`` comes from the argument, else from
    the body, else ``OK``.
    """
    payload = {"success": True, "data": data, "message": "OK"}
    if isinstance(data, dict):
        payload.update({key: value for key, value in data.items() if key != "success"})
    if message is not None:
        payload["message"] = message
    payload["message"] = payload["message"] or "OK"
    return payload


def success_response(data=None, status_code=200, message=None):
    """Return a Flask JSON response for a successful API operation."""
    return jsonify(success_payload(data, message)), status_code


def paginate_query(query, serializer):
    """Return a paginated JSON response for a SQLAlchemy query.

    Reads ?page= and ?limit= from the current request. page defaults to 1,
    limit defaults to 20, max limit is 100.

    Response shape:
        {"success": true, "data": [...], "pagination": {"page": 1, "limit": 20,
         "total": N, "pages": N}, "message": "OK"}
    """
    try:
        page = max(1, int(_request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = min(max(1, int(_request.args.get("limit", 20))), 100)
    except (TypeError, ValueError):
        limit = 20

    total = query.count()
    items = query.offset((page - 1) * limit).limit(limit).all()
    return jsonify(
        {
            "success": True,
            "data": [serializer(item) for item in items],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": max(1, (total + limit - 1) // limit),
            },
            "message": "OK",
        }
    )


def pagination_requested(args=None):
    """Return whether request arguments explicitly ask for pagination."""
    source = args if args is not None else _request.args
    return any(key in source for key in ("limit", "offset", "page", "paginate"))


def parse_pagination_args(args=None, default_limit=20, max_limit=100):
    """Return normalized page, limit and offset values from request arguments."""
    source = args if args is not None else _request.args
    limit = _safe_positive_int(source.get("limit"), default_limit)
    limit = min(limit, max_limit)
    if source.get("offset") is not None:
        offset = _safe_non_negative_int(source.get("offset"), 0)
        page = (offset // limit) + 1
        return page, limit, offset
    page = _safe_positive_int(source.get("page"), 1)
    return page, limit, (page - 1) * limit


def optional_paginated_response(
    query,
    serializer,
    message="OK",
    default_limit=20,
    max_limit=100,
):
    """Return an old array response unless the client requested pagination."""
    if not pagination_requested():
        return jsonify([serializer(item) for item in query.all()])

    page, limit, offset = parse_pagination_args(
        default_limit=default_limit,
        max_limit=max_limit,
    )
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return success_response(
        {
            "items": [serializer(item) for item in items],
            "pagination": {
                "page": page,
                "limit": limit,
                "offset": offset,
                "total": total,
                "pages": max(1, (total + limit - 1) // limit),
            },
        },
        message=message,
    )


def _safe_positive_int(value, default):
    """Return a positive integer or the provided default."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _safe_non_negative_int(value, default):
    """Return a non-negative integer or the provided default."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
