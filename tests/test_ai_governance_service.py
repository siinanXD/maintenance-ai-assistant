"""Tests for AI governance alert evaluation."""

from pathlib import Path

from app.services.ai_governance_service import evaluate_governance_alerts
from app.services.ai_observability_service import ai_observability_dashboard
from app.services.vector_sync_status_service import (
    clear_vector_sync_observability,
    record_atlas_error,
    record_atlas_query,
)


def test_governance_alerts_detect_observability_and_vector_risks(app):
    """Verify governance detects no-source, retrieval, cost, token and vector risks."""
    with app.app_context():
        app.config.update(
            AI_GOVERNANCE_COST_SPIKE_MIN_USD=0.01,
            AI_GOVERNANCE_EXCESSIVE_TOKEN_USAGE_WARNING=100,
            AI_GOVERNANCE_EXCESSIVE_TOKEN_USAGE_CRITICAL=200,
        )
        payload = evaluate_governance_alerts(
            {
                "total_requests": 12,
                "no_source_rate": 0.5,
                "retrieval_hit_rate": 0.5,
                "p95_retrieval_ms": 3500,
                "total_tokens": 300,
                "hallucination_warning_count": 6,
                "costs": {"day": 0.3, "week": 0.35},
            },
            vector_drift={
                "fallback_active": True,
                "store_error": "TimeoutError",
                "vector_sync_failure_count": 4,
                "atlas_errors": 4,
                "atlas_fallbacks": 1,
                "atlas_sync_failures": 2,
                "atlas_reindex_required": True,
            },
        )

    alert_rules = {alert["rule"] for alert in payload["alerts"]}
    assert payload["status"] == "critical"
    assert payload["critical_count"] >= 1
    assert "high_no_source_rate" in alert_rules
    assert "retrieval_degradation" in alert_rules
    assert "retrieval_latency" in alert_rules
    assert "excessive_token_usage" in alert_rules
    assert "hallucination_risk" in alert_rules
    assert "sync_failures" in alert_rules
    assert "atlas_errors" in alert_rules
    assert "atlas_fallbacks" in alert_rules
    assert "atlas_sync_failures" in alert_rules
    assert "atlas_sync_drift" in alert_rules
    assert "unusual_cost_increase" in alert_rules
    assert "vector_store_failure" in alert_rules
    assert "vector_store_fallback" in alert_rules
    assert "TimeoutError" not in str(payload)


def test_governance_alerts_are_configurable(app):
    """Verify configurable thresholds change alert evaluation."""
    with app.app_context():
        app.config.update(
            AI_GOVERNANCE_HIGH_NO_SOURCE_RATE_WARNING=0.8,
            AI_GOVERNANCE_HIGH_NO_SOURCE_RATE_CRITICAL=0.9,
        )
        payload = evaluate_governance_alerts(
            {"total_requests": 5, "no_source_rate": 0.5, "retrieval_hit_rate": 1.0},
            vector_drift={},
        )

    assert all(alert["rule"] != "high_no_source_rate" for alert in payload["alerts"])
    configured_rule = next(
        rule for rule in payload["rules"] if rule["key"] == "high_no_source_rate"
    )
    assert configured_rule["warning"] == 0.8
    assert configured_rule["critical"] == 0.9


def test_governance_can_be_disabled(app):
    """Verify governance alerting can be disabled globally."""
    with app.app_context():
        app.config["AI_GOVERNANCE_ALERTS_ENABLED"] = False
        payload = evaluate_governance_alerts(
            {"total_requests": 5, "no_source_rate": 1.0, "retrieval_hit_rate": 0.1},
            vector_drift={"store_error": "RuntimeError"},
        )

    assert payload["status"] == "disabled"
    assert payload["alerts"] == []
    assert payload["alert_count"] == 0


def test_empty_governance_does_not_report_retrieval_degradation(app):
    """Verify empty systems do not report retrieval degradation without requests."""
    with app.app_context():
        payload = evaluate_governance_alerts({}, vector_drift={})

    assert all(alert["rule"] != "retrieval_degradation" for alert in payload["alerts"])


def test_atlas_governance_rules_do_not_duplicate_generic_vector_alerts(app):
    """Verify Atlas-specific governance covers Atlas risks without generic duplicates."""
    secret_uri = "mongodb+srv://app_user:secret-password@example.mongodb.net"
    with app.app_context():
        payload = evaluate_governance_alerts(
            {
                "total_requests": 8,
                "retrieval_hit_rate": 1.0,
                "atlas_queries": 8,
                "atlas_latency": 1800,
                "atlas_retrieval_hit_rate": 0.5,
            },
            vector_drift={
                "configured_store": "mongodb_atlas",
                "store": "local_knowledge",
                "fallback_active": True,
                "store_error": secret_uri,
                "atlas_fallbacks": 1,
                "atlas_sync_failures": 1,
                "atlas_reindex_required": True,
                "chunk_vector_count_mismatch": True,
                "atlas": {"configured": True, "active": False},
            },
        )

    alert_rules = {alert["rule"] for alert in payload["alerts"]}
    assert "atlas_unavailable" in alert_rules
    assert "atlas_fallbacks" in alert_rules
    assert "atlas_sync_failures" in alert_rules
    assert "atlas_sync_drift" in alert_rules
    assert "atlas_latency_degradation" in alert_rules
    assert "atlas_retrieval_degradation" in alert_rules
    assert "vector_store_failure" not in alert_rules
    assert "vector_store_fallback" not in alert_rules
    assert "secret-password" not in str(payload)
    assert secret_uri not in str(payload)


