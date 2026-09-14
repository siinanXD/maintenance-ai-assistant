"""Tests for the golden retrieval evaluation harness."""

import json
from datetime import timedelta

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import (
    AssistantTrainingEntry,
    ErrorEntry,
    InventoryMaterial,
    KnowledgeChunk,
    KnowledgeDocument,
    Machine,
    MaintenancePlan,
    Priority,
    RetrievalEvaluationRun,
    Role,
    ShiftHandover,
    Task,
    TaskStatus,
    User,
)
from app.services.golden_retrieval_question_service import (
    GoldenQuestion,
    build_golden_questions,
    dummy_source_ids,
)
from app.services.retrieval_evaluation_common import RETRIEVAL_MODE_FULL
from app.services.retrieval_evaluation_history import (
    evaluation_quality_gate,
    persist_retrieval_evaluation_result,
    retrieval_evaluation_history,
)
from app.services.retrieval_evaluation_service import (
    GoldenRetrievalQuery,
    evaluate_and_persist_golden_queries,
    evaluate_golden_queries,
    golden_retrieval_query_from_question,
)
from app.services.vector_store_common import VectorSearchResult


def test_evaluation_quality_gate_warns_on_missing_chunk_structure_metadata():
    """Verify chunk block metadata coverage is a non-blocking quality warning."""
    quality_gate = evaluation_quality_gate(
        {
            "query_count": 2,
            "recall_at_k": 1.0,
            "mrr": 1.0,
            "keyword_query_count": 1,
            "keyword_hit_rate": 1.0,
            "permission_leak_count": 0,
            "forbidden_source_hit_count": 0,
            "expected_no_result_count": 1,
            "expected_no_result_success_rate": 1.0,
            "unexpected_no_result_rate": 0.0,
            "min_source_count_pass_rate": 1.0,
            "query_type_expected_count": 1,
            "query_type_accuracy": 1.0,
            "source_metadata_count": 2,
            "source_pair_coverage_rate": 1.0,
            "metadata_pair_coverage_rate": 1.0,
            "chunk_metadata_coverage": {
                "retrieved_chunk_count": 2,
                "block_metadata_coverage_rate": 0.5,
            },
        }
    )

    warning = quality_gate["warnings"][0]
    assert quality_gate["status"] == "warning"
    assert quality_gate["passed"] is False
    assert warning["metric"] == "block_metadata_coverage_rate"
    assert warning["reason"] == "chunk_structure_metadata_incomplete"


def test_golden_retrieval_evaluation_scores_seeded_queries(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify golden queries calculate stable retrieval metrics."""
    user_data = make_user(
        username="golden_eval_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV900 Filterdruck Messpunkt",
                    expected_source_ids=(source_ids["filter"],),
                    expected_keywords=("Filterdruck", "Messpunkt"),
                    expected_query_type="document_question",
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV903 Orbit Lagerwelle",
                    expected_source_types=("upload",),
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV901 Kupplungsspiel Trainingshinweis",
                    expected_source_types=("manual_training",),
                    expected_keywords=("Kupplungsspiel",),
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV902 Fremdquelle Instandhaltung",
                    forbidden_source_ids=(source_ids["foreign"],),
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV999 Cyanotyp Trefferlos",
                    top_k=3,
                ),
            ),
            user,
        )

    by_query = {item["query"]: item for item in result["queries"]}
    filter_query = by_query["GEV900 Filterdruck Messpunkt"]
    training_query = by_query["GEV901 Kupplungsspiel Trainingshinweis"]
    forbidden_query = by_query["GEV902 Fremdquelle Instandhaltung"]

    assert result["query_count"] == 5
    assert result["metric_query_count"] == 3
    assert result["recall_at_k"] == 1.0
    assert result["mrr"] == 1.0
    assert result["ndcg_at_k"] == 1.0
    assert result["keyword_query_count"] == 2
    assert result["keyword_hit_rate"] == 1.0
    assert result["permission_leak_count"] == 0
    assert result["forbidden_source_hit_count"] == 0
    assert result["no_result_count"] == 2
    assert result["no_result_rate"] == 0.4
    assert result["chunk_metadata_coverage"]["retrieved_chunk_count"] >= 3
    assert result["chunk_metadata_coverage"]["coverage_rate"] == 1.0
    assert result["source_metadata_coverage"]["retrieved_source_count"] >= 3
    assert result["source_metadata_coverage"]["source_id_coverage_rate"] == 1.0
    assert result["source_metadata_coverage"]["source_type_coverage_rate"] == 1.0
    field_coverage = result["source_metadata_coverage"]["field_coverage"]
    assert field_coverage["source_id"]["coverage_rate"] == 1.0
    assert field_coverage["source_type"]["coverage_rate"] == 1.0
    assert field_coverage["title"]["coverage_rate"] == 1.0
    assert field_coverage["module"]["coverage_rate"] == 1.0
    assert field_coverage["role_visibility"]["coverage_rate"] == 1.0
    assert field_coverage["created_at"]["coverage_rate"] == 1.0
    assert "machine_id" in field_coverage
    assert filter_query["normalized_query"] == "gev900 filterdruck messpunkt"
    assert filter_query["retrieved_sources"][0]["source_id"] == source_ids["filter"]
    assert filter_query["retrieved_sources"][0]["module"] == "knowledge"
    assert filter_query["retrieved_sources"][0]["role_visibility"]
    assert filter_query["retrieved_sources"][0]["created_at"]
    assert filter_query["retrieved_sources"][0]["chunk_char_count"] > 0
    assert filter_query["retrieved_sources"][0]["chunk_token_count"] > 0
    assert filter_query["retrieved_sources"][0]["chunk_block_count"] == 1
    assert filter_query["retrieved_sources"][0]["chunk_block_kinds"] == ["paragraph"]
    assert filter_query["retrieved_sources"][0]["chunking_mode"] == "hybrid_semantic"
    assert filter_query["chunk_metadata_coverage"]["coverage_rate"] == 1.0
    assert filter_query["chunk_metadata_coverage"]["block_metadata_coverage_rate"] == 1.0
    assert filter_query["chunk_metadata_coverage"]["average_block_count"] == 1
    assert filter_query["chunk_metadata_coverage"]["block_kind_distribution"] == {"paragraph": 1}
    assert filter_query["source_metadata_coverage"]["source_pair_coverage_rate"] == 1.0
    assert filter_query["expected_keyword_count"] == 2
    assert filter_query["expected_keyword_hit_count"] == 2
    assert filter_query["keyword_hit_rate"] == 1.0
    assert set(filter_query["matched_keywords"]) == {"Filterdruck", "Messpunkt"}
    assert filter_query["missing_keywords"] == []
    assert result["keyword_miss_count"] == 0
    assert training_query["retrieved_sources"][0]["source_type"] == "manual_training"
    assert source_ids["foreign"] not in {
        source["source_id"] for source in forbidden_query["retrieved_sources"]
    }


def test_golden_retrieval_evaluation_reports_missing_expected_keywords(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify golden evaluation explains which expected keywords were not retrieved."""
    user_data = make_user(
        username="golden_eval_missing_keyword_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV900 Filterdruck Messpunkt",
                    expected_source_ids=(source_ids["filter"],),
                    expected_keywords=("Filterdruck", "NichtVorhanden"),
                    top_k=3,
                ),
            ),
            user,
        )

    query_result = result["queries"][0]
    assert query_result["expected_keyword_hit_count"] == 1
    assert query_result["keyword_hit_rate"] == 0.5
    assert query_result["matched_keywords"] == ["Filterdruck"]
    assert query_result["missing_keywords"] == ["NichtVorhanden"]
    assert result["keyword_miss_count"] == 1


