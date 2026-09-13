"""Central MongoDB connection and maintenance_ai database bootstrap."""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app, has_app_context

logger = logging.getLogger(__name__)

DEFAULT_MONGODB_DB_NAME = "maintenance_ai"
DEFAULT_MONGODB_TIMEOUT_MS = 3000

MAINTENANCE_MONGODB_COLLECTIONS = (
    "users",
    "roles",
    "employees",
    "machines",
    "tasks",
    "errors",
    "maintenance_reports",
    "shiftplans",
    "handovers",
    "vacations",
    "inventory",
    "documents",
    "document_chunks",
    "chat_sessions",
    "chat_messages",
    "ai_answers",
    "feedback",
    "audit_logs",
)

MAINTENANCE_MONGODB_INDEX_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "users": ({"keys": [("email", 1)], "unique": True, "name": "users_email_unique"},),
    "employees": ({"keys": [("employee_id", 1)], "name": "employees_employee_id"},),
    "machines": ({"keys": [("machine_id", 1)], "name": "machines_machine_id"},),
    "tasks": (
        {"keys": [("status", 1)], "name": "tasks_status"},
        {"keys": [("due_date", 1)], "name": "tasks_due_date"},
    ),
    "errors": (
        {"keys": [("machine_id", 1)], "name": "errors_machine_id"},
        {"keys": [("status", 1)], "name": "errors_status"},
    ),
    "documents": ({"keys": [("source_type", 1)], "name": "documents_source_type"},),
    "document_chunks": ({"keys": [("document_id", 1)], "name": "document_chunks_document_id"},),
    "chat_sessions": ({"keys": [("user_id", 1)], "name": "chat_sessions_user_id"},),
    "chat_messages": ({"keys": [("session_id", 1)], "name": "chat_messages_session_id"},),
    "ai_answers": ({"keys": [("session_id", 1)], "name": "ai_answers_session_id"},),
    "audit_logs": ({"keys": [("created_at", 1)], "name": "audit_logs_created_at"},),
}

_MONGODB_CLIENT = None


class MongoDBServiceError(Exception):
    """Raised when MongoDB connectivity or bootstrap fails."""


def mongodb_is_configured(config=None):
    """Return whether a MongoDB URI is configured for the maintenance database."""
    return bool(mongodb_uri(config))


def mongodb_uri(config=None):
    """Return the configured MongoDB URI without logging secret values."""
    settings = _config(config)
    return str(settings.get("MONGODB_URI") or settings.get("MONGODB_ATLAS_URI") or "").strip()


def mongodb_database_name(config=None):
    """Return the configured maintenance MongoDB database name."""
    settings = _config(config)
    return str(
        settings.get("MONGODB_DB_NAME")
        or settings.get("MONGODB_ATLAS_DATABASE")
        or DEFAULT_MONGODB_DB_NAME
    ).strip()


def mongodb_timeout_ms(config=None):
    """Return the MongoDB client timeout in milliseconds."""
    settings = _config(config)
    return _positive_int(
        settings.get("MONGODB_TIMEOUT_MS") or settings.get("MONGODB_ATLAS_TIMEOUT_MS"),
        DEFAULT_MONGODB_TIMEOUT_MS,
    )


def get_mongodb_client(config=None, force_new=False):
    """Return a shared MongoDB client for the configured maintenance cluster."""
    global _MONGODB_CLIENT
    settings = _config(config)
    uri = mongodb_uri(settings)
    if not uri:
        raise MongoDBServiceError("mongodb_not_configured")

    if _MONGODB_CLIENT is not None and not force_new:
        return _MONGODB_CLIENT

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise MongoDBServiceError("pymongo_missing") from exc

    timeout_ms = mongodb_timeout_ms(settings)
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
    )
    client.admin.command("ping")
    _MONGODB_CLIENT = client
    return client


def get_mongodb_database(config=None):
    """Return the configured maintenance MongoDB database handle."""
    database_name = mongodb_database_name(config)
    if not database_name:
        raise MongoDBServiceError("mongodb_database_missing")
    client = get_mongodb_client(config)
    return client[database_name]


def ensure_maintenance_mongodb_ready(config=None):
    """Create missing maintenance_ai collections and indexes without touching other DBs."""
    settings = _config(config)
    if not mongodb_is_configured(settings):
        return {
            "configured": False,
            "ok": True,
            "skipped": True,
            "database": mongodb_database_name(settings),
            "collections_created": [],
            "indexes_created": [],
        }

    database_name = mongodb_database_name(settings)
    try:
        database = get_mongodb_database(settings)
        existing = set(database.list_collection_names())
        collections_created = []
        indexes_created = []

        for collection_name in MAINTENANCE_MONGODB_COLLECTIONS:
            if collection_name not in existing:
                database.create_collection(collection_name)
                collections_created.append(collection_name)
                existing.add(collection_name)

            for index_spec in MAINTENANCE_MONGODB_INDEX_SPECS.get(collection_name, ()):
                collection = database[collection_name]
                index_name = index_spec["name"]
                if index_name not in collection.index_information():
                    collection.create_index(
                        index_spec["keys"],
                        name=index_name,
                        unique=index_spec.get("unique", False),
                    )
                    indexes_created.append(f"{collection_name}.{index_name}")

        logger.info(
            "mongodb_bootstrap database=%s collections_created=%s indexes_created=%s",
            database_name,
            len(collections_created),
            len(indexes_created),
        )
        return {
            "configured": True,
            "ok": True,
            "skipped": False,
            "database": database_name,
            "collections_created": collections_created,
            "indexes_created": indexes_created,
        }
    except MongoDBServiceError as exc:
        logger.warning(
            "mongodb_bootstrap_failed database=%s reason=%s",
            database_name,
            exc,
        )
        return {
            "configured": True,
            "ok": False,
            "skipped": False,
            "database": database_name,
            "reason": str(exc),
            "collections_created": [],
            "indexes_created": [],
        }
    except Exception as exc:
        logger.warning(
            "mongodb_bootstrap_failed database=%s error=%s",
            database_name,
            exc.__class__.__name__,
        )
        return {
            "configured": True,
            "ok": False,
            "skipped": False,
            "database": database_name,
            "reason": exc.__class__.__name__,
            "collections_created": [],
            "indexes_created": [],
        }


def reset_mongodb_client_cache():
    """Reset the cached MongoDB client (used by tests)."""
    global _MONGODB_CLIENT
    if _MONGODB_CLIENT is not None:
        try:
            _MONGODB_CLIENT.close()
        except Exception:
            pass
    _MONGODB_CLIENT = None


def _config(config=None):
    if config is not None:
        return config
    if has_app_context():
        return current_app.config
    return {}


def _positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
