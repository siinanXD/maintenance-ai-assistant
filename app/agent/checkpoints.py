"""LangGraph checkpointer selection for persistent agent session memory.

The checkpointer stores the agent graph state per thread (user + session).
Backends:

- ``memory``: in-process ``MemorySaver`` (tests, single process)
- ``sqlite``: file-backed ``SqliteSaver`` under the data folder
- ``postgres``: ``PostgresSaver`` on the application database
- ``none``: no checkpointer; history falls back to ``ChatMessage`` rows
- ``auto`` (default): postgres when the app database is PostgreSQL and the
  saver is installed, otherwise sqlite, otherwise memory
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from flask import current_app

logger = logging.getLogger(__name__)

EXTENSION_KEY = "agent_checkpointer"
_LOCK = threading.Lock()


def checkpointer_mode():
    """Return the configured checkpointer mode."""
    mode = str(current_app.config.get("AI_AGENT_CHECKPOINTER", "auto") or "auto").strip().lower()
    return mode if mode in {"auto", "none", "memory", "sqlite", "postgres"} else "auto"


def agent_checkpointer():
    """Return the app-scoped checkpointer instance and its backend name."""
    cached = current_app.extensions.get(EXTENSION_KEY)
    if cached is not None:
        return cached
    with _LOCK:
        cached = current_app.extensions.get(EXTENSION_KEY)
        if cached is not None:
            return cached
        saver, backend = _build_checkpointer(checkpointer_mode())
        current_app.extensions[EXTENSION_KEY] = (saver, backend)
        logger.info("agent_checkpointer_ready backend=%s", backend)
        return saver, backend


def _build_checkpointer(mode):
    """Create the checkpointer for a mode with graceful fallbacks."""
    if mode == "none":
        return None, "none"
    database_url = str(current_app.config.get("SQLALCHEMY_DATABASE_URI") or "")
    if mode in {"auto", "postgres"} and database_url.startswith("postgresql"):
        saver = _postgres_saver(database_url)
        if saver is not None:
            return saver, "postgres"
        if mode == "postgres":
            logger.warning("agent_checkpointer_fallback requested=postgres backend=memory")
            return _memory_saver(), "memory"
    if mode in {"auto", "sqlite"}:
        saver = _sqlite_saver()
        if saver is not None:
            return saver, "sqlite"
        if mode == "sqlite":
            logger.warning("agent_checkpointer_fallback requested=sqlite backend=memory")
    return _memory_saver(), "memory"


def _memory_saver():
    """Return an in-process checkpointer."""
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def _sqlite_saver():
    """Return a file-backed SQLite checkpointer or ``None`` when unavailable."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning("agent_checkpointer_unavailable backend=sqlite reason=package_missing")
        return None
    configured = str(current_app.config.get("AI_AGENT_CHECKPOINT_PATH") or "").strip()
    if configured == ":memory:":
        path = ":memory:"
    else:
        path = Path(configured or Path("data") / "agent_checkpoints.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        path = str(path)
    try:
        connection = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(connection)
        saver.setup()
    except Exception:  # pragma: no cover - filesystem/driver specific
        logger.exception("agent_checkpointer_setup_failed backend=sqlite")
        return None
    return saver


def _postgres_saver(database_url):
    """Return a PostgreSQL checkpointer or ``None`` when unavailable."""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row
    except ImportError:
        logger.warning("agent_checkpointer_unavailable backend=postgres reason=package_missing")
        return None
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        connection = Connection.connect(connection_url, autocommit=True, row_factory=dict_row)
        saver = PostgresSaver(connection)
        saver.setup()
    except Exception:  # pragma: no cover - requires live database
        logger.exception("agent_checkpointer_setup_failed backend=postgres")
        return None
    return saver