def test_golden_retrieval_evaluation_reports_min_source_count_failures(
    app,
    make_user,
    set_dashboard_permission,
    monkeypatch,
):
    """Verify golden evaluation measures minimum source coverage per query."""
    user_data = make_user(
        username="golden_eval_min_sources_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)

    def fake_retrieve_vector_chunks(_query, _user, limit=None):
        """Return one deterministic vector source despite a higher expectation."""
        return [
            VectorSearchResult(
                text="GEV910 Einzelquelle",
                score=0.9,
                metadata={
                    "id": 910,
                    "source_id": 910,
                    "source_type": "upload",
                    "title": "GEV910 Einzelquelle",
                },
            )
        ][:limit]

    monkeypatch.setattr(
        "app.services.retrieval_evaluation_sources.retrieve_vector_chunks",
        fake_retrieve_vector_chunks,
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV910 braucht zwei Quellen",
                    expected_source_types=("upload",),
                    min_source_count=2,
                    top_k=3,
                ),
            ),
            user,
        )

    query_result = result["queries"][0]
    assert query_result["retrieved_source_count"] == 1
    assert query_result["min_source_count"] == 2
    assert query_result["min_source_count_met"] is False
    assert result["min_source_count_fail_count"] == 1
    assert result["min_source_count_pass_rate"] == 0.0


def test_golden_retrieval_evaluation_tracks_expected_no_result_queries(monkeypatch):
    """Verify intentional no-result checks do not inflate unexpected no-result rate."""

    def fake_retrieve_vector_chunks(query, _user, limit=None):
        """Return deterministic results for expected and unexpected no-result cases."""
        if "but retrieved" in query:
            return [
                VectorSearchResult(
                    text="GEV920 vorhandene Quelle",
                    score=0.9,
                    metadata={
                        "id": 920,
                        "source_id": 920,
                        "source_type": "upload",
                        "title": "GEV920 vorhandene Quelle",
                    },
                )
            ][:limit]
        if "expected empty" in query:
            return []
        if "unexpected empty" in query:
            return []
        return []

    monkeypatch.setattr(
        "app.services.retrieval_evaluation_sources.retrieve_vector_chunks",
        fake_retrieve_vector_chunks,
    )

    result = evaluate_golden_queries(
        (
            GoldenRetrievalQuery(
                query="GEV920 expected empty",
                expected_no_result=True,
                top_k=3,
            ),
            GoldenRetrievalQuery(
                query="GEV921 expected empty but retrieved",
                expected_no_result=True,
                top_k=3,
            ),
            GoldenRetrievalQuery(
                query="GEV922 unexpected empty",
                top_k=3,
            ),
        ),
        user=object(),
    )

    by_query = {item["query"]: item for item in result["queries"]}
    assert result["no_result_count"] == 2
    assert result["expected_no_result_count"] == 2
    assert result["expected_no_result_success_count"] == 1
    assert result["expected_no_result_success_rate"] == 0.5
    assert result["unexpected_no_result_count"] == 1
    assert result["unexpected_no_result_rate"] == 1.0
    assert result["min_source_count_fail_count"] == 1
    assert by_query["GEV920 expected empty"]["min_source_count_met"] is True
    assert by_query["GEV920 expected empty"]["expected_no_result_success"] is True
    assert by_query["GEV921 expected empty but retrieved"]["expected_no_result_success"] is False
    assert by_query["GEV922 unexpected empty"]["unexpected_no_result"] is True


