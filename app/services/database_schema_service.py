"""Database schema diagnostics for runtime readiness checks."""

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - dependency is installed in supported envs
    Vector = None

MIGRATION_COMMAND = "flask --app run:app db upgrade"

REQUIRED_TABLE_COLUMNS = {
    "site": {
        "code",
        "name",
        "timezone",
        "is_active",
    },
    "department": {
        "site_id",
    },
    "employee": {
        "last_shift",
        "current_shift",
        "next_shift",
        "rotation_state_updated_at",
    },
    "task": {
        "planned_minutes",
        "actual_minutes",
        "blocked_reason",
        "reopened_count",
        "error_entry_id",
    },
    "machine": {
        "site_id",
        "criticality",
        "status",
        "last_downtime_at",
    },
    "inventory_material": {
        "min_quantity",
        "criticality",
        "lead_time_days",
        "site_id",
    },
    "error_entry": {
        "status",
        "symptoms",
        "severity",
        "cause_category",
        "impact",
        "downtime_minutes",
        "production_loss_minutes",
        "repeat_count",
        "last_seen_at",
        "closed_at",
    },
    "shift_handover": {
        "area",
        "machine_id",
        "previous_shift",
        "next_shift",
        "production_status",
        "machine_status",
        "safety_notes",
        "material_notes",
        "responsible_employee",
        "problem_category",
        "cause",
        "action_taken",
        "duration_minutes",
        "follow_up_task",
        "involved_employees",
        "confirmed",
    },
    "vacation_request": {
        "cancelled_by",
        "representative_employee_id",
        "cancelled_at",
        "shift_type",
        "reason",
        "impact_level",
        "impact_summary",
    },
    "generated_document": {
        "quality_score",
        "quality_status",
        "quality_checked_at",
        "status",
        "current_version_id",
        "summary",
        "summary_status",
        "approved_by",
        "approved_at",
        "approval_comment",
        "rejected_by",
        "rejected_at",
        "rejection_comment",
    },
    "chat_message": {
        "session_id",
        "response_type",
        "diagnostics_json",
        "source_count",
        "confidence_score",
        "confidence_level",
        "audit_event_id",
    },
    "ai_feedback": {
        "chat_message_id",
        "audit_event_id",
        "response_type",
        "sources_json",
        "source_count",
        "review_status",
    },
    "knowledge_document": {
        "source_type",
        "source_id",
        "title",
        "status",
        "quality_status",
        "last_confirmed_at",
        "confirmation_count",
        "aging_checked_at",
        "is_public",
        "chunk_count",
        "error_message",
    },
    "knowledge_chunk": {
        "document_id",
        "chunk_index",
        "text",
        "token_text",
        "entities_json",
        "embedding",
    },
    "knowledge_gap": {
        "question",
        "question_hash",
        "context_text",
        "machine",
        "department",
        "status",
        "occurrence_count",
        "user_id",
        "audit_event_id",
        "last_seen_at",
    },
    "retrieval_evaluation_run": {
        "query_count",
        "recall_at_k",
        "mrr",
        "ndcg_at_k",
        "keyword_query_count",
        "keyword_hit_rate",
        "permission_leak_count",
        "forbidden_source_hit_count",
        "no_result_count",
        "no_result_rate",
        "expected_no_result_count",
        "expected_no_result_success_count",
        "expected_no_result_success_rate",
        "unexpected_no_result_count",
        "unexpected_no_result_rate",
        "min_source_count_fail_count",
        "min_source_count_pass_rate",
        "query_type_expected_count",
        "query_type_match_count",
        "query_type_accuracy",
        "source_metadata_count",
        "source_id_coverage_rate",
        "source_type_coverage_rate",
        "source_pair_coverage_rate",
        "metadata_pair_coverage_rate",
        "created_at",
    },
    "background_job": {
        "job_type",
        "status",
        "payload_json",
        "result_json",
        "error_message",
        "attempts",
        "max_attempts",
        "locked_at",
        "started_at",
        "finished_at",
        "created_by",
    },
    "ai_audit_event": {
        "confidence_score",
        "confidence_level",
        "retrieval_explainability_json",
        "prompt_template_key",
        "prompt_version_id",
        "prompt_version_number",
    },
    "ai_answer_trace": {
        "answer_id",
        "user_id",
        "chat_message_id",
        "audit_event_id",
        "workflow",
        "provider",
        "model",
        "model_tier",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "confidence_score",
        "confidence_level",
        "source_count",
        "chunk_count",
        "sources_json",
        "chunks_json",
        "created_at",
    },
    "ai_prompt_template": {
        "workflow_key",
        "name",
        "purpose",
        "response_mode",
        "variables_json",
        "is_active",
    },
    "ai_prompt_version": {
        "template_id",
        "version",
        "status",
        "system_prompt",
        "user_prompt_template",
        "json_schema",
        "rules_json",
    },
    "ai_faq_entry": {
        "question",
        "answer",
        "category",
        "keywords",
        "status",
        "source",
    },
    "ai_response_snippet": {
        "key",
        "title",
        "body",
        "category",
        "is_active",
    },
    "assistant_training_entry": {
        "title",
        "question",
        "answer",
        "keywords",
        "category",
        "department",
        "is_active",
        "priority",
        "created_by",
    },
    "operational_event": {
        "event_type",
        "feature",
        "entity_type",
        "entity_id",
        "site_id",
        "department_id",
        "machine_id",
        "task_id",
        "occurred_at",
        "actor_hash",
        "actor_role",
        "source",
        "old_value",
        "new_value",
        "description",
        "metadata_json",
        "created_at",
    },
    "operational_kpi_aggregate": {
        "period_type",
        "period_start",
        "site_id",
        "department_id",
        "feature",
        "metric_key",
        "metric_value",
        "metric_unit",
        "dimensions_json",
    },
}

