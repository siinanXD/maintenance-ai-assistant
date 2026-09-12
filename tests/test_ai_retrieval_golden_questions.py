"""Golden tests for AI chat retrieval questions."""

from datetime import date, timedelta

from app.agent.mock_policy import _choose_tool_calls
from app.agent.tools import TOOL_REGISTRY, available_tools, execute_tool
from app.domain_models.common import utc_now
from app.extensions import db
from app.models import (
    AssistantTrainingEntry,
    Employee,
    ErrorEntry,
    GeneratedDocument,
    InventoryMaterial,
    KnowledgeChunk,
    KnowledgeDocument,
    Machine,
    MachineManual,
    MaintenancePlan,
    Priority,
    Role,
    ShiftHandover,
    Task,
    TaskStatus,
    User,
)
from app.services.golden_retrieval_question_service import (
    REQUIRED_GOLDEN_CATEGORIES,
    allowed_source_types,
    build_demo_golden_questions,
    build_golden_questions,
    dummy_source_ids,
    golden_categories,
)

MIN_RECALL_AT_K = 0.95
MIN_MRR = 0.5


def _golden_user(app, make_user, set_dashboard_permission):
    """Create the department-scoped golden test user with retrieval permissions."""
    user = make_user(
        username="golden_ai_retrieval_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    for dashboard in (
        "tasks",
        "errors",
        "machines",
        "inventory",
        "documents",
        "shiftplans",
    ):
        set_dashboard_permission(user["username"], dashboard, can_view=True)
    set_dashboard_permission(
        user["username"],
        "employees",
        can_view=True,
        employee_access_level="shift",
    )
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"
    return user


def _agent_retrieval(question, user):
    """Execute the tools the offline policy selects for a question and merge their sources.

    Structured questions are answered by ``list_*``/``count_records`` tools, knowledge
    questions by ``search_knowledge``; hybrid questions get both, mirroring the
    evidence the agent can ground an answer in.
    """
    available = {spec.name for spec in available_tools(user)}
    calls = _choose_tool_calls(question, available, set(TOOL_REGISTRY), None)
    if not any(name == "search_knowledge" for name, _ in calls):
        calls.append(("search_knowledge", {"query": question}))
    sources = []
    seen = set()
    failed_tools = []
    for name, arguments in calls:
        result = execute_tool(name, arguments, user)
        if result.status != "ok":
            failed_tools.append(f"{name}:{result.status}")
            continue
        for source in result.sources or []:
            key = (str(source.get("type") or ""), str(source.get("id") or ""))
            if key in seen:
                continue
            seen.add(key)
            sources.append(source)
    return {"sources": sources, "failed_tools": failed_tools}