def test_atlas_governance_thresholds_are_configurable(app):
    """Verify Atlas governance severities use environment-backed config values."""
    with app.app_context():
        app.config.update(
            AI_GOVERNANCE_ATLAS_LATENCY_DEGRADATION_WARNING=2000,
            AI_GOVERNANCE_ATLAS_LATENCY_DEGRADATION_CRITICAL=4000,
            AI_GOVERNANCE_ATLAS_RETRIEVAL_DEGRADATION_WARNING=0.4,
            AI_GOVERNANCE_ATLAS_RETRIEVAL_DEGRADATION_CRITICAL=0.2,
        )
        payload = evaluate_governance_alerts(
            {
                "total_requests": 8,
                "retrieval_hit_rate": 1.0,
                "atlas_queries": 8,
                "atlas_latency": 1800,
                "atlas_retrieval_hit_rate": 0.5,
            },
            vector_drift={
                "configured_store": "mongodb_atlas",
                "store": "mongodb_atlas",
                "atlas": {"configured": True, "active": True},
            },
        )

    alert_rules = {alert["rule"] for alert in payload["alerts"]}
    latency_rule = next(
        rule for rule in payload["rules"] if rule["key"] == "atlas_latency_degradation"
    )
    retrieval_rule = next(
        rule for rule in payload["rules"] if rule["key"] == "atlas_retrieval_degradation"
    )
    assert "atlas_latency_degradation" not in alert_rules
    assert "atlas_retrieval_degradation" not in alert_rules
    assert latency_rule["warning"] == 2000
    assert latency_rule["critical"] == 4000
    assert retrieval_rule["warning"] == 0.4
    assert retrieval_rule["critical"] == 0.2


def test_observability_dashboard_exposes_governance(monkeypatch, app):
    """Verify AI Admin observability exposes governance alerts and counters."""
    expected_governance = {
        "status": "warning",
        "alert_count": 1,
        "critical_count": 0,
        "warning_count": 1,
        "alerts": [
            {
                "rule": "high_no_source_rate",
                "severity": "warning",
                "metric": "no_source_rate",
                "title": "Hohe No-Source-Rate",
                "value": 0.25,
                "threshold": 0.2,
                "recommended_action": "Knowledge-Gaps pruefen.",
            },
        ],
    }
    monkeypatch.setattr(
        "app.services.ai_observability_service.evaluate_governance_alerts",
        lambda *args, **kwargs: expected_governance,
    )

    with app.app_context():
        dashboard = ai_observability_dashboard({"days": "30", "limit": "5"})

    assert dashboard["governance"] == expected_governance
    assert dashboard["alerts"] == expected_governance["alerts"]
    assert dashboard["metrics"]["governance_alert_count"] == 1
    assert dashboard["metrics"]["governance_warning_alert_count"] == 1
    assert dashboard["metrics"]["governance_critical_alert_count"] == 0


def test_observability_dashboard_exposes_atlas_metrics_and_governance(app):
    """Verify AI Admin observability exposes Atlas metrics and alert rules."""
    clear_vector_sync_observability()
    try:
        with app.app_context():
            app.config["RAG_VECTOR_STORE"] = "mongodb_atlas"
            record_atlas_query(25)
            record_atlas_error(RuntimeError("atlas timeout"))

            dashboard = ai_observability_dashboard({"days": "30", "limit": "5"})
    finally:
        clear_vector_sync_observability()

    metrics = dashboard["metrics"]
    alert_rules = {alert["rule"] for alert in dashboard["alerts"]}
    catalog_keys = {item["key"] for item in dashboard["metric_catalog"]}
    assert metrics["atlas_queries"] == 1
    assert metrics["atlas_errors"] == 1
    assert metrics["atlas_latency"] == 25
    assert metrics["atlas_fallbacks"] == 1
    assert metrics["atlas_reindex_required"] is True
    assert "atlas_errors" in alert_rules
    assert "atlas_fallbacks" in alert_rules
    assert "atlas_sync_drift" in alert_rules
    assert "atlas_vector_count" in catalog_keys


def test_governance_documentation_is_available():
    """Verify README and env example document governance alert configuration."""
    root = Path(__file__).resolve().parents[1]
    readme = (root / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    docs = (root / "docs" / "AI_GOVERNANCE_ALERTING.md").read_text(encoding="utf-8")

    assert "AI_GOVERNANCE_ALERTS_ENABLED=true" in readme
    assert "AI_GOVERNANCE_HIGH_NO_SOURCE_RATE_WARNING=0.2" in env_example
    assert "AI Governance And Alerting" in docs
    assert "AI_GOVERNANCE_ATLAS_LATENCY_DEGRADATION_WARNING=500" in readme
    assert "AI_GOVERNANCE_ATLAS_RETRIEVAL_DEGRADATION_WARNING=0.8" in env_example
    assert "atlas_unavailable" in docs
    assert "atlas_latency_degradation" in docs
    assert "MongoDB URIs, credentials and connection strings" in docs