def test_golden_retrieval_evaluation_tracks_query_type_accuracy(monkeypatch):
    """Verify golden evaluation measures query-understanding classification accuracy."""

    def fake_retrieve_vector_chunks(_query, _user, limit=None):
        """Return no retrieval results so the test isolates query classification."""
        return []

    monkeypatch.setattr(
        "app.services.retrieval_evaluation_sources.retrieve_vector_chunks",
        fake_retrieve_vector_chunks,
    )

    result = evaluate_golden_queries(
        (
            GoldenRetrievalQuery(
                query="Welche Tasks sind heute offen?",
                expected_query_type="task_question",
                expected_no_result=True,
            ),
            GoldenRetrievalQuery(
                query="Was bedeutet Fehler E104?",
                expected_query_type="machine_question",
                expected_no_result=True,
            ),
            GoldenRetrievalQuery(
                query="Unbewertete Klassifikation",
                expected_no_result=True,
            ),
        ),
        user=None,
    )

    by_query = {item["query"]: item for item in result["queries"]}
    task_query = by_query["Welche Tasks sind heute offen?"]
    error_query = by_query["Was bedeutet Fehler E104?"]
    unmeasured_query = by_query["Unbewertete Klassifikation"]
    assert result["query_type_expected_count"] == 2
    assert result["query_type_match_count"] == 1
    assert result["query_type_accuracy"] == 0.5
    assert task_query["actual_query_type"] == "task_question"
    assert task_query["query_type_match"] is True
    assert task_query["query_type_confidence"] > 0
    assert error_query["actual_query_type"] == "error_analysis"
    assert error_query["query_type_match"] is False
    assert unmeasured_query["expected_query_type"] == ""
    assert unmeasured_query["query_type_match"] is False


def test_handover_golden_question_keywords_flow_into_evaluation_query():
    """Verify handover golden keywords are preserved for evaluation metrics."""
    question = next(
        case
        for case in build_golden_questions(dummy_source_ids())
        if "shift_handover" in case.expected_source_types
    )

    query = golden_retrieval_query_from_question(question)

    assert query.expected_keywords == ("Hydraulikpruefung", "Sensorabgleich")
    assert query.expected_query_type == "trend_history_question"
    assert ("shift_handover", str(dummy_source_ids()["handover"])) in query.expected_sources


def test_golden_question_permission_context_flows_into_evaluation_query():
    """Verify reusable golden questions can declare permission-leak checks."""
    question = GoldenQuestion(
        question="Welche Trainingsantwort ist fuer Produktion sichtbar?",
        expected_source_types=("manual_training",),
        expected_no_result=True,
        required_permission_context={
            "requires_dashboards": ("documents",),
            "allowed_role_visibility": ("department:Produktion",),
        },
        expected_query_type="document_question",
    )

    query = golden_retrieval_query_from_question(question)

    assert query.expected_no_result is True
    assert query.expected_query_type == "document_question"
    assert query.required_permission_context == {
        "requires_dashboards": ("documents",),
        "allowed_role_visibility": ("department:Produktion",),
    }


def test_full_retrieval_evaluation_matches_handover_keywords_from_record(
    app,
    make_user,
    set_dashboard_permission,
    monkeypatch,
):
    """Verify full-mode keyword checks can inspect visible handover content."""
    user_data = make_user(
        username="golden_eval_handover_keyword_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "shiftplans", can_view=True)

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        handover = ShiftHandover(
            department="Produktion",
            shift_date=utc_now().date(),
            shift_type="Spaet",
            status="open",
            handed_over_by=user.id,
            open_tasks="Hydraulikpruefung fuer Presse Golden 7 ist offen.",
            machine_notes="Sensorabgleich an Presse Golden 7 beobachten.",
            next_notes="Naechste Schicht Druckverlauf pruefen lassen.",
        )
        db.session.add(handover)
        db.session.commit()
        handover_id = handover.id

        def fake_retrieve_context(_query, _user):
            """Return a public handover source without raw content."""
            return {
                "sources": [
                    {
                        "type": "shift_handover",
                        "id": handover_id,
                        "title": "Schichtuebergabe Spaet",
                    }
                ]
            }

        monkeypatch.setattr(
            "app.services.retrieval_evaluation_sources.retrieve_context",
            fake_retrieve_context,
        )
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="Was war zur Presse Golden 7 in der letzten Schicht offen?",
                    expected_sources=(("shift_handover", str(handover_id)),),
                    expected_keywords=("Hydraulikpruefung", "Sensorabgleich"),
                    top_k=3,
                ),
            ),
            user,
            retrieval_mode=RETRIEVAL_MODE_FULL,
        )

    query_result = result["queries"][0]
    assert query_result["retrieval_mode"] == RETRIEVAL_MODE_FULL
    assert query_result["expected_keyword_hit_count"] == 2
    assert query_result["keyword_hit_rate"] == 1.0
    assert query_result["missing_keywords"] == []
    assert result["keyword_miss_count"] == 0


def test_full_retrieval_evaluation_matches_task_keywords_from_record(
    app,
    make_user,
    make_task,
    set_dashboard_permission,
    monkeypatch,
):
    """Verify full-mode keyword checks can inspect visible task content."""
    user_data = make_user(
        username="golden_eval_task_keyword_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "tasks", can_view=True)
    task_id = make_task(
        "Presse Golden 7 pruefen",
        creator_username=user_data["username"],
        department_name="Produktion",
        description="Hydraulikfilter GEV901 ersetzen und Druckabfall dokumentieren.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])

        def fake_retrieve_context(_query, _user):
            """Return a public task source without raw task description."""
            return {
                "sources": [
                    {
                        "type": "task",
                        "id": task_id,
                        "title": "Presse Golden 7 pruefen",
                    }
                ]
            }

        monkeypatch.setattr(
            "app.services.retrieval_evaluation_sources.retrieve_context",
            fake_retrieve_context,
        )
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="Welche Aufgabe nennt Hydraulikfilter GEV901?",
                    expected_sources=(("task", str(task_id)),),
                    expected_keywords=("Hydraulikfilter", "Druckabfall"),
                    top_k=3,
                ),
            ),
            user,
            retrieval_mode=RETRIEVAL_MODE_FULL,
        )

    query_result = result["queries"][0]
    assert query_result["expected_keyword_hit_count"] == 2
    assert query_result["keyword_hit_rate"] == 1.0
    assert query_result["missing_keywords"] == []
    assert result["keyword_miss_count"] == 0


