"""Service helpers for recurring machine maintenance plans."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.machines import PLAN_KIND_INSPECTION, PLAN_KIND_MAINTENANCE, RECORD_RESULTS
from app.extensions import db
from app.handover.services import visible_handovers_query
from app.models import (
    ErrorEntry,
    GeneratedDocument,
    Machine,
    MaintenancePlan,
    MaintenanceRecord,
    Priority,
    Role,
    ShiftHandover,
    Task,
    TaskStatus,
)
from app.security import has_dashboard_permission
from app.services.error_service import visible_errors_query
from app.services.payload_parsing_service import parse_bool as parse_optional_bool
from app.services.recurring_issue_service import analyze_recurring_issues
from app.services.retrieval_service import knowledge_context_for_chat
from app.services.task_service import (
    get_department_for_payload,
    parse_date,
    parse_enum,
    visible_tasks_query,
)


def visible_maintenance_plans_query(user):
    """Return maintenance plans visible to the current user."""
    query = MaintenancePlan.query
    if user.role != Role.MASTER_ADMIN:
        query = query.filter(MaintenancePlan.department_id == user.department_id)
    return query


def parse_interval_days(value):
    """Parse and validate a recurrence interval in days."""
    try:
        interval_days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("interval_days must be a number") from exc
    if interval_days < 1:
        raise ValueError("interval_days must be at least 1")
    return interval_days


RETEST_AFTER_FAILURE_DAYS = 7
PLAN_KINDS = (PLAN_KIND_MAINTENANCE, PLAN_KIND_INSPECTION)


def parse_plan_kind(value, default=PLAN_KIND_MAINTENANCE):
    """Return a valid plan kind."""
    kind = str(value or default).strip()
    if kind not in PLAN_KINDS:
        raise ValueError("kind must be 'maintenance' or 'inspection'")
    return kind


def resolve_machine(machine_id):
    """Resolve an optional machine id from a plan payload."""
    if machine_id in (None, ""):
        return None
    try:
        parsed_id = int(machine_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("machine_id must be a valid machine id") from exc
    machine = db.session.get(Machine, parsed_id)
    if not machine:
        raise ValueError("machine_id does not reference an existing machine")
    return machine


def create_maintenance_plan(data, user):
    """Create a recurring maintenance plan."""
    try:
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        department = get_department_for_payload(data, user)
        plan = MaintenancePlan(
            title=title,
            kind=parse_plan_kind(data.get("kind")),
            legal_basis=str(data.get("legal_basis") or "").strip()[:120],
            description=str(data.get("description") or "").strip(),
            interval_days=parse_interval_days(data.get("interval_days")),
            next_due_date=parse_date(data.get("next_due_date")),
            priority=parse_enum(Priority, data.get("priority"), Priority.NORMAL),
            is_active=parse_optional_bool(data.get("is_active"), default=True),
            machine=resolve_machine(data.get("machine_id")),
            department=department,
            created_by=user.id,
        )
    except PermissionError as exc:
        return None, {"error": str(exc)}, 403
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    db.session.add(plan)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"error": "Database error while creating maintenance plan"}, 500
    return plan, None, 201


def update_maintenance_plan(plan, data, user):
    """Apply a partial update to a recurring maintenance plan."""
    try:
        if "title" in data:
            title = str(data["title"] or "").strip()
            if not title:
                raise ValueError("title must not be empty")
            plan.title = title
        if "description" in data:
            plan.description = str(data["description"] or "").strip()
        if "kind" in data:
            plan.kind = parse_plan_kind(data["kind"], default=plan.kind)
        if "legal_basis" in data:
            plan.legal_basis = str(data["legal_basis"] or "").strip()[:120]
        if "interval_days" in data:
            plan.interval_days = parse_interval_days(data["interval_days"])
        if "next_due_date" in data:
            plan.next_due_date = parse_date(data["next_due_date"])
        if "priority" in data:
            plan.priority = parse_enum(Priority, data["priority"], plan.priority)
        if "is_active" in data:
            plan.is_active = parse_optional_bool(data["is_active"], default=plan.is_active)
        if "machine_id" in data:
            plan.machine = resolve_machine(data.get("machine_id"))
        if "department_id" in data or "department" in data:
            plan.department = get_department_for_payload(data, user)
    except PermissionError as exc:
        return None, {"error": str(exc)}, 403
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"error": "Database error while updating maintenance plan"}, 500
    return plan, None, 200


def delete_maintenance_plan(plan):
    """Delete a recurring maintenance plan."""
    try:
        db.session.delete(plan)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return {"error": "Database error while deleting maintenance plan"}, 500
    return None, 204


def record_maintenance(plan, data, user):
    """Document one execution of a plan and schedule the next one.

    ``passed`` and ``defects`` move the due date one interval past the execution
    date. ``failed`` schedules a re-test after seven days. For ``defects`` and
    ``failed`` a follow-up task is created unless ``create_follow_up`` is false;
    that needs task write permission.
    """
    try:
        performed_on = parse_date(data.get("performed_on"))
        if performed_on > date.today():
            raise ValueError("performed_on must not be in the future")
        performed_by = str(data.get("performed_by") or "").strip()
        if not performed_by:
            raise ValueError("performed_by is required")
        result = str(data.get("result") or "").strip()
        if result not in RECORD_RESULTS:
            raise ValueError("result must be 'passed', 'defects' or 'failed'")
    except ValueError as exc:
        return None, {"error": str(exc)}, 400

    notes = str(data.get("notes") or "").strip()
    wants_follow_up = result != "passed" and parse_optional_bool(
        data.get("create_follow_up"), default=True
    )
    if wants_follow_up and not has_dashboard_permission(user, "tasks", "write"):
        return None, {"error": "tasks write permission is required for a follow-up task"}, 403

    follow_up_task = _follow_up_task(plan, result, notes, user) if wants_follow_up else None
    record = MaintenanceRecord(
        plan=plan,
        performed_on=performed_on,
        performed_by=performed_by[:120],
        result=result,
        notes=notes,
        follow_up_task=follow_up_task,
        recorded_by=user.id,
    )
    retest = result == "failed"
    plan.next_due_date = performed_on + timedelta(
        days=RETEST_AFTER_FAILURE_DAYS if retest else plan.interval_days
    )
    db.session.add(record)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"error": "Database error while recording maintenance"}, 500
    return record, None, 201


def _follow_up_task(plan, result, notes, user):
    """Build the task that fixes defects found during an execution."""
    machine = f" ({plan.machine.name})" if plan.machine else ""
    return Task(
        title=f"Mängel beheben: {plan.title}{machine}"[:160],
        description="\n".join(
            part
            for part in (
                f"{'Prüfung' if plan.kind == PLAN_KIND_INSPECTION else 'Wartung'} "
                f"{'nicht bestanden' if result == 'failed' else 'mit Mängeln'}.",
                f"Grundlage: {plan.legal_basis}" if plan.legal_basis else "",
                notes,
            )
            if part
        ),
        priority=Priority.URGENT if result == "failed" else Priority.SOON,
        status=TaskStatus.OPEN,
        due_date=date.today() + timedelta(days=0 if result == "failed" else 7),
        department=plan.department,
        created_by=user.id,
    )


def get_visible_maintenance_plan(plan_id, user):
    """Return a visible maintenance plan by id, or None."""
    return visible_maintenance_plans_query(user).filter(MaintenancePlan.id == plan_id).first()


def advance_due_date(current_due_date, interval_days, generated_until):
    """Return the next due date after generated_until."""
    next_due_date = current_due_date + timedelta(days=interval_days)
    while next_due_date <= generated_until:
        next_due_date += timedelta(days=interval_days)
    return next_due_date


def task_payload_for_plan(plan):
    """Build the task fields for one maintenance plan run."""
    machine_label = f"{plan.machine.name}: " if plan.machine else ""
    title = f"Wartung: {machine_label}{plan.title}"[:160]
    description_parts = [
        plan.description,
        f"Wiederkehrender Wartungsplan #{plan.id}",
        f"Intervall: {plan.interval_days} Tage",
    ]
    if plan.machine:
        description_parts.append(f"Maschine: {plan.machine.name}")
    return {
        "title": title,
        "description": "\n".join(part for part in description_parts if part),
        "priority": plan.priority,
        "status": TaskStatus.OPEN,
        "due_date": plan.next_due_date,
        "department": plan.department,
        "created_by": plan.created_by,
    }


def generate_due_maintenance_tasks(user, generated_until=None):
    """Generate one open task for each due active maintenance plan."""
    if not has_dashboard_permission(user, "tasks", "write"):
        return None, {"error": "tasks write permission is required"}, 403
    target_date = generated_until or date.today()
    due_plans = (
        visible_maintenance_plans_query(user)
        .filter(
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.next_due_date <= target_date,
        )
        .order_by(MaintenancePlan.next_due_date.asc(), MaintenancePlan.id.asc())
        .all()
    )

    generated = []
    now = datetime.now(UTC)
    for plan in due_plans:
        payload = task_payload_for_plan(plan)
        task = Task(**payload)
        db.session.add(task)
        db.session.flush()
        plan.last_generated_task = task
        plan.last_generated_at = now
        plan.next_due_date = advance_due_date(
            plan.next_due_date,
            plan.interval_days,
            target_date,
        )
        generated.append({"plan": plan.to_dict(), "task": task.to_dict()})

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return None, {"error": "Database error while generating maintenance tasks"}, 500

    return {"generated_count": len(generated), "items": generated}, None, 200


def recommend_preventive_maintenance(user, limit=5):
    """Return read-only preventive maintenance recommendations from visible history."""
    if not has_dashboard_permission(user, "machines", "view"):
        return None, {"error": "machines view permission is required"}, 403
    try:
        limit_value = min(max(1, int(limit)), 20)
    except (TypeError, ValueError):
        return None, {"error": "limit must be an integer between 1 and 20"}, 400

    machine_signals = _machine_signal_map(user)
    recurring_trends = analyze_recurring_issues(user, days=30, min_occurrences=2, limit=20)
    recommendations = [
        _preventive_recommendation(
            machine,
            signals,
            user,
            _matching_recurring_trend(machine, recurring_trends.get("items", [])),
        )
        for machine, signals in machine_signals.items()
        if _signal_score(signals) >= 2
        or _matching_recurring_trend(machine, recurring_trends.get("items", []))
    ]
    recommendations.sort(
        key=lambda item: (item["score"], item["source_counts"]["errors"]),
        reverse=True,
    )
    return (
        {
            "items": recommendations[:limit_value],
            "count": min(len(recommendations), limit_value),
            "total_candidates": len(recommendations),
            "recommendation_type": "maintenance_recommendation_light",
            "disclaimer": (
                "Heuristische Empfehlung aus sichtbaren Fehlern, Wartungen, Tasks "
                "und RAG-Quellen; keine Predictive-Maintenance-Prognose."
            ),
            "recurring_issues": recurring_trends,
        },
        None,
        200,
    )


def _machine_signal_map(user):
    """Return visible recurring maintenance signals grouped by machine."""
    signals = {}
    machines = Machine.query.order_by(Machine.name.asc()).all()
    for machine in machines:
        signals[machine] = _empty_machine_signals()

    if has_dashboard_permission(user, "tasks", "view"):
        tasks = visible_tasks_query(user).order_by(Task.updated_at.desc()).limit(200).all()
        for task in tasks:
            machine = _matching_machine(task.title, task.description, machines=machines)
            if machine:
                signals.setdefault(machine, _empty_machine_signals())["tasks"].append(task)

    if has_dashboard_permission(user, "errors", "view"):
        errors = visible_errors_query(user).order_by(ErrorEntry.created_at.desc()).limit(200).all()
        for entry in errors:
            machine = _matching_machine(entry.machine, entry.title, machines=machines)
            if machine:
                signals.setdefault(machine, _empty_machine_signals())["errors"].append(entry)

    for plan in visible_maintenance_plans_query(user).order_by(
        MaintenancePlan.next_due_date.asc(),
        MaintenancePlan.id.desc(),
    ):
        machine = plan.machine or _matching_machine(plan.title, plan.description, machines=machines)
        if machine:
            signals.setdefault(machine, _empty_machine_signals())["maintenance_plans"].append(
                plan,
            )

    if has_dashboard_permission(user, "documents", "view"):
        documents_query = GeneratedDocument.query.order_by(
            GeneratedDocument.created_at.desc(),
            GeneratedDocument.id.desc(),
        )
        if user.role != Role.MASTER_ADMIN and user.department:
            documents_query = documents_query.filter(
                GeneratedDocument.department == user.department.name,
            )
        for document in documents_query.limit(200).all():
            machine = _document_machine(document, machines)
            if machine:
                signals.setdefault(machine, _empty_machine_signals())["maintenance_reports"].append(
                    document
                )

    if has_dashboard_permission(user, "shiftplans", "view"):
        handovers = (
            visible_handovers_query(user)
            .order_by(ShiftHandover.shift_date.desc(), ShiftHandover.id.desc())
            .limit(200)
            .all()
        )
        for handover in handovers:
            machine = handover.machine or _matching_machine(
                handover.area,
                handover.content,
                handover.open_tasks,
                handover.machine_notes,
                handover.next_notes,
                machines=machines,
            )
            if machine:
                signals.setdefault(machine, _empty_machine_signals())["shift_handovers"].append(
                    handover
                )
    return signals


def _empty_machine_signals():
    """Return an empty signal bucket for one machine."""
    return {
        "tasks": [],
        "errors": [],
        "maintenance_reports": [],
        "maintenance_plans": [],
        "shift_handovers": [],
    }


def _matching_machine(*values, machines):
    """Return the first machine referenced by text values."""
    text = " ".join(str(value or "").lower() for value in values)
    return next((machine for machine in machines if machine.name.lower() in text), None)


def _document_machine(document, machines):
    """Return the machine referenced by a generated maintenance document."""
    if document.machine_id:
        match = next((machine for machine in machines if machine.id == document.machine_id), None)
        if match:
            return match
    return _matching_machine(
        document.machine,
        document.title,
        document.relative_path,
        machines=machines,
    )


def _signal_score(signals):
    """Return a simple recurrence score for task and error signals."""
    return (
        len(signals["tasks"])
        + (len(signals["errors"]) * 2)
        + len(signals["maintenance_reports"])
        + len(signals["maintenance_plans"])
        + len(signals["shift_handovers"])
    )


def _preventive_recommendation(machine, signals, user, recurring_trend=None):
    """Return one preventive maintenance recommendation for a machine."""
    recurring_score = (recurring_trend or {}).get("occurrence_count", 0) * 15
    score = min(100, (_signal_score(signals) * 20) + recurring_score)
    query = f"{machine.name} Wartung Stoerung Fehler wiederkehrend"
    _context, rag_sources = knowledge_context_for_chat(query, user, limit=3)
    confidence = _preventive_confidence(signals, recurring_trend, rag_sources)
    confidence_level = _preventive_confidence_level(confidence)
    return {
        "machine": machine.to_dict(),
        "score": score,
        "confidence": confidence,
        "confidence_level": confidence_level,
        "confidence_uncertainty": _preventive_confidence_uncertainty(confidence_level),
        "confidence_reason": _preventive_confidence_reason(
            signals,
            recurring_trend,
            rag_sources,
        ),
        "recommendation_type": "maintenance_recommendation_light",
        "risk_level": _preventive_risk_level(score),
        "reason": _preventive_reason(signals, recurring_trend),
        "recommended_action": _preventive_action(machine, signals, recurring_trend),
        "next_steps": _preventive_next_steps(machine, signals, recurring_trend, rag_sources),
        "source_counts": {
            "tasks": len(signals["tasks"]),
            "errors": len(signals["errors"]),
            "maintenance_reports": len(signals["maintenance_reports"]),
            "maintenance_plans": len(signals["maintenance_plans"]),
            "shift_handovers": len(signals["shift_handovers"]),
            "rag_sources": len(rag_sources),
            "recurring_issues": 1 if recurring_trend else 0,
        },
        "evidence_summary": _preventive_evidence_summary(
            signals,
            rag_sources,
            recurring_trend,
        ),
        "evidence": _preventive_evidence(signals),
        "sources": rag_sources,
        "recurring_issue": recurring_trend,
        "assumptions": [
            "Empfehlung basiert nur auf sichtbaren historischen Daten.",
            "Keine Vorhersage von Ausfallzeit oder Restlebensdauer.",
        ],
        "limitations": [
            "Keine Prognose von Ausfallzeit, Restlebensdauer oder Ausfallwahrscheinlichkeit.",
            "Empfehlung ist ein leichter Wartungshinweis, keine automatische Freigabe.",
        ],
    }


def _preventive_risk_level(score):
    """Return a risk level for a preventive recommendation score."""
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _preventive_reason(signals, recurring_trend=None):
    """Return a concise German reason for recurring signals."""
    if recurring_trend:
        return (
            f"{recurring_trend['occurrence_count']} Vorkommen im Fehlertrend plus "
            f"{len(signals['tasks'])} Tasks, {len(signals['errors'])} Fehler, "
            f"{len(signals['maintenance_reports'])} Wartungsberichte und "
            f"{len(signals['maintenance_plans'])} Wartungsplaene sowie "
            f"{len(signals['shift_handovers'])} Schichtuebergaben."
        )
    return (
        f"{len(signals['tasks'])} sichtbare Tasks und "
        f"{len(signals['errors'])} Fehler, "
        f"{len(signals['maintenance_reports'])} Wartungsberichte und "
        f"{len(signals['maintenance_plans'])} Wartungsplaene sowie "
        f"{len(signals['shift_handovers'])} Schichtuebergaben deuten auf "
        "wiederkehrende Themen hin."
    )


def _preventive_action(machine, signals, recurring_trend=None):
    """Return a practical next action for preventive maintenance."""
    if recurring_trend:
        return recurring_trend["recommendation"]
    if signals["errors"]:
        return (
            f"Wartungsplan fuer {machine.name} pruefen: Fehlerursachen buendeln, "
            "Inspektionsintervall festlegen und Ersatzteile abgleichen."
        )
    return (
        f"Tasks zu {machine.name} auswerten und bei wiederkehrenden Symptomen "
        "einen praeventiven Wartungsplan anlegen."
    )


def _preventive_next_steps(machine, signals, recurring_trend=None, rag_sources=None):
    """Return structured next steps derived from visible maintenance evidence."""
    steps = []
    if recurring_trend:
        steps.append(
            _preventive_step(
                "recurring_issue_review",
                "Wiederkehrenden Fehlertrend pruefen",
                recurring_trend.get("recommendation")
                or "Fehlertrend fachlich pruefen und Massnahme festlegen.",
                "recurring_issue",
                "high",
            )
        )
    if signals["errors"]:
        steps.append(
            _preventive_step(
                "error_history_review",
                "Fehlerhistorie buendeln",
                (
                    f"{len(signals['errors'])} sichtbare Fehler an {machine.name} "
                    "auf gemeinsame Ursachen und Ersatzteilbedarf pruefen."
                ),
                "error",
                "high",
            )
        )
    if signals["maintenance_plans"]:
        steps.append(
            _preventive_step(
                "maintenance_plan_review",
                "Wartungsplan abgleichen",
                (
                    "Intervall, naechsten Faelligkeitstermin und vorhandene "
                    "Wartungsaufgaben gegen die aktuelle Historie pruefen."
                ),
                "maintenance_plan",
                "medium",
            )
        )
    if signals["tasks"]:
        steps.append(
            _preventive_step(
                "task_follow_up",
                "Offene Aufgaben priorisieren",
                (
                    f"{len(signals['tasks'])} sichtbare Tasks zu {machine.name} "
                    "auf Wiederholungen und offene Pruefpunkte auswerten."
                ),
                "task",
                "medium",
            )
        )
    if signals["shift_handovers"]:
        steps.append(
            _preventive_step(
                "handover_review",
                "Schichtuebergaben pruefen",
                "Uebergaben auf wiederkehrende Hinweise und naechste Massnahmen lesen.",
                "shift_handover",
                "medium",
            )
        )
    if rag_sources:
        steps.append(
            _preventive_step(
                "knowledge_check",
                "Dokumentierte Quellen pruefen",
                "Passende RAG-Quellen gegen den geplanten Wartungsschritt halten.",
                "rag_source",
                "low",
            )
        )
    if not steps:
        steps.append(
            _preventive_step(
                "monitor_history",
                "Historie weiter beobachten",
                "Noch keine belastbare Massnahme ableiten; neue Signale dokumentieren.",
                "maintenance_history",
                "low",
            )
        )
    return steps[:4]


def _preventive_step(step_type, title, detail, source_type, urgency):
    """Return one bounded next-step payload for maintenance recommendations."""
    return {
        "type": str(step_type or "")[:80],
        "title": str(title or "")[:160],
        "detail": str(detail or "")[:500],
        "source_type": str(source_type or "")[:80],
        "urgency": str(urgency or "medium")[:40],
    }


def _preventive_confidence(signals, recurring_trend, rag_sources):
    """Return a bounded confidence score for a light recommendation."""
    evidence_count = (
        len(signals["tasks"])
        + len(signals["errors"])
        + len(signals["maintenance_reports"])
        + len(signals["maintenance_plans"])
        + len(signals["shift_handovers"])
    )
    score = 30 + min(35, evidence_count * 8) + min(20, len(rag_sources) * 5)
    if recurring_trend:
        score += 15
    return max(0, min(95, score))


def _preventive_confidence_level(confidence):
    """Return a coarse confidence level for a light maintenance recommendation."""
    if confidence >= 75:
        return "high"
    if confidence >= 50:
        return "medium"
    return "low"


def _preventive_confidence_uncertainty(confidence_level):
    """Return uncertainty aligned with the light recommendation confidence level."""
    if confidence_level == "high":
        return "low"
    if confidence_level == "medium":
        return "medium"
    return "high"


def _preventive_confidence_reason(signals, recurring_trend, rag_sources):
    """Return a concise reason explaining recommendation confidence."""
    evidence_count = (
        len(signals["tasks"])
        + len(signals["errors"])
        + len(signals["maintenance_reports"])
        + len(signals["maintenance_plans"])
        + len(signals["shift_handovers"])
    )
    if recurring_trend:
        return "Wiederkehrender Fehlertrend plus sichtbare Wartungshistorie vorhanden."
    if evidence_count >= 3 and rag_sources:
        return "Mehrere sichtbare Wartungssignale und passende RAG-Quellen vorhanden."
    if evidence_count >= 2:
        return "Mehrere sichtbare Wartungssignale vorhanden, Quellenlage begrenzt."
    return "Schwache Quellenlage; Empfehlung nur als leichter Wartungshinweis."


def _preventive_evidence(signals):
    """Return compact evidence entries for a recommendation."""
    task_items = [
        {
            "type": "task",
            "id": task.id,
            "title": task.title,
            "status": task.status.value,
            "date": task.updated_at.isoformat(),
        }
        for task in signals["tasks"][:3]
    ]
    error_items = [
        {
            "type": "error",
            "id": entry.id,
            "title": f"{entry.error_code} - {entry.title}",
            "machine": entry.machine,
            "date": entry.created_at.isoformat(),
        }
        for entry in signals["errors"][:3]
    ]
    report_items = [
        {
            "type": "maintenance_report",
            "id": document.id,
            "title": document.title,
            "machine": document.machine,
            "date": document.created_at.isoformat(),
        }
        for document in signals["maintenance_reports"][:3]
    ]
    plan_items = [
        {
            "type": "maintenance_plan",
            "id": plan.id,
            "title": plan.title,
            "next_due_date": plan.next_due_date.isoformat(),
            "is_active": plan.is_active,
        }
        for plan in signals["maintenance_plans"][:3]
    ]
    handover_items = [
        {
            "type": "shift_handover",
            "id": handover.id,
            "title": f"Schichtuebergabe {handover.shift_date.isoformat()}",
            "status": handover.status,
            "machine_id": handover.machine_id,
            "shift_date": handover.shift_date.isoformat(),
        }
        for handover in signals["shift_handovers"][:3]
    ]
    return task_items + error_items + report_items + plan_items + handover_items


def _preventive_evidence_summary(signals, rag_sources, recurring_trend=None):
    """Return audit-friendly evidence metadata for a light recommendation."""
    source_types = _preventive_source_types(signals, rag_sources, recurring_trend)
    direct_source_count = sum(
        len(signals[key])
        for key in (
            "tasks",
            "errors",
            "maintenance_reports",
            "maintenance_plans",
            "shift_handovers",
        )
    )
    return {
        "uses_only_visible_sources": True,
        "source_types": source_types,
        "direct_source_count": direct_source_count,
        "rag_source_count": len(rag_sources),
        "rag_sources": _preventive_rag_source_references(rag_sources),
        "recurring_issue_window_days": 30,
        "latest_signal_at": _latest_preventive_signal_at(signals),
        "predictive_claim": False,
    }


def _preventive_rag_source_references(rag_sources):
    """Return prompt-safe RAG source references for maintenance recommendations."""
    references = []
    for source in (rag_sources or [])[:3]:
        references.append(
            {
                "type": source.get("type") or source.get("source_type") or "",
                "id": source.get("id"),
                "source_type": source.get("source_type") or source.get("type") or "",
                "source_id": source.get("source_id") or source.get("id"),
                "chunk_id": source.get("chunk_id"),
                "title": str(source.get("title") or "")[:220],
                "module": source.get("module") or "",
                "machine_id": source.get("machine_id"),
                "role_visibility": source.get("role_visibility") or "",
                "created_at": source.get("created_at") or "",
                "score": _safe_int(source.get("score") or source.get("relevance")),
            }
        )
    return references


def _preventive_source_types(signals, rag_sources, recurring_trend=None):
    """Return sorted source type names contributing to a recommendation."""
    source_types = [
        source_type
        for source_type, signal_key in (
            ("task", "tasks"),
            ("error", "errors"),
            ("maintenance_report", "maintenance_reports"),
            ("maintenance_plan", "maintenance_plans"),
            ("shift_handover", "shift_handovers"),
        )
        if signals[signal_key]
    ]
    if rag_sources:
        source_types.append("rag_source")
    if recurring_trend:
        source_types.append("recurring_issue")
    return sorted(source_types)


def _latest_preventive_signal_at(signals):
    """Return the newest timestamp from direct recommendation evidence."""
    timestamps = []
    timestamps.extend(task.updated_at for task in signals["tasks"] if task.updated_at)
    timestamps.extend(entry.created_at for entry in signals["errors"] if entry.created_at)
    timestamps.extend(
        document.created_at for document in signals["maintenance_reports"] if document.created_at
    )
    timestamps.extend(
        datetime.combine(handover.shift_date, datetime.min.time())
        for handover in signals["shift_handovers"]
        if handover.shift_date
    )
    if not timestamps:
        return None
    return max(timestamps).isoformat()


def _matching_recurring_trend(machine, trends):
    """Return a recurring trend matching the machine, if available."""
    machine_name = machine.name.strip().lower()
    for trend in trends:
        if trend.get("machine_id") == machine.id:
            return trend
        if str(trend.get("affected_machine") or "").strip().lower() == machine_name:
            return trend
    return None


def _safe_int(value):
    """Return a non-negative integer from a source score-like value."""
    try:
        parsed = int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)
