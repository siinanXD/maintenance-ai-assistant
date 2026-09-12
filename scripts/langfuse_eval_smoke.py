#!/usr/bin/env python3
"""Smoke-check Langfuse tracing and automatic evaluation scores."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _bootstrap_environment() -> None:
    """Load environment variables before importing application modules."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")


def _find_admin_user():
    """Return an active master admin user when available."""
    from app.models import Role, User

    return (
        User.query.filter_by(is_active=True)
        .filter(User.role == Role.MASTER_ADMIN)
        .order_by(User.id.asc())
        .first()
    )


def main():
    """Run a minimal Langfuse eval smoke check inside one app context."""
    _bootstrap_environment()

    from app import create_app
    from app.agent.service import run_agent
    from app.services.ai_history_service import save_chat_message
    from app.services.ai_traceability_service import create_answer_trace
    from app.services.langfuse_eval_score_service import submit_automatic_eval_scores
    from app.services.langfuse_service import langfuse_eval_enabled, langfuse_status

    app = create_app()
    with app.app_context():
        status = langfuse_status()
        print("Langfuse status:", json.dumps(status, indent=2))
        print("Eval enabled:", langfuse_eval_enabled())

        if not status.get("ready"):
            print("SKIP: Langfuse is not ready (check keys, package, LANGFUSE_ENABLED).")
            return 1
        if not langfuse_eval_enabled():
            print("SKIP: LANGFUSE_EVAL_ENABLED is false.")
            return 1

        user = _find_admin_user()
        if user is None:
            print("SKIP: No active master_admin user in the database.")
            return 1

        message = "Welche offenen Wartungsaufgaben gibt es heute?"
        result = run_agent(message, user, session_id="langfuse-eval-smoke")
        chat_message = save_chat_message(user, message, result, session_id="langfuse-eval-smoke")
        if chat_message is None:
            print("FAIL: Could not persist chat message.")
            return 1

        trace = create_answer_trace(chat_message, result)
        diagnostics = result.get("diagnostics") or {}
        trace_id = diagnostics.get("langfuse_trace_id") or ""
        score_count = submit_automatic_eval_scores(diagnostics, {**result, "question": message})

        print("Chat message id:", chat_message.id)
        print("Langfuse trace id:", trace_id or "(missing – OpenAI trace required)")
        print("Answer trace:", getattr(trace, "answer_id", None))
        print("Automatic scores submitted:", score_count)
        print("Answer quality:", (result.get("answer_quality") or {}).get("status"))
        print("Hallucination warning:", diagnostics.get("hallucination_warning"))

        if not trace_id:
            print(
                "WARN: No langfuse_trace_id. Use an OpenAI-backed chat path or restart "
                "the app after enabling Langfuse.",
            )
            return 2
        if score_count <= 0:
            print("FAIL: Expected automatic Langfuse scores but none were submitted.")
            return 1

        print("OK: Langfuse eval smoke check passed.")
        print(
            "Next: open Langfuse, Traces, filter trace id, Scores tab "
            "(user-feedback after POST /api/v1/ai/feedback).",
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