def test_full_retrieval_evaluation_matches_error_keywords_from_record(
    app,
    make_user,
    make_error_entry,
    set_dashboard_permission,
    monkeypatch,
):
    """Verify full-mode keyword checks can inspect visible error-entry content."""
    user_data = make_user(
        username="golden_eval_error_keyword_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "errors", can_view=True)
    error_id = make_error_entry(
        "Presse Golden 7",
        "GEV902",
        "Druckabfall",
        department_name="Produktion",
        description="Stoerung an Hydraulikgruppe.",
        possible_causes="Rueckschlagventil klemmt.",
        solution="Rueckschlagventil reinigen und Sensorabgleich pruefen.",
    )

    with app.app_context():
        user = db.session.get(User, user_data["id"])

        def fake_retrieve_context(_query, _user):
            """Return a public error source without raw cause or solution text."""
            return {
                "sources": [
                    {
                        "type": "error",
                        "id": error_id,
                        "title": "GEV902 - Druckabfall",
                    }
                ]
            }

        monkeypatch.setattr(
            "app.services.retrieval_evaluation_sources.retrieve_context",
            fake_retrieve_context,
        )
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="Welche Fehlerquelle nennt Rueckschlagventil und Sensorabgleich?",
                    expected_sources=(("error", str(error_id)),),
                    expected_keywords=("Rueckschlagventil", "Sensorabgleich"),
                    top_k=3,
                ),
            ),
            user,
            retrieval_mode=RETRIEVAL_MODE_FULL,
        )

    query_result = result["queries"][0]
    assert query_result["expected_keyword_hit_count"] == 2
    assert query_result["keyword_hit_rate"] == 1.0
    assert query_result["missing_keywords"] == []
    assert result["keyword_miss_count"] == 0


def test_full_retrieval_evaluation_matches_maintenance_plan_keywords_from_record(
    app,
    make_user,
    make_machine,
    set_dashboard_permission,
    monkeypatch,
):
    """Verify full-mode keyword checks can inspect maintenance-plan content."""
    user_data = make_user(
        username="golden_eval_maintenance_keyword_user",
        role=Role.INSTANDHALTUNG,
        department_name="Instandhaltung",
    )
    set_dashboard_permission(user_data["username"], "machines", can_view=True)
    machine_id = make_machine(name="Golden Wartungspresse")

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        plan = MaintenancePlan(
            title="Golden Druckspeicher Wartung",
            description="Hydraulikdruck und Rueckschlagventil an Golden Wartungspresse pruefen.",
            interval_days=21,
            next_due_date=utc_now().date(),
            priority=Priority.SOON,
            is_active=True,
            machine_id=machine_id,
            department=user.department,
            created_by=user.id,
        )
        db.session.add(plan)
        db.session.commit()
        plan_id = plan.id

        def fake_retrieve_context(_query, _user):
            """Return a public maintenance-plan source without raw description."""
            return {
                "sources": [
                    {
                        "type": "maintenance_plan",
                        "id": plan_id,
                        "title": "Golden Druckspeicher Wartung",
                    }
                ]
            }

        monkeypatch.setattr(
            "app.services.retrieval_evaluation_sources.retrieve_context",
            fake_retrieve_context,
        )
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="Welche Wartung nennt Rueckschlagventil und Hydraulikdruck?",
                    expected_sources=(("maintenance_plan", str(plan_id)),),
                    expected_keywords=("Rueckschlagventil", "Hydraulikdruck"),
                    top_k=3,
                ),
            ),
            user,
            retrieval_mode=RETRIEVAL_MODE_FULL,
        )

    query_result = result["queries"][0]
    assert query_result["expected_keyword_hit_count"] == 2
    assert query_result["keyword_hit_rate"] == 1.0
    assert query_result["missing_keywords"] == []
    assert result["keyword_miss_count"] == 0


def test_golden_retrieval_evaluation_counts_manual_training_permission_context(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify manual training does not leak without the required dashboard permission."""
    user_data = make_user(
        username="golden_eval_no_docs_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=False)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV901 Kupplungsspiel Trainingshinweis",
                    forbidden_source_types=("manual_training",),
                    required_permission_context={
                        "requires_dashboards": ("documents",),
                        "forbidden_source_types": ("manual_training",),
                    },
                    top_k=3,
                ),
            ),
            user,
        )

    query_result = result["queries"][0]
    assert result["permission_leak_count"] == 0
    assert result["forbidden_source_hit_count"] == 0
    assert result["no_result_count"] == 1
    assert query_result["retrieved_sources"] == []
    assert query_result["required_permission_context"]["requires_dashboards"] == ["documents"]


def test_golden_retrieval_evaluation_counts_role_visibility_permission_context(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify role visibility mismatches count as permission leaks."""
    user_data = make_user(
        username="golden_eval_role_visibility_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV900 Filterdruck Messpunkt",
                    expected_source_ids=(source_ids["filter"],),
                    required_permission_context={
                        "allowed_role_visibility": ("department:Instandhaltung",),
                    },
                    top_k=1,
                ),
            ),
            user,
        )

    query_result = result["queries"][0]
    assert query_result["retrieved_sources"][0]["role_visibility"] == "department:Produktion"
    assert query_result["permission_leak_count"] == 1
    assert result["permission_leak_count"] == 1
    assert query_result["required_permission_context"]["allowed_role_visibility"] == [
        "department:Instandhaltung"
    ]


