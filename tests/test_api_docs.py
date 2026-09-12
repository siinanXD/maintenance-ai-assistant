"""Tests for OpenAPI documentation and demo setup entry points."""

from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import Role, User
from app.permissions import upsert_default_permissions


def test_openapi_json_documents_core_endpoints(client):
    """Verify the OpenAPI JSON exposes the documented production endpoints."""
    response = client.get("/api/swagger.json")

    assert response.status_code == 200
    spec = response.get_json()
    paths = spec["paths"]

    assert spec["openapi"].startswith("3.")
    assert "/health/ready" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/tasks" in paths
    assert "/api/v1/tasks/{task_id}/start" in paths
    assert "/api/v1/tasks/{task_id}/complete" in paths
    assert "/api/v1/tasks/prioritize" in paths
    assert "/api/v1/errors/search" in paths
    assert "/api/v1/errors/similar" in paths
    assert "/api/v1/ai/daily-briefing" in paths
    assert "/api/v1/ai/incident-timeline" in paths
    assert "/api/v1/ai/order-plan" in paths
    assert "/api/v1/ai/error-assistant" in paths
    assert "/api/v1/ai/feedback" in paths
    assert "/api/v1/ai/status" in paths
    assert "/api/v1/ai/chat" in paths
    assert "/api/v1/ai/chat/history" in paths
    assert "/api/v1/sites" in paths
    assert "/api/v1/operations/summary" in paths
    assert "/api/v1/operations/events" in paths
    assert "/api/v1/operations/tasks" in paths
    assert "/api/v1/operations/machines" in paths
    assert "/api/v1/operations/inventory" in paths
    assert "/api/v1/operations/workforce" in paths
    assert "/api/v1/operations/ai-quality" in paths
    assert "/api/v1/admin/sites" in paths
    assert "/api/v1/admin/sites/{site_id}" in paths
    assert "/api/v1/admin/operations/aggregate" in paths

    assert "/api/v1/admin/ai/chats" in paths
    assert "/api/v1/admin/ai/events" in paths
    assert "/api/v1/admin/jobs" in paths
    assert "/api/v1/admin/ai/knowledge/upload" in paths
    assert "/api/v1/admin/ai/knowledge" in paths
    assert "/api/v1/admin/ai/knowledge/status" in paths
    assert "/api/v1/admin/ai/knowledge-network" in paths
    assert "/api/v1/admin/ai/retrieval-telemetry" in paths
    assert "/api/v1/admin/ai/retrieval-debug" in paths
    assert "/api/v1/admin/ai/retrieval-evaluations" in paths
    assert "/api/v1/admin/ai/retrieval-evaluations/run" in paths
    assert "/api/v1/admin/ai/observability" in paths
    assert "/api/v1/admin/ai/knowledge-gaps" in paths
    assert "/api/v1/admin/ai/knowledge/reindex/jobs" in paths
    assert "/api/v1/admin/ai/knowledge/reindex" in paths
    assert "/api/v1/admin/ai/knowledge/{id}/reindex" in paths
    assert "/api/v1/admin/ai/knowledge/{id}/quality-status" in paths
    assert "/api/v1/admin/ai/knowledge/{id}" in paths
    assert "/api/v1/machines/{machine_id}/assistant" in paths
    assert "/api/v1/machines/maintenance-recommendations" in paths
    assert "/api/v1/handover/{handover_id}/summary" in paths
    assert "/api/v1/inventory/forecast" in paths
    assert "/api/v1/admin/permissions/schema" in paths
    assert "/api/v1/admin/users/{user_id}/permissions" in paths
    assert "/api/v1/admin/audit-log" in paths
    assert "/api/v1/admin/backups" in paths
    assert "/api/v1/admin/backups/{backup_id}/download" in paths
    assert "/api/v1/admin/backups/{backup_id}/restore" in paths
    assert "/api/v1/admin/notifications/deliveries" in paths
    assert "/api/v1/admin/notifications/test-email" in paths
    assert "/api/v1/employees/qualifications" in paths
    assert "/api/v1/employees/{employee_id}/qualifications" in paths
    assert "/api/v1/shiftplans/{plan_id}/conflicts" in paths
    assert "/api/v1/shiftplans/validate" in paths
    assert "/api/v1/shiftplans/{plan_id}/export.xlsx" in paths
    assert "/api/v1/notifications" in paths
    assert "/api/v1/notifications/{id}/read" in paths
    assert "/api/v1/notifications/read-all" in paths
    assert "/api/v1/documents/{document_id}/download.pdf" in paths
    assert "/api/v1/documents/{document_id}/summarize" in paths
    assert "/api/v1/documents/{document_id}/submit-review" in paths
    assert "/api/v1/documents/{document_id}/approve" in paths
    assert "/api/v1/documents/{document_id}/reject" in paths
    assert "/api/v1/documents/{document_id}/versions" in paths
    assert "/api/v1/documents/manuals" in paths
    assert "/api/v1/documents/manuals/{manual_id}/download" in paths
    assert "/api/v1/documents/manuals/{manual_id}/analyze" in paths
    assert "/api/v1/documents/manuals/{manual_id}/summarize" in paths
    assert "/api/v1/documents/manuals/{manual_id}" in paths
    assert (
        paths["/api/v1/admin/ai/observability"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/AIObservability"
    )
    assert (
        "source identifiers"
        in paths["/api/v1/admin/ai/retrieval-evaluations"]["get"]["responses"]["200"]["description"]
    )
    assert (
        paths["/api/v1/admin/ai/retrieval-evaluations/run"]["post"]["requestBody"]["content"][
            "application/json"
        ]["example"]["limit"]
        == 20
    )
    assert paths["/api/v1/admin/ai/retrieval-evaluations/run"]["post"]["responses"]["201"][
        "content"
    ]["application/json"]["schema"]["$ref"] == ("#/components/schemas/RetrievalEvaluationRunResult")
    assert (
        paths["/api/v1/admin/ai/retrieval-telemetry"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/RetrievalTelemetry"
    )
    assert (
        paths["/api/v1/ai/error-assistant"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        == "#/components/schemas/ErrorAssistantResult"
    )
    assert (
        paths["/api/v1/ai/status"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/AIStatus"
    )
    assert (
        paths["/api/v1/ai/chat"]["post"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/AIChatResponse"
    )
    assert (
        paths["/health/ready"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
            "$ref"
        ]
        == "#/components/schemas/HealthReadiness"
    )
    assert (
        paths["/api/v1/tasks/prioritize"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]["items"]["$ref"]
        == "#/components/schemas/TaskPrioritySuggestion"
    )
    assert paths["/api/v1/machines/maintenance-recommendations"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]["$ref"] == (
        "#/components/schemas/MaintenanceRecommendationLightResponse"
    )
    assert paths["/api/v1/handover/{handover_id}/summary"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"] == ("#/components/schemas/ShiftHandoverSummary")


def test_legacy_openapi_json_route_redirects_to_canonical_path(client):
    """Verify the deprecated v1 OpenAPI JSON route is only a redirect."""
    response = client.get("/api/v1/swagger.json")

    assert response.status_code == 308
    assert response.headers["Location"] == "/api/swagger.json"


def test_openapi_examples_are_present(client):
    """Verify important endpoints include concise example payloads."""
    spec = client.get("/api/swagger.json").get_json()

    task_example = spec["paths"]["/api/v1/tasks"]["post"]["requestBody"]["content"][
        "application/json"
    ]["example"]
    briefing_example = spec["paths"]["/api/v1/ai/daily-briefing"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["example"]

    assert task_example["title"]
    assert task_example["priority"] == "urgent"
    assert briefing_example["sections"]
    assert spec["components"]["schemas"]["ErrorResponse"]["properties"]["message"]["example"]
    assert spec["components"]["schemas"]["PaginatedAuditLog"]["properties"]["pagination"]
    assert spec["components"]["schemas"]["BackupMetadata"]["properties"]["download_url"]["example"]
    assert spec["components"]["schemas"]["NotificationDelivery"]["properties"]["status"]["example"]
    assert spec["components"]["schemas"]["MailStatus"]["properties"]["dry_run"]["example"] is True
    assert spec["components"]["schemas"]["GeneratedDocument"]["properties"]["pdf_url"]["example"]
    assert spec["components"]["schemas"]["EmployeeMachineQualification"]["properties"]["level"][
        "example"
    ]
    assert spec["components"]["schemas"]["ShiftPlanConflict"]["properties"]["type"]["example"]
    assert spec["components"]["schemas"]["Notification"]["properties"]["title"]["example"]
    assert spec["components"]["schemas"]["DocumentVersion"]["properties"]["version_number"][
        "example"
    ]
    assert spec["components"]["schemas"]["MachineManual"]["properties"]["download_url"]["example"]
    assert spec["components"]["schemas"]["ChatHistoryEntry"]["properties"]["response_type"][
        "example"
    ]
    assert spec["components"]["schemas"]["ChatHistoryEntry"]["properties"]["session_id"]["example"]
    assert spec["components"]["schemas"]["AIAuditEvent"]["properties"]["error_category"]["example"]
    ai_status_schema = spec["components"]["schemas"]["AIStatus"]
    provider_status_schema = spec["components"]["schemas"]["AIProviderStatus"]
    assert ai_status_schema["properties"]["provider_status"]["$ref"] == (
        "#/components/schemas/AIProviderStatus"
    )
    provider_catalog = ai_status_schema["properties"]["provider_catalog"]["example"]
    assert any(
        item["provider"] == "gemini" and item["status"] == "planned" for item in provider_catalog
    )
    embedding_provider_catalog = ai_status_schema["properties"]["embedding_provider_catalog"][
        "example"
    ]
    assert any(
        item["provider"] == "hashing" and item["status"] == "supported"
        for item in embedding_provider_catalog
    )
    readiness_schema = ai_status_schema["properties"]["readiness"]
    assert (
        readiness_schema["properties"]["actions"]["items"]["properties"]["configuration_action"][
            "example"
        ]
        == "select_supported_provider"
    )
    assert readiness_schema["properties"]["next_action"]["nullable"] is True
    assert (
        "AI_PROVIDER"
        in readiness_schema["properties"]["next_action"]["properties"]["recommended_action"][
            "example"
        ]
    )
    assert provider_status_schema["properties"]["effective_provider"]["example"] == "mock"
    assert provider_status_schema["properties"]["fallback_active"]["example"] is True
    assert provider_status_schema["properties"]["production_default"]["example"] is False
    assert (
        provider_status_schema["properties"]["configuration_action"]["example"] == "set_ai_base_url"
    )
    assert "AI_BASE_URL" in provider_status_schema["properties"]["recommended_action"]["example"]
    assert provider_status_schema["properties"]["api_key_configured"]["example"] is False
    assert provider_status_schema["properties"]["model_configured"]["example"] is True
    assert provider_status_schema["properties"]["dimensions"]["example"] == 384
    health_schema = spec["components"]["schemas"]["HealthReadiness"]
    health_ai_schema = health_schema["properties"]["components"]["properties"]["ai"]
    assert health_ai_schema["properties"]["effective_provider"]["example"] == "mock"
    assert (
        health_ai_schema["properties"]["configuration_action"]["example"]
        == "select_supported_provider"
    )
    assert "AI_PROVIDER" in health_ai_schema["properties"]["recommended_action"]["example"]
    assert health_ai_schema["properties"]["embedding_provider"]["$ref"] == (
        "#/components/schemas/AIProviderStatus"
    )
    rca_schema = spec["components"]["schemas"]["ErrorAssistantResult"]["properties"][
        "root_cause_analysis"
    ]
    rca_step_schema = rca_schema["properties"]["next_steps"]["items"]
    rca_confidence_schema = rca_schema["properties"]["confidence"]
    assert rca_step_schema["properties"]["source"]["example"] == "similar_case_solution"
    assert rca_step_schema["properties"]["source_id"]["example"] == 7
    assert rca_confidence_schema["properties"]["uncertainty"]["example"] == "medium"
    evidence_schema = rca_schema["properties"]["evidence"]
    assert evidence_schema["properties"]["uses_only_visible_sources"]["example"] is True
    assert (
        evidence_schema["properties"]["similar_case_sources"]["items"]["properties"]["error_code"][
            "example"
        ]
        == "P42-HYD"
    )
    assert (
        evidence_schema["properties"]["rag_sources"]["items"]["properties"]["source_type"][
            "example"
        ]
        == "machine_manual"
    )
    rag_source_schema = evidence_schema["properties"]["rag_sources"]["items"]
    assert rag_source_schema["properties"]["chunk_id"]["example"] == 42
    assert rag_source_schema["properties"]["machine_id"]["example"] == 7
    assert rag_source_schema["properties"]["created_at"]["format"] == "date-time"
    task_priority_schema = spec["components"]["schemas"]["TaskPrioritySuggestion"]
    task_confidence_schema = task_priority_schema["properties"]["confidence"]
    task_evidence_schema = task_priority_schema["properties"]["evidence_counts"]
    task_reference_schema = task_priority_schema["properties"]["evidence_references"]["items"]
    task_steps_schema = task_priority_schema["properties"]["next_steps"]["items"]
    assert task_confidence_schema["properties"]["score"]["example"] == 78
    assert task_confidence_schema["properties"]["uncertainty"]["example"] == "low"
    assert task_steps_schema["properties"]["type"]["example"] == "review_related_errors"
    assert task_steps_schema["properties"]["urgency"]["example"] == "high"
    assert task_evidence_schema["properties"]["uses_only_visible_sources"]["example"] is True
    assert task_evidence_schema["properties"]["related_errors"]["example"] == 2
    assert task_reference_schema["properties"]["type"]["example"] == "error"
    assert task_reference_schema["properties"]["role_visibility"]["example"] == (
        "department:Instandhaltung"
    )
    assert task_reference_schema["properties"]["created_at"]["format"] == "date-time"
    maintenance_schema = spec["components"]["schemas"]["MaintenanceRecommendationLight"]
    maintenance_evidence = maintenance_schema["properties"]["evidence_summary"]
    maintenance_steps = maintenance_schema["properties"]["next_steps"]["items"]
    assert maintenance_schema["properties"]["confidence_uncertainty"]["example"] == "medium"
    assert maintenance_steps["properties"]["type"]["example"] == "error_history_review"
    assert maintenance_steps["properties"]["urgency"]["example"] == "high"
    assert maintenance_evidence["properties"]["uses_only_visible_sources"]["example"] is True
    assert maintenance_evidence["properties"]["predictive_claim"]["example"] is False
    assert maintenance_evidence["properties"]["recurring_issue_window_days"]["example"] == 30
    assert "rag_source" in maintenance_evidence["properties"]["source_types"]["example"]
    maintenance_rag_source = maintenance_evidence["properties"]["rag_sources"]["items"]
    assert maintenance_rag_source["properties"]["source_type"]["example"] == ("maintenance_plan")
    assert maintenance_rag_source["properties"]["chunk_id"]["example"] == 42
    assert maintenance_rag_source["properties"]["created_at"]["format"] == "date-time"
    maintenance_response = spec["components"]["schemas"]["MaintenanceRecommendationLightResponse"]
    assert (
        maintenance_response["properties"]["recommendation_type"]["example"]
        == "maintenance_recommendation_light"
    )
    handover_schema = spec["components"]["schemas"]["ShiftHandoverSummary"]
    handover_confidence = handover_schema["properties"]["confidence"]
    handover_evidence = handover_schema["properties"]["evidence_summary"]
    handover_action_schema = handover_schema["properties"]["next_actions"]["items"]
    assert handover_confidence["properties"]["uncertainty"]["example"] == "low"
    assert handover_action_schema["properties"]["source_id"]["example"] == 18
    assert handover_action_schema["properties"]["priority"]["example"] == "high"
    assert handover_evidence["properties"]["workflow"]["example"] == ("shift_handover_summary")
    assert handover_evidence["properties"]["provider"]["example"] == "local_rules"
    assert handover_evidence["properties"]["uses_only_visible_sources"]["example"] is True
    assert handover_evidence["properties"]["llm_call"]["example"] is False
    assert "task" in handover_evidence["properties"]["source_types"]["example"]
    handover_source_reference = handover_evidence["properties"]["source_references"]["items"]
    assert handover_source_reference["properties"]["type"]["example"] == "task"
    assert handover_source_reference["properties"]["machine"]["example"] == "Handover Presse"
    assert (
        handover_source_reference["properties"]["role_visibility"]["example"]
        == "department:Produktion"
    )
    assert handover_source_reference["properties"]["created_at"]["format"] == "date-time"
    run_schema = spec["components"]["schemas"]["RetrievalEvaluationRunResult"]
    assert run_schema["properties"]["keyword_miss_count"]["example"] == 2
    assert run_schema["properties"]["expected_no_result_success_rate"]["example"] == 1.0
    assert run_schema["properties"]["unexpected_no_result_rate"]["example"] == 0.0
    assert run_schema["properties"]["min_source_count_fail_count"]["example"] == 1
    assert run_schema["properties"]["min_source_count_pass_rate"]["example"] == 0.92
    assert run_schema["properties"]["quality_gate"]["example"]["status"] == "warning"
    assert run_schema["properties"]["privacy"]["example"]["stores_expected_keywords"] is False
    telemetry_schema = spec["components"]["schemas"]["RetrievalTelemetry"]
    unused_chunks_schema = telemetry_schema["properties"]["unused_chunks"]
    chunk_metrics_schema = unused_chunks_schema["properties"]["chunk_size_metrics"]
    assert chunk_metrics_schema["properties"]["average_block_count"]["example"] == 2
    assert (
        chunk_metrics_schema["properties"]["block_kind_distribution"]["items"]["properties"]["key"][
            "example"
        ]
        == "list"
    )
    unused_sample_schema = unused_chunks_schema["properties"]["sample"]["items"]
    assert unused_sample_schema["properties"]["chunk_block_count"]["example"] == 2
    assert unused_sample_schema["properties"]["chunk_block_kinds"]["example"] == [
        "list",
        "paragraph",
    ]
    observability_schema = spec["components"]["schemas"]["AIObservability"]
    answer_quality_schema = spec["components"]["schemas"]["AnswerQuality"]
    assert answer_quality_schema["properties"]["evidence_visible"]["example"] is True
    assert answer_quality_schema["properties"]["status_reason"]["example"] == "sources_available"
    assert (
        answer_quality_schema["properties"]["primary_warning_type"]["example"] == "source_conflict"
    )
    chat_schema = spec["components"]["schemas"]["AIChatResponse"]
    assert chat_schema["properties"]["answer_quality"]["$ref"] == (
        "#/components/schemas/AnswerQuality"
    )
    assert chat_schema["properties"]["evidence_visible"]["example"] is False
    assert observability_schema["properties"]["metric_catalog"]["items"]["required"] == [
        "key",
        "label",
        "category",
        "unit",
    ]
    provider_readiness_schema = observability_schema["properties"]["provider_readiness"]
    assert provider_readiness_schema["properties"]["provider_status"]["$ref"] == (
        "#/components/schemas/AIProviderStatus"
    )
    assert (
        provider_readiness_schema["properties"]["readiness"]["properties"]["next_action"][
            "nullable"
        ]
        is True
    )
    observability_metrics = observability_schema["properties"]["metrics"]["properties"]
    assert "retrieval_hit_rate" in observability_metrics
    assert observability_metrics["provider_ready"]["example"] is False
    assert observability_metrics["provider_readiness_status"]["example"] == "degraded"
    assert observability_metrics["provider_degraded_component_count"]["example"] == 1
    assert (
        observability_metrics["provider_next_action_type"]["example"] == "select_supported_provider"
    )
    assert observability_metrics["atlas_queries"]["example"] == 24
    assert observability_metrics["atlas_errors"]["example"] == 1
    assert observability_metrics["atlas_latency"]["example"] == 35.5
    assert observability_metrics["atlas_fallbacks"]["example"] == 1
    assert observability_metrics["atlas_sync_failures"]["example"] == 1
    assert observability_metrics["atlas_vector_count"]["example"] == 1280
    assert observability_metrics["atlas_reindex_required"]["example"] is True
    assert observability_metrics["governance_alert_count"]["example"] == 2
    assert observability_metrics["governance_status"]["example"] == "warning"
    governance_schema = observability_schema["properties"]["governance"]
    assert governance_schema["properties"]["alerts"]["items"]["properties"]["rule"]["example"] == (
        "high_no_source_rate"
    )
    assert "alerts" in observability_schema["properties"]
    assert observability_metrics["source_conflict_count"]["example"] == 1
    assert observability_metrics["source_conflict_rate"]["example"] == 0.04
    assert (
        observability_metrics["answer_quality_distribution"]["example"]["conflicting_sources"] == 1
    )
    assert "answer_quality_distribution_rows" in observability_metrics
    assert (
        observability_metrics["answer_quality_reason_distribution"]["example"][
            "empty_retrieval_hallucination_guard"
        ]
        == 2
    )
    assert "answer_quality_reason_distribution_rows" in observability_metrics
    answer_quality_action_schema = observability_metrics["answer_quality_actions"]["items"]
    assert answer_quality_action_schema["properties"]["type"]["example"] == (
        "review_no_answer_guarded_questions"
    )
    assert observability_metrics["answer_quality_action_count"]["example"] == 2
    assert (
        observability_metrics["answer_quality_action_summary"]["properties"]["next_action_type"][
            "example"
        ]
        == "review_no_answer_guarded_questions"
    )
    assert (
        observability_metrics["primary_warning_distribution"]["example"]["hallucination_risk"] == 2
    )
    assert "primary_warning_distribution_rows" in observability_metrics
    assert observability_metrics["uncertainty_distribution"]["example"]["high"] == 2
    assert "uncertainty_distribution_rows" in observability_metrics
    assert observability_metrics["high_uncertainty_rate"]["example"] == 0.08
    assert observability_metrics["uncertain_answer_count"]["example"] == 5
    assert observability_metrics["source_freshness"]["example"]["stale_source_rate"] == 0.1667
    assert observability_metrics["stale_source_count"]["example"] == 2
    assert observability_metrics["retrieval_action_count"]["example"] == 3
    assert observability_metrics["evaluation_critical_action_count"]["example"] == 1
    assert observability_metrics["evaluation_quality_gate_status"]["example"] == "fail"
    assert observability_metrics["evaluation_quality_gate_passed"]["example"] is False
    assert observability_metrics["evaluation_quality_gate_issue_count"]["example"] == 3
    assert observability_metrics["evaluation_blocking_count"]["example"] == 1
    assert observability_metrics["evaluation_warning_count"]["example"] == 2
    assert observability_metrics["source_metadata_gap_count"]["example"] == 2
    assert observability_metrics["source_metadata_gap_fields"]["example"] == [
        "source_pair",
        "metadata_pair",
    ]
    assert observability_metrics["source_metadata_min_coverage_rate"]["example"] == 0.5
    retrieval_monitoring_schema = observability_schema["properties"]["retrieval_monitoring"]
    source_freshness_schema = retrieval_monitoring_schema["properties"]["source_freshness"]
    top_hit_schema = retrieval_monitoring_schema["properties"]["top_hits"]["items"]
    assert top_hit_schema["properties"]["title"]["example"] == ("Presse 42 Hydraulikhandbuch")
    assert "source_created_at" in top_hit_schema["properties"]
    assert top_hit_schema["properties"]["source_age_days"]["example"] == 365
    stale_source_schema = retrieval_monitoring_schema["properties"]["stale_sources"]["items"]
    assert stale_source_schema["properties"]["stale_threshold_days"]["example"] == 180
    assert stale_source_schema["properties"]["title"]["example"] == ("Presse 42 Hydraulikhandbuch")
    retrieval_quality_action_schema = retrieval_monitoring_schema["properties"][
        "retrieval_quality_actions"
    ]["items"]
    assert retrieval_quality_action_schema["properties"]["type"]["example"] == (
        "review_low_quality_retrieval_hits"
    )
    assert retrieval_quality_action_schema["properties"]["target"]["example"] == ("poor_hits")
    undated_source_schema = retrieval_monitoring_schema["properties"]["undated_sources"]["items"]
    assert undated_source_schema["properties"]["title"]["example"] == (
        "Presse 42 Wartungsnotiz ohne Datum"
    )
    assert undated_source_schema["properties"]["source_age_days"]["nullable"] is True
    metadata_action_schema = retrieval_monitoring_schema["properties"]["metadata_quality_actions"][
        "items"
    ]
    assert metadata_action_schema["properties"]["type"]["example"] == ("complete_source_dates")
    assert metadata_action_schema["properties"]["target_type"]["example"] == (
        "retrieval_source_metadata"
    )
    action_summary_schema = retrieval_monitoring_schema["properties"]["action_summary"]
    assert action_summary_schema["properties"]["total"]["example"] == 3
    assert action_summary_schema["properties"]["critical_priority_count"]["example"] == 0
    assert action_summary_schema["properties"]["high_priority_count"]["example"] == 1
    assert action_summary_schema["properties"]["next_action_priority"]["example"] == "high"
    assert source_freshness_schema["properties"]["stale_threshold_days"]["example"] == 180
    assert source_freshness_schema["properties"]["stale_source_rate"]["example"] == 0.1667
    quality_metrics_schema = observability_schema["properties"]["quality_metrics"]
    assert quality_metrics_schema["properties"]["min_source_count_fail_count"]["example"] == 1
    assert quality_metrics_schema["properties"]["min_source_count_pass_rate"]["example"] == 0.92
    assert quality_metrics_schema["properties"]["expected_no_result_success_rate"]["example"] == 1.0
    assert quality_metrics_schema["properties"]["unexpected_no_result_rate"]["example"] == 0.0
    assert quality_metrics_schema["properties"]["query_type_accuracy"]["example"] == 0.8333
    assert (
        quality_metrics_schema["properties"]["evaluation_quality_gate"]["example"]["warnings"][0][
            "metric"
        ]
        == "recall_at_k"
    )
    evaluation_action_schema = quality_metrics_schema["properties"]["evaluation_actions"]["items"]
    assert evaluation_action_schema["properties"]["type"]["example"] == ("fix_permission_leaks")
    assert evaluation_action_schema["properties"]["priority"]["example"] == "critical"
    assert evaluation_action_schema["properties"]["warning_metrics"]["example"] == [
        "block_metadata_coverage_rate"
    ]
    assert evaluation_action_schema["properties"]["focus_areas"]["example"] == [
        "chunk_structure_metadata"
    ]
    assert "chunk_block_count" in " ".join(
        evaluation_action_schema["properties"]["next_steps"]["example"]
    )
    assert (
        "block_metadata_coverage_rate"
        in evaluation_action_schema["properties"]["success_criteria"]["example"][0]
    )
    evaluation_action_summary_schema = quality_metrics_schema["properties"][
        "evaluation_action_summary"
    ]
    assert evaluation_action_summary_schema["properties"]["total"]["example"] == 4
    assert evaluation_action_summary_schema["properties"]["critical_priority_count"]["example"] == 1
    assert (
        evaluation_action_summary_schema["properties"]["next_action_type"]["example"]
        == "fix_permission_leaks"
    )
    assert quality_metrics_schema["properties"]["evaluation_warning_count"]["example"] == 2
    assert quality_metrics_schema["properties"]["evaluation_blocking_count"]["example"] == 1
    assert (
        "permission_leak_count"
        in quality_metrics_schema["properties"]["evaluation_blocking_metrics"]["example"]
    )
    blocking_row_schema = quality_metrics_schema["properties"]["evaluation_blocking_rows"]["items"]
    assert (
        blocking_row_schema["properties"]["reason"]["example"]
        == "retrieved_forbidden_or_invisible_source"
    )
    assert (
        "keyword_hit_rate"
        in quality_metrics_schema["properties"]["evaluation_warning_metrics"]["example"]
    )
    warning_row_schema = quality_metrics_schema["properties"]["evaluation_warning_rows"]["items"]
    assert warning_row_schema["properties"]["reason"]["example"] == "expected_keywords_missing"
    recommended_action_schema = observability_schema["properties"]["recommended_actions"]["items"]
    assert recommended_action_schema["properties"]["action_source"]["example"] == ("evaluation")
    assert recommended_action_schema["properties"]["action_source"]["type"] == "string"
    assert recommended_action_schema["properties"]["type"]["example"] == ("fix_permission_leaks")
    assert recommended_action_schema["properties"]["rank"]["example"] == 1
    assert recommended_action_schema["properties"]["rank_label"]["example"] == "P1"
    next_best_action_schema = observability_schema["properties"]["next_best_action"]
    assert next_best_action_schema["nullable"] is True
    assert next_best_action_schema["properties"]["type"]["example"] == ("fix_permission_leaks")
    recommended_action_summary_schema = observability_schema["properties"][
        "recommended_action_summary"
    ]
    assert recommended_action_summary_schema["properties"]["total"]["example"] == 5
    assert (
        recommended_action_summary_schema["properties"]["critical_priority_count"]["example"] == 1
    )
    assert (
        recommended_action_summary_schema["properties"]["next_action_source"]["example"]
        == "evaluation"
    )
    assert (
        recommended_action_summary_schema["properties"]["answer_quality_action_count"]["example"]
        == 2
    )
    assert (
        recommended_action_summary_schema["properties"]["answer_quality_next_action_type"][
            "example"
        ]
        == "review_no_answer_guarded_questions"
    )
    assert recommended_action_summary_schema["properties"]["source_distribution"]["type"] == "array"
    ai_log_schema = observability_schema["properties"]["ai_logs"]["items"]
    assert ai_log_schema["properties"]["knowledge_gap_id"]["example"] == 321
    assert ai_log_schema["properties"]["knowledge_gap_created"]["example"] is True
    assert (
        ai_log_schema["properties"]["confidence"]["properties"]["uncertainty"]["example"] == "high"
    )
    assert (
        ai_log_schema["properties"]["sources"]["items"]["properties"]["title"]["example"]
        == "Presse 42 Hydraulikhandbuch"
    )
    knowledge_gap_schema = observability_schema["properties"]["metrics"]["properties"][
        "knowledge_gaps"
    ]
    assert "error_gap_count" in knowledge_gap_schema["properties"]
    assert "uncovered_error_gap_count" in knowledge_gap_schema["properties"]
    assert "uncovered_machine_gap_count" in knowledge_gap_schema["properties"]
    assert "uncovered_error_gaps" in knowledge_gap_schema["properties"]
    assert "uncovered_machine_gaps" in knowledge_gap_schema["properties"]
    assert "uncertain_question_gaps" in knowledge_gap_schema["properties"]
    assert (
        knowledge_gap_schema["properties"]["uncertain_question_gaps"]["items"]["properties"][
            "answer_uncertainty"
        ]["example"]
        == "high"
    )
    assert "uncertain_question_actions" in knowledge_gap_schema["properties"]
    assert (
        knowledge_gap_schema["properties"]["uncertain_question_actions"]["example"][0]["type"]
        == "review_uncertain_answer_gap"
    )
    error_gap_item = knowledge_gap_schema["properties"]["error_gaps"]["items"]
    assert error_gap_item["properties"]["error_code"]["example"] == "P42-HYD"
    assert error_gap_item["properties"]["coverage"]["example"] == "missing"
    uncovered_error_item = knowledge_gap_schema["properties"]["uncovered_error_gaps"]["items"]
    assert uncovered_error_item["properties"]["priority"]["example"] == "high"
    uncovered_machine_item = knowledge_gap_schema["properties"]["uncovered_machine_gaps"]["items"]
    assert uncovered_machine_item["properties"]["criticality"]["example"] == "critical"
    assert spec["components"]["schemas"]["KnowledgeDocument"]["properties"]["status"]["example"]
    assert spec["components"]["schemas"]["KnowledgeDocument"]["properties"]["quality_status"][
        "example"
    ]
    assert spec["components"]["schemas"]["KnowledgeGap"]["properties"]["status"]["example"]
    retrieval_eval_schema = spec["components"]["schemas"]["RetrievalEvaluationRunResult"]
    assert retrieval_eval_schema["properties"]["query_type_accuracy"]["example"] == 0.8333
    chunk_coverage_schema = retrieval_eval_schema["properties"]["chunk_metadata_coverage"]
    assert chunk_coverage_schema["properties"]["block_metadata_coverage_rate"]["example"] == 1.0
    assert chunk_coverage_schema["properties"]["block_kind_distribution"]["example"] == {
        "paragraph": 6,
        "list": 2,
    }
    assert spec["components"]["schemas"]["MissingInformation"]["properties"]["questions"]
    assert spec["components"]["schemas"]["Site"]["properties"]["code"]["example"]
    assert spec["components"]["schemas"]["OperationalEvent"]["properties"]["actor_hash"]["example"]
    assert spec["components"]["schemas"]["OperationsSummary"]["properties"]["tasks"]


def test_swagger_ui_route_loads(client):
    """Verify the Swagger UI or local fallback page is reachable."""
    response = client.get("/swagger/", follow_redirects=True)

    assert response.status_code == 200
    assert b"Swagger" in response.data


def test_api_docs_page_links_to_swagger(client):
    """Verify the developer docs page points to Swagger and OpenAPI JSON."""
    response = client.get("/api-docs")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "/swagger/" in body
    assert "/api/swagger.json" in body


def test_api_docs_are_disabled_by_default_in_production(tmp_path):
    """Verify production deployments do not expose API docs by default."""
    application = _api_docs_test_app(tmp_path, flask_env="production")

    with application.app_context():
        client = application.test_client()
        protected_paths = (
            "/swagger/",
            "/api/swagger.json",
            "/api/v1/swagger.json",
            "/apispec_1.json",
        )
        for path in protected_paths:
            response = client.get(path)
            assert response.status_code == 404, path


def test_enabled_production_api_docs_require_master_admin(tmp_path):
    """Verify explicitly enabled production API docs are master-admin only."""
    application = _api_docs_test_app(
        tmp_path,
        flask_env="production",
        enable_api_docs=True,
        require_master_admin=True,
    )

    with application.app_context():
        master_headers = _create_user_headers(application, "docs_master", Role.MASTER_ADMIN)
        user_headers = _create_user_headers(application, "docs_user", Role.PRODUKTION)
        client = application.test_client()

        protected_paths = (
            "/swagger/",
            "/api/swagger.json",
            "/api/v1/swagger.json",
            "/apispec_1.json",
        )
        for path in protected_paths:
            assert client.get(path).status_code == 401, path
            assert client.get(path, headers=user_headers).status_code == 403, path

        master_responses = {
            path: client.get(path, headers=master_headers) for path in protected_paths
        }

    spec_response = master_responses["/api/swagger.json"]
    legacy_response = master_responses["/api/v1/swagger.json"]
    swagger_response = master_responses["/swagger/"]
    flasgger_spec_response = master_responses["/apispec_1.json"]
    assert spec_response.status_code == 200
    assert spec_response.get_json()["openapi"].startswith("3.")
    assert legacy_response.status_code == 308
    assert legacy_response.headers["Location"] == "/api/swagger.json"
    assert swagger_response.status_code == 200
    assert b"Swagger" in swagger_response.data
    assert flasgger_spec_response.status_code == 200


def test_development_api_docs_preserve_current_public_behavior(tmp_path):
    """Verify development deployments keep API docs public unless configured otherwise."""
    application = _api_docs_test_app(tmp_path, flask_env="development")

    with application.app_context():
        client = application.test_client()
        spec_response = client.get("/api/swagger.json")
        swagger_response = client.get("/swagger/")

    assert spec_response.status_code == 200
    assert spec_response.get_json()["openapi"].startswith("3.")
    assert swagger_response.status_code == 200
    assert b"Swagger" in swagger_response.data


def _api_docs_test_app(
    tmp_path,
    flask_env,
    enable_api_docs=None,
    require_master_admin=None,
):
    """Create a minimal app configured for API documentation security tests."""

    class ApiDocsSecurityConfig:
        """Provide deterministic app settings for API documentation tests."""

        TESTING = True
        FLASK_ENV = flask_env
        SECRET_KEY = "test-secret-key-with-enough-length"
        JWT_SECRET_KEY = "test-jwt-secret-key-with-enough-length"
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        AUTO_CREATE_DATABASE = True
        AI_PROVIDER = "mock"
        EMBEDDING_PROVIDER = "hashing"
        # The legacy suites exercise the rule-based router directly; agent tests
        # opt in with AI_CHAT_MODE="agent". Checkpoints stay in-process.
        AI_CHAT_MODE = "legacy"
        AI_AGENT_CHECKPOINTER = "memory"
        OPENAI_API_KEY = ""
        OPENAI_MODEL = "test-model"
        MAIL_DRY_RUN = True
        MAIL_ENABLED = False
        MAIL_FROM = "noreply@example.test"
        UPLOAD_FOLDER = str(Path(tmp_path) / "uploads")
        DOCUMENTS_FOLDER = str(Path(tmp_path) / "documents")
        MANUALS_FOLDER = str(Path(tmp_path) / "manuals")
        KNOWLEDGE_FOLDER = str(Path(tmp_path) / "knowledge")
        BACKUP_FOLDER = str(Path(tmp_path) / "backups")
        LOG_DIR = str(Path(tmp_path) / "logs")

    if enable_api_docs is not None:
        ApiDocsSecurityConfig.ENABLE_API_DOCS = enable_api_docs
    if require_master_admin is not None:
        ApiDocsSecurityConfig.API_DOCS_REQUIRE_MASTER_ADMIN = require_master_admin
    return create_app(ApiDocsSecurityConfig)


def _create_user_headers(application, username, role):
    """Create a user in the provided app and return JWT authorization headers."""
    user = User(
        username=username,
        email=f"{username}@example.test",
        role=role,
        is_active=True,
    )
    user.set_password("password")
    db.session.add(user)
    db.session.flush()
    upsert_default_permissions(user)
    db.session.commit()

    response = application.test_client().post(
        "/api/v1/auth/login",
        json={"login": username, "password": "password"},
    )
    assert response.status_code == 200, response.get_json()
    token = response.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
