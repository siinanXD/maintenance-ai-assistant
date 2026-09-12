"""In-process per-user rate limiting for AI chat and assistant endpoints.

The limiter is intentionally simple: a sliding window per user held in the
Flask app extensions. It protects one web process against runaway LLM usage
and gives a clear ``429`` with ``Retry-After``. Multi-process deployments get
one window per worker; a shared store can replace the backend later without
touching the call sites.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from flask import current_app

EXTENSION_KEY = "ai_rate_limit"
DEFAULT_AI_CHAT_RATE_LIMIT_PER_MINUTE = 30
WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitDecision:
    """Outcome of one rate-limit check."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

    def headers(self):
        """Return standard rate-limit response headers."""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
        }
        if not self.allowed:
            headers["Retry-After"] = str(max(1, self.retry_after_seconds))
        return headers


class AIRateLimiter:
    """Thread-safe sliding-window limiter keyed by an arbitrary identifier."""

    def __init__(self):
        """Create an empty limiter."""
        self._lock = threading.Lock()
        self._windows = {}

    def check(self, key, limit, window_seconds=WINDOW_SECONDS, now=None):
        """Register one request for ``key`` and return the limit decision."""
        if limit <= 0:
            return RateLimitDecision(True, 0, 0, 0)
        current = time.monotonic() if now is None else now
        cutoff = current - window_seconds
        with self._lock:
            window = self._windows.setdefault(key, deque())
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) >= limit:
                retry_after = int(window[0] + window_seconds - current) + 1
                return RateLimitDecision(False, limit, 0, max(1, retry_after))
            window.append(current)
            return RateLimitDecision(True, limit, limit - len(window), 0)

    def reset(self):
        """Forget all recorded requests."""
        with self._lock:
            self._windows.clear()


def chat_rate_limit_per_minute():
    """Return the configured per-user AI request limit per minute."""
    try:
        return int(
            current_app.config.get(
                "AI_CHAT_RATE_LIMIT_PER_MINUTE",
                DEFAULT_AI_CHAT_RATE_LIMIT_PER_MINUTE,
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_AI_CHAT_RATE_LIMIT_PER_MINUTE


def rate_limiter():
    """Return the app-scoped limiter instance."""
    limiter = current_app.extensions.get(EXTENSION_KEY)
    if limiter is None:
        limiter = AIRateLimiter()
        current_app.extensions[EXTENSION_KEY] = limiter
    return limiter


def check_ai_rate_limit(user, bucket="ai"):
    """Register one AI request for a user and return the limit decision."""
    key = (bucket, getattr(user, "id", None) or "anonymous")
    return rate_limiter().check(key, chat_rate_limit_per_minute())


def rate_limited_response(decision):
    """Return a JSON 429 response for a rejected AI request."""
    from app.responses import error_response

    response, status = error_response("AI request rate limit exceeded", 429)
    for header, value in decision.headers().items():
        response.headers[header] = value
    return response, status


@dataclass(frozen=True)
class TokenBudgetDecision:
    """Outcome of one daily token budget check."""

    allowed: bool
    budget: int
    used: int

    @property
    def remaining(self):
        """Return the remaining budget for today."""
        return max(0, self.budget - self.used)


def daily_token_budget():
    """Return the configured per-user daily token budget (0 disables)."""
    try:
        return max(0, int(current_app.config.get("AI_DAILY_TOKEN_BUDGET_PER_USER", 0) or 0))
    except (TypeError, ValueError):
        return 0


def check_daily_token_budget(user):
    """Return whether the user still has token budget for today."""
    budget = daily_token_budget()
    if budget <= 0:
        return TokenBudgetDecision(True, 0, 0)
    from datetime import UTC, datetime

    from sqlalchemy import func

    from app.extensions import db
    from app.models import AIAuditEvent

    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        db.session.query(func.coalesce(func.sum(AIAuditEvent.total_tokens), 0))
        .filter(
            AIAuditEvent.user_id == getattr(user, "id", None),
            AIAuditEvent.created_at >= start_of_day,
        )
        .scalar()
        or 0
    )
    return TokenBudgetDecision(int(used) < budget, budget, int(used))


def token_budget_exceeded_response(decision):
    """Return a JSON 429 response when the daily token budget is exhausted."""
    from app.responses import error_response

    response, status = error_response("AI daily token budget exceeded", 429)
    response.headers["X-AI-Token-Budget"] = str(decision.budget)
    response.headers["X-AI-Token-Used"] = str(decision.used)
    return response, status


def check_ai_quota(user, bucket="ai"):
    """Return a rejected response for exhausted quotas, otherwise ``None``."""
    rate_limit = check_ai_rate_limit(user, bucket=bucket)
    if not rate_limit.allowed:
        return rate_limited_response(rate_limit)
    budget = check_daily_token_budget(user)
    if not budget.allowed:
        return token_budget_exceeded_response(budget)
    return None
