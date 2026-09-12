"""Tests for per-user AI request rate limiting."""

from app.services.ai_rate_limit_service import AIRateLimiter


def test_rate_limiter_uses_sliding_window():
    """Verify the limiter blocks the request that exceeds the window and recovers."""
    limiter = AIRateLimiter()

    first = limiter.check("user", limit=2, window_seconds=60, now=100.0)
    second = limiter.check("user", limit=2, window_seconds=60, now=101.0)
    third = limiter.check("user", limit=2, window_seconds=60, now=102.0)
    later = limiter.check("user", limit=2, window_seconds=60, now=161.0)

    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0
    assert third.allowed is False
    assert third.retry_after_seconds >= 1
    assert third.headers()["Retry-After"] == str(third.retry_after_seconds)
    assert later.allowed is True


def test_rate_limiter_is_disabled_for_zero_limit():
    """Verify a zero limit disables rate limiting."""
    limiter = AIRateLimiter()

    for _ in range(5):
        assert limiter.check("user", limit=0).allowed is True


def test_ai_chat_returns_429_when_user_exceeds_limit(app, client, make_user, auth_headers):
    """Verify the chat endpoint rejects requests above the per-user limit."""
    user = make_user(username="rate_limited_chat_user")
    app.config["AI_CHAT_RATE_LIMIT_PER_MINUTE"] = 2
    headers = auth_headers(user["username"])

    responses = [
        client.post("/api/v1/ai/chat", headers=headers, json={"message": "Welche Tasks?"})
        for _ in range(3)
    ]

    assert [response.status_code for response in responses[:2]] == [200, 200]
    assert responses[2].status_code == 429
    assert responses[2].headers["Retry-After"]
    assert responses[2].get_json()["error"] == "ai_request_rate_limit_exceeded"


def test_ai_rate_limit_is_scoped_per_user(app, client, make_user, auth_headers):
    """Verify one user's usage does not block another user."""
    first = make_user(username="rate_limit_user_a")
    second = make_user(username="rate_limit_user_b")
    app.config["AI_CHAT_RATE_LIMIT_PER_MINUTE"] = 1

    first_response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(first["username"]),
        json={"message": "Welche Tasks?"},
    )
    blocked_response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(first["username"]),
        json={"message": "Welche Tasks?"},
    )
    second_response = client.post(
        "/api/v1/ai/chat",
        headers=auth_headers(second["username"]),
        json={"message": "Welche Tasks?"},
    )

    assert first_response.status_code == 200
    assert blocked_response.status_code == 429
    assert second_response.status_code == 200