def test_golden_retrieval_evaluation_matches_source_record_pairs(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify expected and forbidden source pairs match original module records."""
    user_data = make_user(
        username="golden_eval_source_record_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV901 Kupplungsspiel Trainingshinweis",
                    expected_sources=(("manual_training", str(source_ids["training_record"])),),
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV901 Kupplungsspiel Trainingshinweis",
                    forbidden_sources=(("manual_training", str(source_ids["training_record"])),),
                    top_k=3,
                ),
            ),
            user,
        )

    matched_query = result["queries"][0]
    forbidden_query = result["queries"][1]
    assert matched_query["retrieved_sources"][0]["source_type"] == "manual_training"
    assert (
        matched_query["retrieved_sources"][0]["source_record_id"] == source_ids["training_record"]
    )
    assert matched_query["expected_hit_count"] == 1
    assert matched_query["recall_at_k"] == 1.0
    assert matched_query["mrr"] == 1.0
    assert forbidden_query["forbidden_source_hit_count"] == 1
    assert result["forbidden_source_hit_count"] == 1


def test_golden_retrieval_evaluation_reports_missing_expected_results(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify misses and empty result sets produce stable zero metrics."""
    user_data = make_user(
        username="golden_eval_miss_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV902 Fremdquelle Instandhaltung",
                    expected_source_ids=(source_ids["foreign"],),
                    forbidden_source_ids=(source_ids["foreign"],),
                    top_k=3,
                ),
            ),
            user,
        )

    assert result["metric_query_count"] == 1
    assert result["recall_at_k"] == 0.0
    assert result["mrr"] == 0.0
    assert result["ndcg_at_k"] == 0.0
    assert result["forbidden_source_hit_count"] == 0
    assert result["no_result_count"] == 1