def test_agent_tools_golden_retrieval_questions(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify fixed knowledge questions retrieve reproducible, relevant sources."""
    user = _golden_user(app, make_user, set_dashboard_permission)

    with app.app_context():
        db_user = db.session.get(User, user["id"])
        source_ids = _seed_golden_sources(db_user)
        cases = build_golden_questions(source_ids)
        results = {case.question: _agent_retrieval(case.question, db_user) for case in cases}

    failures = []
    evaluations = []
    for case in cases:
        result = results[case.question]
        sources = result["sources"]
        source_keys = _source_keys(sources)
        missing_sources = set(case.expected_sources) - source_keys
        missing_types = set(case.expected_source_types) - _source_types(sources)
        case_allowed_types = allowed_source_types(case)
        disallowed_types = _source_types(sources) - case_allowed_types
        forbidden_hits = source_keys & set(case.forbidden_sources)
        evaluation = _evaluate_golden_question(case, sources)
        evaluations.append(evaluation)

        if result["failed_tools"]:
            failures.append(f"{case.question}: tool failures {result['failed_tools']}")
        if not sources:
            failures.append(f"{case.question}: empty retrieval")
        if len(sources) < case.min_source_count:
            failures.append(
                f"{case.question}: expected at least {case.min_source_count} sources, "
                f"got {len(sources)}"
            )
        if missing_sources:
            failures.append(
                f"{case.question}: missing sources {sorted(missing_sources)}, "
                f"actual {sorted(source_keys)}"
            )
        if missing_types:
            failures.append(
                f"{case.question}: missing source types {sorted(missing_types)}, "
                f"actual {sorted(_source_types(sources))}"
            )
        if disallowed_types:
            failures.append(
                f"{case.question}: disallowed source types {sorted(disallowed_types)}, "
                f"allowed {sorted(case_allowed_types)}"
            )
        if forbidden_hits:
            failures.append(f"{case.question}: forbidden sources {sorted(forbidden_hits)}")

    metrics = _golden_metrics(evaluations)
    if metrics["no_result_count"]:
        failures.append(f"no_result_count={metrics['no_result_count']}")
    if metrics["forbidden_source_count"]:
        failures.append(f"forbidden_source_count={metrics['forbidden_source_count']}")
    if metrics["recall_at_k"] < MIN_RECALL_AT_K:
        failures.append(f"recall_at_k={metrics['recall_at_k']}")
    if metrics["mrr"] < MIN_MRR:
        failures.append(f"mrr={metrics['mrr']}")

    assert not failures, "\n".join(failures)


def test_ai_chat_endpoint_answers_golden_questions_with_sources(
    app,
    client,
    make_user,
    auth_headers,
    set_dashboard_permission,
):
    """Verify the agent chat endpoint grounds every golden question in visible sources."""
    user = _golden_user(app, make_user, set_dashboard_permission)

    with app.app_context():
        db_user = db.session.get(User, user["id"])
        cases = build_golden_questions(_seed_golden_sources(db_user))

    failures = []
    for case in cases:
        response = client.post(
            "/api/v1/ai/chat",
            headers=auth_headers(user["username"]),
            json={"message": case.question},
        )
        payload = response.get_json() or {}
        diagnostics = payload.get("diagnostics") or {}
        if response.status_code != 200:
            failures.append(f"{case.question}: HTTP {response.status_code}")
            continue
        if diagnostics.get("empty_retrieval") is True or not payload.get("sources"):
            failures.append(
                f"{case.question}: no sources via "
                f"{[entry.get('tool') for entry in payload.get('tool_trace') or []]}"
            )

    assert not failures, "\n".join(failures)


def test_golden_question_set_has_required_coverage():
    """Verify the golden question structure covers core retrieval domains."""
    cases = build_golden_questions(dummy_source_ids())
    categories = set()
    for case in cases:
        categories.update(golden_categories(case))

    assert len(cases) >= 20
    assert REQUIRED_GOLDEN_CATEGORIES.issubset(categories)
    assert "Mitarbeiter" in categories
    assert all(case.expected_sources for case in cases)
    assert all(case.min_source_count >= 1 for case in cases)
    assert all(allowed_source_types(case) for case in cases)
    assert all(
        case.expected_keywords for case in cases if "shift_handover" in case.expected_source_types
    )


def test_demo_golden_handover_questions_include_expected_keywords():
    """Verify demo handover golden questions are keyword-checkable."""
    cases = build_demo_golden_questions(
        {
            "task_hydraulic": 101,
            "hydraulic": 301,
            "ins_e_103": 201,
            "ins_e_106": 202,
            "seal_kit": 401,
            "oring": 402,
            "hydraulic_plan": 501,
            "hydraulic_manual_doc": 601,
            "hydraulic_training_doc": 602,
            "spritz_handover": 901,
        }
    )

    assert all(
        case.expected_keywords for case in cases if "shift_handover" in case.expected_source_types
    )


def _seed_golden_sources(user):
    """Create deterministic project data used by golden AI retrieval tests."""
    today = date.today()
    machine = Machine(
        name="Presse Golden 7",
        produced_item="Hydraulikdeckel",
        required_employees=2,
        criticality="critical",
        status="maintenance_required",
    )
    normal_machine = Machine(
        name="Presse Golden 8",
        produced_item="Standarddeckel",
        required_employees=1,
        criticality="normal",
        status="running",
    )
    db.session.add_all([machine, normal_machine])
    db.session.flush()

    task_today = Task(
        title="Golden offene Hydraulikpruefung",
        description="Offene Aufgabe heute an Presse Golden 7 mit Fehler E104.",
        priority=Priority.URGENT,
        status=TaskStatus.OPEN,
        due_date=today,
        department=user.department,
        created_by=user.id,
    )
    task_overdue = Task(
        title="Golden ueberfaellige Sensorpruefung",
        description="Ueberfaellige Aufgabe an Presse Golden 7.",
        priority=Priority.URGENT,
        status=TaskStatus.OPEN,
        due_date=today - timedelta(days=3),
        department=user.department,
        created_by=user.id,
    )
    task_done = Task(
        title="Golden abgeschlossene Gegenprobe",
        description="Diese erledigte Aufgabe soll nicht als offen zaehlen.",
        priority=Priority.NORMAL,
        status=TaskStatus.DONE,
        due_date=today,
        department=user.department,
        created_by=user.id,
    )
    db.session.add_all([task_today, task_overdue, task_done])

    error_e104 = _error_entry(
        machine="Presse Golden 7",
        code="E104",
        title="Sensorabgleich Hydraulik",
        description="Fehler E104 bedeutet Sensorabgleich an Presse Golden 7.",
        solution="Sensor reinigen, Abstand pruefen und Sensorabgleich dokumentieren.",
        user=user,
    )
    error_x900 = _error_entry(
        machine="Presse Golden 7",
        code="X900",
        title="Hydraulikdruckverlust",
        description="X900 weist auf Hydraulikdruckverlust an Presse Golden 7 hin.",
        solution="Druckspeicher pruefen und Leckage am Ventilblock suchen.",
        user=user,
    )
    foreign_error = _error_entry(
        machine="Fremde Presse",
        code="FG999",
        title="Fremder Fehler",
        description="Fremder Instandhaltungsfehler.",
        solution="Nicht sichtbar fuer Produktion.",
        user=user,
        department_name="Instandhaltung",
    )

    material_filter = InventoryMaterial(
        name="Golden Hydraulikfilter",
        unit_cost=42,
        quantity=1,
        min_quantity=4,
        criticality="critical",
        lead_time_days=12,
        manufacturer="Golden Parts",
        machine=machine,
    )
    material_sensor = InventoryMaterial(
        name="Golden E104 Sensorsatz",
        unit_cost=89,
        quantity=2,
        min_quantity=5,
        criticality="high",
        lead_time_days=9,
        manufacturer="Golden Parts",
        machine=machine,
    )
    db.session.add_all([material_filter, material_sensor])

    employee = Employee(
        personnel_number="GOLDEN-EMP-7",
        name="Golden Hydraulikerin Mila",
        department="Produktion",
        shift_model="3-Schicht",
        current_shift="Spaet",
        next_shift="Nacht",
        team=7,
        qualifications="Hydraulikqualifikation Golden Presse 7 Sensorabgleich",
        favorite_machine="Presse Golden 7",
        favorite_machine_id=machine.id,
    )
    db.session.add(employee)

    plan = MaintenancePlan(
        title="Golden Hydraulikpruefung faellig",
        description="Faellige Wartung fuer Presse Golden 7: Hydraulikdruck pruefen.",
        interval_days=30,
        next_due_date=today,
        priority=Priority.URGENT,
        is_active=True,
        machine=machine,
        department=user.department,
        created_by=user.id,
    )
    db.session.add(plan)

    document = GeneratedDocument(
        task=task_today,
        document_type="maintenance_report",
        title="Golden Dokumentation X900",
        relative_path="golden/x900_report.html",
        department="Produktion",
        machine="Presse Golden 7",
        summary="Dokumentation hilft bei X900 Hydraulikdruckverlust.",
        created_by=user.id,
        created_at=utc_now(),
    )
    manual = MachineManual(
        machine=machine,
        department="Produktion",
        title="Golden Handbuch Sensorabgleich E104",
        original_filename="golden-e104-handbuch.pdf",
        relative_path="manuals/golden-e104.pdf",
        content_type="application/pdf",
        analysis="Sensorabgleich E104 an Presse Golden 7 kalibrieren.",
        analysis_status="completed",
        summary="Handbuch zu Sensorabgleich E104.",
        summary_status="completed",
        created_by=user.id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    training = AssistantTrainingEntry(
        title="Golden Trainingsantwort Hydraulikpruefung",
        question="Welche Trainingsantwort gibt es zur Hydraulikpruefung?",
        answer="Hydraulikpruefung: Druck, Filter und Ventilblock kontrollieren.",
        keywords="Golden, Hydraulikpruefung, Trainingsantwort",
        category="wartung",
        department="Produktion",
        is_active=True,
        priority=90,
        created_by=user.id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    handover = ShiftHandover(
        department="Produktion",
        shift_date=today,
        shift_type="late",
        status="open",
        handed_over_by=user.id,
        content="Presse Golden 7 braucht Kontrolle.",
        open_tasks="Offene Aufgabe: Golden offene Hydraulikpruefung.",
        machine_notes="Presse Golden 7 mit E104 Sensorabgleich beobachten.",
        next_notes="Hydraulikdruckverlust X900 im Blick behalten.",
    )
    db.session.add_all([document, manual, training, handover])
    db.session.flush()

    knowledge_hydraulic = _knowledge_document(
        title="Golden Anleitung Hydraulikdruckverlust",
        text="Anleitung Hydraulikdruckverlust: Druckspeicher und Ventilblock pruefen.",
        user=user,
    )
    knowledge_e104 = _knowledge_document(
        title="Golden Sensorabgleich E104 Wissen",
        text="Sensorabgleich E104: Sensor reinigen, Abstand einstellen und testen.",
        user=user,
        source_type="machine_manual",
        source_id=manual.id,
    )
    knowledge_training = _knowledge_document(
        title="Golden Trainingsantwort Hydraulikpruefung",
        text="Trainingsantwort Hydraulikpruefung: Filter, Druck und Leckage pruefen.",
        user=user,
        source_type="manual_training",
        source_id=training.id,
    )
    foreign_doc = _knowledge_document(
        title="Golden Fremdquelle Instandhaltung",
        text="Diese fremde Quelle darf Produktion nicht sehen.",
        user=user,
        department="Instandhaltung",
    )
    db.session.commit()

    return {
        "task_today": task_today.id,
        "task_overdue": task_overdue.id,
        "task_done": task_done.id,
        "error_e104": error_e104.id,
        "error_x900": error_x900.id,
        "foreign_error": foreign_error.id,
        "machine": machine.id,
        "normal_machine": normal_machine.id,
        "material_filter": material_filter.id,
        "material_sensor": material_sensor.id,
        "employee_hydraulic": employee.id,
        "plan": plan.id,
        "document": document.id,
        "manual": manual.id,
        "training": training.id,
        "handover": handover.id,
        "knowledge_hydraulic": knowledge_hydraulic.id,
        "knowledge_e104": knowledge_e104.id,
        "knowledge_training": knowledge_training.id,
        "foreign_doc": foreign_doc.id,
    }


def _error_entry(
    machine,
    code,
    title,
    description,
    solution,
    user,
    department_name="Produktion",
):
    """Create one deterministic error catalog entry."""
    department = user.department
    if department_name != user.department.name:
        from app.models import Department

        department = Department.query.filter_by(name=department_name).first()
        if not department:
            department = Department(name=department_name)
            db.session.add(department)
            db.session.flush()
    entry = ErrorEntry(
        machine=machine,
        error_code=code,
        title=title,
        description=description,
        possible_causes=f"Ursache fuer {code}",
        solution=solution,
        department=department,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def _knowledge_document(
    title,
    text,
    user,
    department="Produktion",
    source_type="upload",
    source_id=None,
):
    """Create one indexed knowledge document with a single chunk."""
    timestamp = utc_now()
    document = KnowledgeDocument(
        source_type=source_type,
        source_id=source_id,
        title=title,
        original_filename=f"{title}.txt",
        relative_path=f"uploads/{title}.txt",
        content_type="text/plain",
        department=department,
        status="indexed",
        quality_status="admin_approved",
        is_public=True,
        chunk_count=1,
        created_by=user.id,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.session.add(document)
    db.session.flush()
    db.session.add(
        KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            text=text,
            token_text=text.lower(),
        )
    )
    db.session.flush()
    return document


def _source_keys(sources):
    """Return stable type/id pairs from API source payloads."""
    return {(str(source.get("type") or ""), str(source.get("id") or "")) for source in sources}


def _source_types(sources):
    """Return source types from API source payloads."""
    return {str(source.get("type") or "") for source in sources}


def _evaluate_golden_question(case, sources):
    """Return retrieval metrics for one golden question."""
    ranked_keys = _ranked_source_keys(sources, limit=case.top_k)
    expected_sources = set(case.expected_sources)
    forbidden_sources = set(case.forbidden_sources)
    allowed_types = allowed_source_types(case)
    expected_hits = [key for key in ranked_keys if key in expected_sources]
    forbidden_hits = [key for key in ranked_keys if key in forbidden_sources]
    disallowed_type_hits = [key for key in ranked_keys if key[0] and key[0] not in allowed_types]
    return {
        "question": case.question,
        "expected_count": len(expected_sources),
        "expected_hit_count": len(set(expected_hits)),
        "recall_at_k": _recall_at_k(expected_hits, expected_sources),
        "mrr": _mrr(ranked_keys, expected_sources),
        "no_result": not ranked_keys,
        "forbidden_source_count": len(forbidden_hits) + len(disallowed_type_hits),
    }


def _golden_metrics(evaluations):
    """Return aggregate golden retrieval metrics."""
    metric_items = [item for item in evaluations if item["expected_count"] > 0]
    return {
        "query_count": len(evaluations),
        "metric_query_count": len(metric_items),
        "recall_at_k": _average_metric(metric_items, "recall_at_k"),
        "mrr": _average_metric(metric_items, "mrr"),
        "no_result_count": sum(1 for item in evaluations if item["no_result"]),
        "forbidden_source_count": sum(item["forbidden_source_count"] for item in evaluations),
    }


def _ranked_source_keys(sources, limit):
    """Return ordered type/id pairs from API source payloads."""
    return [
        (str(source.get("type") or ""), str(source.get("id") or ""))
        for source in (sources or [])[:limit]
    ]


def _recall_at_k(expected_hits, expected_sources):
    """Return Recall@K for expected source pairs."""
    if not expected_sources:
        return 1.0
    return round(len(set(expected_hits)) / len(expected_sources), 4)


def _mrr(ranked_keys, expected_sources):
    """Return mean reciprocal rank for one query."""
    if not expected_sources:
        return 1.0
    for index, key in enumerate(ranked_keys, start=1):
        if key in expected_sources:
            return round(1 / index, 4)
    return 0.0


def _average_metric(items, key):
    """Return an average metric for evaluated golden questions."""
    if not items:
        return 0.0
    return round(sum(item[key] for item in items) / len(items), 4)
