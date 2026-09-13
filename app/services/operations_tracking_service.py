"""Pseudonymized operations event tracking and KPI aggregation."""

import hashlib
import hmac
import json
import logging
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta

from flask import current_app, has_app_context

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import (
    AIAuditEvent,
    AIFeedback,
    Department,
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    Machine,
    OperationalEvent,
    OperationalKpiAggregate,
    ShiftPlan,
    ShiftPlanChangeLog,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def actor_hash_for_user(user):
    """Return a stable pseudonymous HMAC hash for a user."""
    if not user:
        return ""
    secret = str(
        current_app.config.get("OPERATIONS_HASH_SECRET")
        or current_app.config.get("SECRET_KEY")
        or "dev-secret-change-me"
    ).encode("utf-8")
    message = str(user.id).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def metadata_text(metadata):
    """Return compact JSON text for event metadata."""
    safe_metadata = metadata if isinstance(metadata, dict) else {}
    return json.dumps(safe_metadata, ensure_ascii=True, sort_keys=True, default=str)


def event_value_text(value):
    """Return compact JSON text for optional old/new event values."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def event_site_id(department=None, machine=None, site_id=None):
    """Resolve the best site id for an event."""
    if site_id:
        return site_id
    if department is not None and getattr(department, "site_id", None):
        return department.site_id
    if machine is not None and getattr(machine, "site_id", None):
        return machine.site_id
    return None


def record_event(
    event_type,
    feature,
    entity_type="",
    entity_id=None,
    user=None,
    department=None,
    department_id=None,
    machine=None,
    machine_id=None,
    task=None,
    task_id=None,
    site_id=None,
    source="app",
    metadata=None,
    old_value=None,
    new_value=None,
    description="",
    occurred_at=None,
    commit=False,
):
    """Add one operations event to the current database session."""
    try:
        department_id = department_id or getattr(department, "id", None)
        machine_id = machine_id or getattr(machine, "id", None)
        task_id = task_id or getattr(task, "id", None)
        site_id = event_site_id(department=department, machine=machine, site_id=site_id)
        if not site_id and department_id:
            department_obj = department or db.session.get(Department, department_id)
            site_id = event_site_id(department=department_obj)
        if not site_id and machine_id:
            machine_obj = machine or db.session.get(Machine, machine_id)
            site_id = event_site_id(machine=machine_obj)

        event = OperationalEvent(
            event_type=str(event_type)[:80],
            feature=str(feature)[:80],
            entity_type=str(entity_type or "")[:80],
            entity_id=entity_id,
            site_id=site_id,
            department_id=department_id,
            machine_id=machine_id,
            task_id=task_id,
            occurred_at=occurred_at or utc_now(),
            actor_hash=actor_hash_for_user(user),
            actor_role=getattr(getattr(user, "role", None), "value", "") if user else "",
            source=str(source or "app")[:80],
            old_value=event_value_text(old_value),
            new_value=event_value_text(new_value),
            description=str(description or "")[:1000],
            metadata_json=metadata_text(metadata),
        )
        db.session.add(event)
        if commit:
            db.session.commit()
        return event
    except Exception:
        if commit:
            db.session.rollback()
        _log_event_failure(event_type, entity_type, entity_id)
        return None


def _log_event_failure(event_type, entity_type, entity_id):
    """Log event failures without interrupting the primary workflow."""
    message = "operations_event_record_failed event_type=%s entity_type=%s entity_id=%s"
    if has_app_context():
        current_app.logger.exception(message, event_type, entity_type, entity_id)
        return
    logger.exception(message, event_type, entity_type, entity_id)


def parse_date_range(args, default_days=30):
    """Return inclusive datetime range from request arguments."""
    today = date.today()
    start = _parse_date_arg(args.get("from") or args.get("date_from"))
    end = _parse_date_arg(args.get("to") or args.get("date_to"))
    if not end:
        end = today
    if not start:
        start = end - timedelta(days=max(1, int(default_days or 30)) - 1)
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


def filtered_events_query(args, user):
    """Return operations events filtered by request arguments and permissions."""
    start_at, end_at = parse_date_range(args)
    query = OperationalEvent.query.filter(
        OperationalEvent.occurred_at >= start_at,
        OperationalEvent.occurred_at <= end_at,
    )
    query = _scope_query_to_user(query, user)
    query = _apply_common_event_filters(query, args)
    event_type = str(args.get("event_type") or "").strip()
    if event_type:
        query = query.filter(OperationalEvent.event_type == event_type)
    feature = str(args.get("feature") or "").strip()
    if feature:
        query = query.filter(OperationalEvent.feature == feature)
    return query.order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())


def operations_summary(args, user):
    """Return compact cross-feature operations KPIs."""
    start_at, end_at = parse_date_range(args)
    filters = {
        "from": start_at.date().isoformat(),
        "to": end_at.date().isoformat(),
        "site_id": _optional_int(args.get("site_id")),
        "department_id": _optional_int(args.get("department_id")),
        "machine_id": _optional_int(args.get("machine_id")),
    }
    return {
        "filters": filters,
        "tasks": task_metrics(args, user, start_at, end_at),
        "machines": machine_metrics(args, user, start_at, end_at),
        "inventory": inventory_metrics(args, user),
        "workforce": workforce_metrics(args, user, start_at, end_at),
        "documents": document_metrics(args, user, start_at, end_at),
        "ai_quality": ai_quality_metrics(args, user, start_at, end_at),
        "events": event_metrics(args, user, start_at, end_at),
        "generated_at": utc_now().isoformat(),
    }


def task_metrics(args, user, start_at=None, end_at=None):
    """Return task lifecycle KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    query = _visible_task_query(user)
    query = _apply_task_filters(query, args)
    all_visible = query.all()
    completed_window = [
        task
        for task in all_visible
        if task.completed_at and _between(task.completed_at, start_at, end_at)
    ]
    response_values = [
        _minutes_between(task.created_at, task.started_at)
        for task in all_visible
        if task.started_at and task.created_at and _between(task.started_at, start_at, end_at)
    ]
    cycle_values = [
        _minutes_between(task.created_at, task.completed_at)
        for task in completed_window
        if task.created_at
    ]
    today = date.today()
    return {
        "total": len(all_visible),
        "open": sum(1 for task in all_visible if task.status == TaskStatus.OPEN),
        "in_progress": sum(1 for task in all_visible if task.status == TaskStatus.IN_PROGRESS),
        "completed": len(completed_window),
        "overdue": sum(
            1
            for task in all_visible
            if task.due_date < today and task.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
        ),
        "blocked": sum(1 for task in all_visible if task.blocked_reason),
        "reopened": sum(task.reopened_count or 0 for task in all_visible),
        "planned_minutes": sum(task.planned_minutes or 0 for task in all_visible),
        "actual_minutes": sum(task.actual_minutes or 0 for task in completed_window),
        "avg_response_minutes": _average(response_values),
        "avg_cycle_minutes": _average(cycle_values),
    }


def machine_metrics(args, user, start_at=None, end_at=None):
    """Return machine and fault KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    machine_query = Machine.query
    machine_query = _apply_machine_filters(machine_query, args)
    error_query = _visible_error_query(user)
    error_query = _apply_error_filters(error_query, args)
    error_query = error_query.filter(
        ErrorEntry.created_at >= start_at,
        ErrorEntry.created_at <= end_at,
    )
    errors = error_query.all()
    downtime_values = [entry.downtime_minutes or 0 for entry in errors if entry.downtime_minutes]
    return {
        "machines_total": machine_query.count(),
        "machines_down": machine_query.filter(Machine.status == "down").count(),
        "faults": len(errors),
        "repeat_faults": sum(entry.repeat_count or 0 for entry in errors),
        "downtime_minutes": sum(downtime_values),
        "production_loss_minutes": sum(entry.production_loss_minutes or 0 for entry in errors),
        "mttr_minutes": _average(downtime_values),
        "top_cause_categories": dict(
            Counter(entry.cause_category or "unknown" for entry in errors)
        ),
    }


def inventory_metrics(args, user):
    """Return inventory risk KPIs."""
    query = InventoryMaterial.query
    query = _apply_inventory_filters(query, args)
    items = query.all()
    low_stock = [item for item in items if item.min_quantity and item.quantity < item.min_quantity]
    critical_low = [
        item for item in low_stock if item.criticality in {"critical", "high", "urgent"}
    ]
    return {
        "material_count": len(items),
        "total_quantity": sum(item.quantity or 0 for item in items),
        "total_value": round(sum(item.total_value for item in items), 2),
        "low_stock_count": len(low_stock),
        "critical_shortage_count": len(critical_low),
        "top_shortages": [
            {
                "id": item.id,
                "name": item.name,
                "quantity": item.quantity,
                "min_quantity": item.min_quantity,
                "criticality": item.criticality,
            }
            for item in sorted(low_stock, key=lambda item: item.quantity - item.min_quantity)[:8]
        ],
    }


def workforce_metrics(args, user, start_at=None, end_at=None):
    """Return shift planning and workforce coverage KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    query = ShiftPlan.query.filter(
        ShiftPlan.created_at >= start_at,
        ShiftPlan.created_at <= end_at,
    )
    department = _department_name_from_args(args)
    if department:
        query = query.filter(ShiftPlan.department == department)
    plans = query.all()
    return {
        "plans": len(plans),
        "published": sum(1 for plan in plans if plan.status == "published"),
        "avg_coverage_percent": _average([plan.coverage_percent for plan in plans]),
        "conflicts": sum(plan.conflict_count or 0 for plan in plans),
        "critical_conflicts": sum(plan.critical_conflict_count or 0 for plan in plans),
        "change_count": sum(plan.change_count or 0 for plan in plans)
        or _shift_change_count(args, start_at, end_at),
    }


def document_metrics(args, user, start_at=None, end_at=None):
    """Return document quality and approval KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    query = GeneratedDocument.query.filter(
        GeneratedDocument.created_at >= start_at,
        GeneratedDocument.created_at <= end_at,
    )
    if not getattr(user, "is_admin", False) and getattr(user, "department", None):
        query = query.filter(GeneratedDocument.department == user.department.name)
    department = _department_name_from_args(args)
    if department:
        query = query.filter(GeneratedDocument.department == department)
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(GeneratedDocument.machine_id == machine_id)
    documents = query.all()
    approval_hours = [
        _minutes_between(document.created_at, document.approved_at) / 60
        for document in documents
        if document.approved_at and document.created_at
    ]
    return {
        "documents": len(documents),
        "in_review": sum(1 for document in documents if document.status == "in_review"),
        "approved": sum(1 for document in documents if document.status == "approved"),
        "rejected": sum(1 for document in documents if document.status == "rejected"),
        "quality_checked": sum(
            1 for document in documents if document.quality_status != "not_checked"
        ),
        "avg_quality_score": _average(
            [document.quality_score for document in documents if document.quality_score]
        ),
        "avg_approval_hours": _average(approval_hours),
    }


def ai_quality_metrics(args, user, start_at=None, end_at=None):
    """Return AI quality, cost and feedback KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    query = AIAuditEvent.query.filter(
        AIAuditEvent.created_at >= start_at,
        AIAuditEvent.created_at <= end_at,
    )
    events = query.all()
    feedback = AIFeedback.query.filter(
        AIFeedback.created_at >= start_at,
        AIFeedback.created_at <= end_at,
    ).all()
    return {
        "events": len(events),
        "fallback_count": sum(1 for event in events if event.fallback_used),
        "error_count": sum(1 for event in events if event.error_category),
        "source_count": sum(event.source_count or 0 for event in events),
        "avg_latency_ms": _average([event.latency_ms for event in events if event.latency_ms]),
        "total_tokens": sum(event.total_tokens or 0 for event in events),
        "estimated_cost_usd": round(sum(event.estimated_cost_usd or 0 for event in events), 6),
        "feedback_count": len(feedback),
        "positive_feedback": sum(1 for item in feedback if item.rating in {"positive", "helpful"}),
        "negative_feedback": sum(
            1 for item in feedback if item.rating in {"negative", "not_helpful"}
        ),
        "partial_feedback": sum(1 for item in feedback if item.rating == "partially_helpful"),
    }


def event_metrics(args, user, start_at=None, end_at=None):
    """Return event volume KPIs."""
    start_at, end_at = _ensure_range(args, start_at, end_at)
    query = OperationalEvent.query.filter(
        OperationalEvent.occurred_at >= start_at,
        OperationalEvent.occurred_at <= end_at,
    )
    query = _scope_query_to_user(query, user)
    query = _apply_common_event_filters(query, args)
    events = query.all()
    return {
        "total": len(events),
        "by_feature": dict(Counter(event.feature for event in events)),
        "by_type": dict(Counter(event.event_type for event in events)),
    }


def aggregate_operations(period_type="day", args=None, user=None):
    """Rebuild persisted KPI aggregates for operations events."""
    args = args or {}
    if period_type not in {"day", "month"}:
        raise ValueError("period_type must be day or month")
    start_at, end_at = parse_date_range(args, default_days=30)
    query = OperationalEvent.query.filter(
        OperationalEvent.occurred_at >= start_at,
        OperationalEvent.occurred_at <= end_at,
    )
    query = _scope_query_to_user(query, user)
    rows = query.all()
    buckets = defaultdict(int)
    for event in rows:
        period_start = _period_start(event.occurred_at.date(), period_type)
        key = (
            period_start,
            event.site_id,
            event.department_id,
            event.feature,
            "event_count",
            json.dumps({"event_type": event.event_type}, sort_keys=True),
        )
        buckets[key] += 1

    saved = []
    for (
        period_start,
        site_id,
        department_id,
        feature,
        metric_key,
        dimensions,
    ), value in buckets.items():
        aggregate = OperationalKpiAggregate.query.filter_by(
            period_type=period_type,
            period_start=period_start,
            site_id=site_id,
            department_id=department_id,
            feature=feature,
            metric_key=metric_key,
            dimensions_json=dimensions,
        ).first()
        if not aggregate:
            aggregate = OperationalKpiAggregate(
                period_type=period_type,
                period_start=period_start,
                site_id=site_id,
                department_id=department_id,
                feature=feature,
                metric_key=metric_key,
                metric_unit="count",
                dimensions_json=dimensions,
            )
            db.session.add(aggregate)
        aggregate.metric_value = float(value)
        saved.append(aggregate)
    db.session.commit()
    return {"aggregates": len(saved), "events": len(rows), "period_type": period_type}


def _ensure_range(args, start_at, end_at):
    """Return a valid start/end range."""
    if start_at and end_at:
        return start_at, end_at
    return parse_date_range(args)


def _scope_query_to_user(query, user):
    """Scope an event query to the current user's department when needed."""
    if user and getattr(user, "role", None) and user.role.value != "master_admin":
        return query.filter(OperationalEvent.department_id == user.department_id)
    return query


def _visible_task_query(user):
    """Return tasks visible to a user."""
    query = Task.query
    if user and getattr(user, "role", None) and user.role.value != "master_admin":
        query = query.filter(Task.department_id == user.department_id)
    return query


def _visible_error_query(user):
    """Return error entries visible to a user."""
    query = ErrorEntry.query
    if user and getattr(user, "role", None) and user.role.value != "master_admin":
        query = query.filter(ErrorEntry.department_id == user.department_id)
    return query


def _apply_common_event_filters(query, args):
    """Apply common site, department, machine and task filters to events."""
    site_id = _optional_int(args.get("site_id"))
    if site_id:
        query = query.filter(OperationalEvent.site_id == site_id)
    department_id = _optional_int(args.get("department_id"))
    if department_id:
        query = query.filter(OperationalEvent.department_id == department_id)
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(OperationalEvent.machine_id == machine_id)
    task_id = _optional_int(args.get("task_id"))
    if task_id:
        query = query.filter(OperationalEvent.task_id == task_id)
    return query


def _apply_task_filters(query, args):
    """Apply common filters to task queries."""
    department_id = _optional_int(args.get("department_id"))
    if department_id:
        query = query.filter(Task.department_id == department_id)
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(Task.id.in_(_task_ids_for_machine(machine_id)))
    site_id = _optional_int(args.get("site_id"))
    if site_id:
        query = query.join(Department, Task.department_id == Department.id).filter(
            Department.site_id == site_id
        )
    return query


def _apply_machine_filters(query, args):
    """Apply site and machine filters to machine queries."""
    site_id = _optional_int(args.get("site_id"))
    if site_id:
        query = query.filter(Machine.site_id == site_id)
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(Machine.id == machine_id)
    return query


def _apply_inventory_filters(query, args):
    """Apply site and machine filters to inventory queries."""
    site_id = _optional_int(args.get("site_id"))
    if site_id:
        query = query.filter(InventoryMaterial.site_id == site_id)
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(InventoryMaterial.machine_id == machine_id)
    return query


def _apply_error_filters(query, args):
    """Apply common filters to error queries."""
    department_id = _optional_int(args.get("department_id"))
    if department_id:
        query = query.filter(ErrorEntry.department_id == department_id)
    site_id = _optional_int(args.get("site_id"))
    if site_id:
        query = query.join(Department, ErrorEntry.department_id == Department.id).filter(
            Department.site_id == site_id
        )
    machine_id = _optional_int(args.get("machine_id"))
    if machine_id:
        query = query.filter(ErrorEntry.machine_id == machine_id)
    return query


def _task_ids_for_machine(machine_id):
    """Return task ids associated through generated document machine metadata."""
    rows = db.session.query(GeneratedDocument.task_id).filter(
        GeneratedDocument.machine_id == machine_id
    )
    return [row[0] for row in rows.all()]


def _shift_change_count(args, start_at, end_at):
    """Return shift-plan changelog count for the selected time window."""
    query = ShiftPlanChangeLog.query.filter(
        ShiftPlanChangeLog.changed_at >= start_at,
        ShiftPlanChangeLog.changed_at <= end_at,
    )
    return query.count()


def _department_name_from_args(args):
    """Return a department name from filters when available."""
    department_id = _optional_int(args.get("department_id"))
    if not department_id:
        return str(args.get("department") or "").strip()
    department = db.session.get(Department, department_id)
    return department.name if department else ""


def _parse_date_arg(value):
    """Parse an ISO date argument or return None."""
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _optional_int(value):
    """Return an integer for non-empty input or None."""
    if value in (None, ""):
        return None
    return int(value)


def _comparable_datetime(value):
    """Return a timezone-free UTC datetime for Python-side comparisons."""
    if value.tzinfo:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _between(value, start_at, end_at):
    """Return whether a datetime falls in the inclusive range."""
    comparable = _comparable_datetime(value)
    return _comparable_datetime(start_at) <= comparable <= _comparable_datetime(end_at)


def _minutes_between(start_at, end_at):
    """Return elapsed minutes between two datetimes."""
    return (_comparable_datetime(end_at) - _comparable_datetime(start_at)).total_seconds() / 60


def _average(values):
    """Return a rounded average for numeric values."""
    clean_values = [float(value) for value in values if value is not None]
    if not clean_values:
        return 0
    return round(sum(clean_values) / len(clean_values), 2)


def _period_start(value, period_type):
    """Return normalized aggregate period start."""
    if period_type == "month":
        return value.replace(day=1)
    return value