def test_golden_retrieval_evaluation_uses_full_retrieval_pipeline(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify full-mode golden evaluation uses the chat retrieval pipeline."""
    user_data = make_user(
        username="golden_eval_full_pipeline_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV900 Filterdruck Messpunkt",
                    expected_sources=(
                        ("knowledge", str(source_ids["filter"])),
                        ("upload", str(source_ids["filter"])),
                    ),
                    expected_source_types=("knowledge", "upload"),
                    top_k=3,
                ),
            ),
            user,
            retrieval_mode=RETRIEVAL_MODE_FULL,
        )

    query_result = result["queries"][0]
    assert result["query_count"] == 1
    assert result["recall_at_k"] == 1.0
    assert query_result["retrieval_mode"] == RETRIEVAL_MODE_FULL
    assert query_result["retrieved_sources"][0]["source_type"] == "knowledge"
    assert query_result["retrieved_sources"][0]["metadata_source_type"] == "upload"
    assert query_result["retrieved_sources"][0]["source_id"] == source_ids["filter"]


def test_golden_retrieval_evaluation_persists_prompt_safe_run(
    app,
    make_user,
    set_dashboard_permission,
):
    """Verify golden evaluation runs persist only aggregate quality metrics."""
    user_data = make_user(
        username="golden_eval_persist_user",
        role=Role.PRODUKTION,
        department_name="Produktion",
    )
    set_dashboard_permission(user_data["username"], "documents", can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        user = db.session.get(User, user_data["id"])
        source_ids = _seed_golden_retrieval_documents(user.id)
        result = evaluate_and_persist_golden_queries(
            (
                GoldenRetrievalQuery(
                    query="GEV900 Filterdruck Messpunkt",
                    expected_source_ids=(source_ids["filter"],),
                    expected_keywords=("Filterdruck", "Messpunkt"),
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV999 Cyanotyp Trefferlos",
                    top_k=3,
                ),
                GoldenRetrievalQuery(
                    query="GEV998 Erwartet Trefferlos",
                    expected_no_result=True,
                    expected_query_type="general_question",
                    top_k=3,
                ),
            ),
            user,
        )
        run = RetrievalEvaluationRun.query.one()
        run_payload = run.to_dict()

    assert result["evaluation_run"]["id"] == run_payload["id"]
    assert run_payload["query_count"] == 3
    assert run_payload["recall_at_k"] == result["recall_at_k"]
    assert run_payload["mrr"] == result["mrr"]
    assert run_payload["ndcg_at_k"] == result["ndcg_at_k"]
    assert run_payload["keyword_query_count"] == result["keyword_query_count"]
    assert run_payload["keyword_hit_rate"] == result["keyword_hit_rate"]
    assert run_payload["permission_leak_count"] == result["permission_leak_count"]
    assert run_payload["forbidden_source_hit_count"] == result["forbidden_source_hit_count"]
    assert run_payload["no_result_count"] == result["no_result_count"]
    assert run_payload["no_result_rate"] == result["no_result_rate"]
    assert run_payload["expected_no_result_count"] == result["expected_no_result_count"]
    assert (
        run_payload["expected_no_result_success_count"]
        == result["expected_no_result_success_count"]
    )
    assert (
        run_payload["expected_no_result_success_rate"] == result["expected_no_result_success_rate"]
    )
    assert run_payload["unexpected_no_result_count"] == result["unexpected_no_result_count"]
    assert run_payload["unexpected_no_result_rate"] == result["unexpected_no_result_rate"]
    assert run_payload["min_source_count_fail_count"] == result["min_source_count_fail_count"]
    assert run_payload["min_source_count_pass_rate"] == result["min_source_count_pass_rate"]
    assert run_payload["query_type_expected_count"] == result["query_type_expected_count"]
    assert run_payload["query_type_match_count"] == result["query_type_match_count"]
    assert run_payload["query_type_accuracy"] == result["query_type_accuracy"]
    assert (
        run_payload["source_metadata_count"]
        == result["source_metadata_coverage"]["retrieved_source_count"]
    )
    assert (
        run_payload["source_id_coverage_rate"]
        == result["source_metadata_coverage"]["source_id_coverage_rate"]
    )
    assert (
        run_payload["source_pair_coverage_rate"]
        == result["source_metadata_coverage"]["source_pair_coverage_rate"]
    )
    assert "GEV900" not in json.dumps(run_payload, ensure_ascii=True)
    assert "Filterdruck" not in json.dumps(run_payload, ensure_ascii=True)


def test_retrieval_evaluation_history_detects_regression(app):
    """Verify persisted evaluation history reports quality regressions."""
    with app.app_context():
        previous = persist_retrieval_evaluation_result(
            {
                "query_count": 5,
                "recall_at_k": 1.0,
                "mrr": 1.0,
                "ndcg_at_k": 1.0,
                "keyword_query_count": 2,
                "keyword_hit_rate": 1.0,
                "permission_leak_count": 0,
                "forbidden_source_hit_count": 0,
                "no_result_count": 0,
                "no_result_rate": 0.0,
                "expected_no_result_count": 1,
                "expected_no_result_success_count": 1,
                "expected_no_result_success_rate": 1.0,
                "unexpected_no_result_count": 0,
                "unexpected_no_result_rate": 0.0,
                "min_source_count_fail_count": 0,
                "min_source_count_pass_rate": 1.0,
                "query_type_expected_count": 4,
                "query_type_match_count": 4,
                "query_type_accuracy": 1.0,
                "source_metadata_coverage": {
                    "retrieved_source_count": 5,
                    "source_id_coverage_rate": 1.0,
                    "source_type_coverage_rate": 1.0,
                    "source_pair_coverage_rate": 1.0,
                    "metadata_pair_coverage_rate": 1.0,
                },
            },
            commit=False,
        )
        previous.created_at = utc_now() - timedelta(minutes=5)
        current = persist_retrieval_evaluation_result(
            {
                "query_count": 5,
                "recall_at_k": 0.7,
                "mrr": 0.8,
                "ndcg_at_k": 0.75,
                "keyword_query_count": 2,
                "keyword_hit_rate": 0.5,
                "permission_leak_count": 1,
                "forbidden_source_hit_count": 0,
                "no_result_count": 2,
                "no_result_rate": 0.4,
                "expected_no_result_count": 2,
                "expected_no_result_success_count": 1,
                "expected_no_result_success_rate": 0.5,
                "unexpected_no_result_count": 1,
                "unexpected_no_result_rate": 0.3333,
                "min_source_count_fail_count": 2,
                "min_source_count_pass_rate": 0.6,
                "query_type_expected_count": 4,
                "query_type_match_count": 2,
                "query_type_accuracy": 0.5,
                "source_metadata_coverage": {
                    "retrieved_source_count": 5,
                    "source_id_coverage_rate": 1.0,
                    "source_type_coverage_rate": 0.8,
                    "source_pair_coverage_rate": 0.7,
                    "metadata_pair_coverage_rate": 0.4,
                },
            },
            commit=False,
        )
        current.created_at = utc_now()
        db.session.commit()
        current_id = current.id
        previous_id = previous.id

        history = retrieval_evaluation_history(limit=5)

    regression = history["regression"]
    signal_metrics = {signal["metric"] for signal in regression["signals"]}
    assert history["latest"]["id"] == current_id
    assert history["previous"]["id"] == previous_id
    assert history["latest"]["quality_gate"]["status"] == "fail"
    assert history["latest"]["quality_gate"]["passed"] is False
    assert history["latest"]["quality_gate"]["blocking"][0]["metric"] == ("permission_leak_count")
    warning_metrics = {
        warning["metric"] for warning in history["latest"]["quality_gate"]["warnings"]
    }
    assert "recall_at_k" in warning_metrics
    assert "metadata_pair_coverage_rate" in warning_metrics
    assert regression["regressed"] is True
    assert "recall_at_k" in signal_metrics
    assert "mrr" in signal_metrics
    assert "ndcg_at_k" in signal_metrics
    assert "keyword_hit_rate" in signal_metrics
    assert "permission_leak_count" in signal_metrics
    assert "no_result_count" in signal_metrics
    assert "no_result_rate" in signal_metrics
    assert "unexpected_no_result_count" in signal_metrics
    assert "unexpected_no_result_rate" in signal_metrics
    assert "expected_no_result_success_rate" in signal_metrics
    assert "min_source_count_fail_count" in signal_metrics
    assert "min_source_count_pass_rate" in signal_metrics
    assert "query_type_accuracy" in signal_metrics
    assert "source_type_coverage_rate" in signal_metrics
    assert "source_pair_coverage_rate" in signal_metrics
    assert "metadata_pair_coverage_rate" in signal_metrics


def test_admin_retrieval_evaluation_history_endpoint_is_admin_only(
    app,
    client,
    make_user,
    auth_headers,
):
    """Verify admins can read prompt-safe retrieval evaluation history."""
    regular = make_user(username="retrieval_eval_history_user")
    admin = make_user(username="retrieval_eval_history_admin", role=Role.MASTER_ADMIN)
    with app.app_context():
        persist_retrieval_evaluation_result(
            {
                "query_count": 2,
                "recall_at_k": 0.5,
                "mrr": 0.5,
                "ndcg_at_k": 0.5,
                "keyword_query_count": 1,
                "keyword_hit_rate": 0.75,
                "permission_leak_count": 0,
                "forbidden_source_hit_count": 0,
                "no_result_count": 1,
                "no_result_rate": 0.5,
                "expected_no_result_count": 1,
                "expected_no_result_success_count": 1,
                "expected_no_result_success_rate": 1.0,
                "unexpected_no_result_count": 0,
                "unexpected_no_result_rate": 0.0,
                "query_type_expected_count": 2,
                "query_type_match_count": 1,
                "query_type_accuracy": 0.5,
                "source_metadata_coverage": {
                    "retrieved_source_count": 4,
                    "source_id_coverage_rate": 1.0,
                    "source_type_coverage_rate": 1.0,
                    "source_pair_coverage_rate": 0.75,
                    "metadata_pair_coverage_rate": 0.5,
                },
            },
        )

    forbidden_response = client.get(
        "/api/v1/admin/ai/retrieval-evaluations?limit=5",
        headers=auth_headers(regular["username"]),
    )
    admin_response = client.get(
        "/api/v1/admin/ai/retrieval-evaluations?limit=5",
        headers=auth_headers(admin["username"]),
    )
    payload = admin_response.get_json()["data"]
    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 200
    assert payload["latest"]["query_count"] == 2
    assert payload["latest"]["recall_at_k"] == 0.5
    assert payload["latest"]["keyword_query_count"] == 1
    assert payload["latest"]["keyword_hit_rate"] == 0.75
    assert payload["latest"]["no_result_rate"] == 0.5
    assert payload["latest"]["expected_no_result_success_rate"] == 1.0
    assert payload["latest"]["unexpected_no_result_count"] == 0
    assert payload["latest"]["unexpected_no_result_rate"] == 0.0
    assert payload["latest"]["query_type_expected_count"] == 2
    assert payload["latest"]["query_type_match_count"] == 1
    assert payload["latest"]["query_type_accuracy"] == 0.5
    assert payload["latest"]["source_metadata_count"] == 4
    assert payload["latest"]["source_pair_coverage_rate"] == 0.75
    assert payload["latest"]["metadata_pair_coverage_rate"] == 0.5
    assert payload["latest"]["quality_gate"]["status"] == "warning"
    assert payload["latest"]["quality_gate"]["passed"] is False
    assert payload["privacy"]["stores_query_text"] is False
    assert payload["privacy"]["stores_expected_sources"] is False
    assert payload["privacy"]["stores_expected_keywords"] is False
    assert payload["privacy"]["stores_retrieved_sources"] is False
    assert payload["privacy"]["stores_source_ids"] is False
    assert payload["privacy"]["stores_source_metadata_aggregates"] is True
    assert payload["privacy"]["source"] == "retrieval_evaluation_run_metrics"
    assert payload["unavailable"] is False


def test_admin_retrieval_evaluation_run_endpoint_persists_prompt_safe_run(
    app,
    client,
    make_user,
    auth_headers,
    set_dashboard_permission,
):
    """Verify master admins can run full golden evaluations from the API."""
    regular = make_user(username="retrieval_eval_run_user")
    admin = make_user(
        username="retrieval_eval_run_admin",
        role=Role.MASTER_ADMIN,
        department_name="Instandhaltung",
    )
    for dashboard in ("tasks", "errors", "machines", "inventory", "documents"):
        set_dashboard_permission(admin["username"], dashboard, can_view=True)
    app.config["RAG_ENABLED"] = True
    app.config["RAG_VECTOR_STORE"] = "local"

    with app.app_context():
        db_user = db.session.get(User, admin["id"])
        _seed_demo_runtime_sources(db_user)

    forbidden_response = client.post(
        "/api/v1/admin/ai/retrieval-evaluations/run",
        headers=auth_headers(regular["username"]),
        json={"limit": 5},
    )
    admin_response = client.post(
        "/api/v1/admin/ai/retrieval-evaluations/run",
        headers=auth_headers(admin["username"]),
        json={"limit": 5},
    )
    payload = admin_response.get_json()["data"]

    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 201
    assert payload["evaluation_run"]["id"]
    assert payload["quality_gate"]["status"] in {"pass", "warning", "fail"}
    assert "queries" not in payload["quality_gate"]
    assert payload["retrieval_mode"] == "full"
    assert payload["question_set"] == "demo"
    assert payload["query_count"] >= 1
    assert payload["keyword_miss_count"] >= 0
    assert payload["expected_no_result_count"] >= 0
    assert payload["unexpected_no_result_count"] >= 0
    assert 0 <= payload["unexpected_no_result_rate"] <= 1
    assert payload["query_type_expected_count"] >= 1
    assert 0 <= payload["query_type_match_count"] <= payload["query_type_expected_count"]
    assert 0 <= payload["query_type_accuracy"] <= 1
    assert payload["privacy"]["stores_query_text"] is False
    assert payload["privacy"]["stores_expected_sources"] is False
    assert payload["privacy"]["stores_expected_keywords"] is False
    assert payload["privacy"]["stores_retrieved_sources"] is False
    assert payload["privacy"]["stores_source_ids"] is False
    assert payload["privacy"]["stores_chunk_text"] is False
    assert payload["privacy"]["source"] == "retrieval_evaluation_run_metrics"
    assert payload["chunk_metadata_coverage"]["retrieved_chunk_count"] >= 0
    assert 0 <= payload["chunk_metadata_coverage"]["coverage_rate"] <= 1
    assert payload["chunk_metadata_coverage"]["block_metadata_count"] >= 0
    assert 0 <= payload["chunk_metadata_coverage"]["block_metadata_coverage_rate"] <= 1
    assert isinstance(payload["chunk_metadata_coverage"]["block_kind_distribution"], dict)
    assert payload["source_metadata_coverage"]["retrieved_source_count"] >= 0
    assert 0 <= payload["source_metadata_coverage"]["source_pair_coverage_rate"] <= 1
    assert 0 <= payload["source_metadata_coverage"]["metadata_pair_coverage_rate"] <= 1
    field_coverage = payload["source_metadata_coverage"]["field_coverage"]
    assert "source_id" in field_coverage
    assert "module" in field_coverage
    assert "role_visibility" in field_coverage
    assert "created_at" in field_coverage
    assert 0 <= field_coverage["source_id"]["coverage_rate"] <= 1
    assert "queries" not in payload

    history_response = client.get(
        "/api/v1/admin/ai/retrieval-evaluations?limit=1",
        headers=auth_headers(admin["username"]),
    )
    history_payload = history_response.get_json()["data"]
    assert history_payload["latest"]["id"] == payload["evaluation_run"]["id"]
    assert "keyword_miss_count" not in history_payload["latest"]
    assert "field_coverage" not in history_payload["latest"]


def _seed_golden_retrieval_documents(user_id):
    """Create deterministic knowledge documents for golden retrieval tests."""
    training = AssistantTrainingEntry(
        title="GEV901 Kupplungsspiel Training",
        question="Wie wird GEV901 geprueft?",
        answer="GEV901 Kupplungsspiel mit Lehre messen und Ergebnis dokumentieren.",
        keywords="GEV901, Kupplungsspiel, Training",
        department="Produktion",
        is_active=True,
        priority=90,
        created_by=user_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.session.add(training)
    db.session.flush()

    documents = {
        "filter": _create_indexed_document(
            title="GEV900 Filterdruck Upload",
            text="GEV900 Filterdruck am Messpunkt pruefen und Druckverlust notieren.",
            created_by=user_id,
        ),
        "orbit": _create_indexed_document(
            title="GEV903 Orbit Lagerwelle",
            text="GEV903 Orbit Lagerwelle reinigen und Schmierfilm kontrollieren.",
            created_by=user_id,
        ),
        "training": _create_indexed_document(
            title="GEV901 Kupplungsspiel Training",
            text="GEV901 Kupplungsspiel mit Lehre messen und Ergebnis dokumentieren.",
            created_by=user_id,
            source_type="manual_training",
            source_id=training.id,
        ),
        "foreign": _create_indexed_document(
            title="GEV902 Fremdquelle Instandhaltung",
            text="GEV902 Fremdquelle nur fuer Instandhaltung sichtbar.",
            created_by=user_id,
            department="Instandhaltung",
        ),
    }
    db.session.commit()
    source_ids = {key: document.id for key, document in documents.items()}
    source_ids["training_record"] = training.id
    return source_ids


def _seed_demo_runtime_sources(user):
    """Create enough demo-like records for the admin golden run endpoint."""
    timestamp = utc_now()
    machine = Machine(
        name="Hydraulikpresse 03",
        produced_item="Blechformteile",
        required_employees=2,
        criticality="critical",
        status="maintenance_required",
    )
    db.session.add(machine)
    db.session.flush()
    task = Task(
        title="Hydraulikpresse 03 - Dichtigkeitspruefung",
        description="Hydraulikverbindungen pruefen und Druckverlust dokumentieren.",
        priority=Priority.URGENT,
        status=TaskStatus.IN_PROGRESS,
        due_date=timestamp.date(),
        department=user.department,
        created_by=user.id,
    )
    error = ErrorEntry(
        machine="Hydraulikpresse 03",
        machine_id=machine.id,
        error_code="INS-E-103",
        title="Druck faellt ab",
        description="Hydraulikdruck faellt an Hydraulikpresse 03 ab.",
        possible_causes="Leckage, defektes Ventil oder Filter zugesetzt.",
        solution="Lecktest durchfuehren, Ventilspule messen und Filter tauschen.",
        department=user.department,
    )
    material = Machine(
        name="Spritzgussanlage 04",
        produced_item="Kunststoffclips",
        required_employees=4,
        criticality="high",
        status="running",
    )
    db.session.add_all([task, error, material])
    db.session.flush()
    db.session.add(
        InventoryMaterial(
            name="Dichtungssatz Presse",
            unit_cost=115,
            quantity=0,
            min_quantity=3,
            criticality="critical",
            machine=machine,
        )
    )
    _create_indexed_document(
        title="Betriebsanweisung Hydraulikpresse 03",
        text="Hydraulikdruckverlust: Anlage sichern, Druck abbauen und Lecktest machen.",
        created_by=user.id,
        department=user.department.name,
    )
    db.session.commit()


def _create_indexed_document(
    title,
    text,
    created_by,
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
        created_by=created_by,
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
            entities_json=json.dumps(
                {
                    "_chunk_metadata": {
                        "chunk_char_count": len(text),
                        "chunk_line_count": 1,
                        "chunk_token_count": len(text.split()),
                        "chunk_block_count": 1,
                        "chunk_block_kinds": "paragraph",
                        "chunking_mode": "hybrid_semantic",
                        "section_title": "Golden Evaluation Source",
                    }
                },
                ensure_ascii=True,
            ),
            created_at=timestamp,
        )
    )
    return document