LOCAL_DEV_SCHEMA_COLUMNS = {
    "department": (sa.Column("site_id", sa.Integer(), nullable=True),),
    "employee": (
        sa.Column("last_shift", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("current_shift", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("next_shift", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("rotation_state_updated_at", sa.DateTime(), nullable=True),
    ),
    "task": (
        sa.Column("planned_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_reason", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("reopened_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_entry_id", sa.Integer(), nullable=True),
    ),
    "machine": (
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("criticality", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="running"),
        sa.Column("last_downtime_at", sa.DateTime(), nullable=True),
    ),
    "inventory_material": (
        sa.Column("min_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criticality", sa.String(length=40), nullable=False, server_default="normal"),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("site_id", sa.Integer(), nullable=True),
    ),
    "error_entry": (
        sa.Column("status", sa.String(length=40), nullable=False, server_default="open"),
        sa.Column("symptoms", sa.Text(), nullable=False, server_default=""),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="medium"),
        sa.Column("cause_category", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("impact", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("downtime_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "production_loss_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("repeat_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    ),
    "shift_handover": (
        sa.Column("area", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("machine_id", sa.Integer(), nullable=True),
        sa.Column("previous_shift", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("next_shift", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("production_status", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("machine_status", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("safety_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("material_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("responsible_employee", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("problem_category", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("cause", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_taken", sa.Text(), nullable=False, server_default=""),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("follow_up_task", sa.Text(), nullable=False, server_default=""),
        sa.Column("involved_employees", sa.Text(), nullable=False, server_default=""),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    ),
    "vacation_request": (
        sa.Column("cancelled_by", sa.Integer(), nullable=True),
        sa.Column("representative_employee_id", sa.Integer(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("shift_type", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("reason", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("impact_level", sa.String(length=40), nullable=False, server_default="ok"),
        sa.Column("impact_summary", sa.Text(), nullable=False, server_default=""),
    ),
    "generated_document": (
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column(
            "quality_status",
            sa.String(length=40),
            nullable=False,
            server_default="not_checked",
        ),
        sa.Column("quality_checked_at", sa.DateTime(), nullable=True),
    ),
    "ai_feedback": (
        sa.Column("chat_message_id", sa.Integer(), nullable=True),
        sa.Column("audit_event_id", sa.Integer(), nullable=True),
        sa.Column("response_type", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("review_status", sa.String(length=40), nullable=False, server_default="open"),
    ),
    "chat_message": (
        sa.Column("session_id", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("confidence_level", sa.String(length=40), nullable=False, server_default=""),
    ),
    "ai_audit_event": (
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("confidence_level", sa.String(length=40), nullable=False, server_default=""),
        sa.Column(
            "retrieval_explainability_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    ),
    "knowledge_document": (
        sa.Column(
            "quality_status",
            sa.String(length=40),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("last_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("confirmation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aging_checked_at", sa.DateTime(), nullable=True),
    ),
    "knowledge_chunk": (
        sa.Column("entities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector() if Vector is not None else sa.JSON(), nullable=True),
    ),
    "retrieval_evaluation_run": (
        sa.Column("keyword_query_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("keyword_hit_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("no_result_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "expected_no_result_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "expected_no_result_success_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "expected_no_result_success_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "unexpected_no_result_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "unexpected_no_result_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "min_source_count_fail_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "min_source_count_pass_rate",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "query_type_expected_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "query_type_match_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "query_type_accuracy",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("source_metadata_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_id_coverage_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_type_coverage_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_pair_coverage_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_pair_coverage_rate", sa.Float(), nullable=False, server_default="0"),
    ),
    "shift_plan": (
        sa.Column("coverage_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "critical_conflict_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
    ),
    "operational_event": (
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    ),
}


def database_schema_status():
    """Return whether the runtime database has all required AI/RAG columns."""
    try:
        inspector = inspect(db.engine)
        table_names = set(inspector.get_table_names())
        missing_tables = []
        missing_columns = {}

        for table_name, expected_columns in REQUIRED_TABLE_COLUMNS.items():
            if table_name not in table_names:
                missing_tables.append(table_name)
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = sorted(expected_columns - existing_columns)
            if missing:
                missing_columns[table_name] = missing

        is_ready = not missing_tables and not missing_columns
        return {
            "ok": is_ready,
            "missing_tables": sorted(missing_tables),
            "missing_columns": missing_columns,
            "migration_command": MIGRATION_COMMAND,
        }
    except SQLAlchemyError as exc:
        return {
            "ok": False,
            "missing_tables": [],
            "missing_columns": {},
            "error": exc.__class__.__name__,
            "migration_command": MIGRATION_COMMAND,
        }


def ensure_local_development_schema():
    """Add safe additive columns for local auto-created development databases."""
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    with db.engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        for table_name, columns in LOCAL_DEV_SCHEMA_COLUMNS.items():
            if table_name not in table_names:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column in columns:
                if column.name in existing_columns:
                    continue
                operations.add_column(table_name, clone_column(column))


def clone_column(column):
    """Return a new SQLAlchemy column for imperative ALTER TABLE operations."""
    server_default = column.server_default.arg if column.server_default is not None else None
    return sa.Column(
        column.name,
        column.type,
        nullable=column.nullable,
        server_default=server_default,
    )


def database_schema_error_payload(schema_status=None):
    """Return a consistent API payload for an outdated database schema."""
    status = schema_status or database_schema_status()
    return {
        "success": False,
        "error": "database_schema_outdated",
        "message": (
            "Database schema is outdated. Run "
            f"`{status['migration_command']}` and restart the app."
        ),
        "data": status,
    }
