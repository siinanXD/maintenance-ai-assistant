"""Additional OpenAPI schema and path definitions."""

ADDITIONAL_SCHEMAS = {
    "ChatHistoryEntry": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 12},
            "user_id": {"type": "integer", "example": 3},
            "message": {"type": "string", "example": "Was ist ein User?"},
            "response": {"type": "string", "example": "Ein User ist ein Benutzerkonto."},
            "response_type": {"type": "string", "example": "general_chat"},
            "session_id": {"type": "string", "example": "chat-widget"},
            "source_count": {"type": "integer", "example": 1},
            "confidence_score": {"type": "integer", "example": 72},
            "confidence_level": {"type": "string", "example": "high"},
            "audit_event_id": {"type": "integer", "example": 44},
            "answer_quality": {"$ref": "#/components/schemas/AnswerQuality"},
            "evidence_visible": {"type": "boolean", "example": True},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
    "AnswerQuality": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "example": "grounded"},
            "status_reason": {"type": "string", "example": "sources_available"},
            "confidence_score": {"type": "integer", "nullable": True, "example": 72},
            "confidence_level": {"type": "string", "example": "high"},
            "uncertainty": {"type": "string", "example": "low"},
            "has_sources": {"type": "boolean", "example": True},
            "source_count": {"type": "integer", "example": 2},
            "no_answer": {"type": "boolean", "example": False},
            "warning_count": {"type": "integer", "example": 0},
            "warning_types": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["source_conflict"],
            },
            "primary_warning_type": {
                "type": "string",
                "example": "source_conflict",
            },
            "recommended_user_action": {
                "type": "string",
                "example": "Quellen pruefen und bei Bedarf Rueckfrage stellen.",
            },
            "evidence_visible": {"type": "boolean", "example": True},
        },
    },
    "AIChatResponse": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "example": "assistant"},
            "answer": {
                "type": "string",
                "example": "## Antwort\n- Anlage Quelle ist sichtbar.",
            },
            "sources": {
                "type": "array",
                "items": {"type": "object"},
            },
            "confidence": {"type": "object"},
            "answer_quality": {"$ref": "#/components/schemas/AnswerQuality"},
            "diagnostics": {"type": "object"},
            "chat_message_id": {"type": "integer", "example": 42},
            "evidence_visible": {
                "type": "boolean",
                "example": False,
                "description": (
                    "Present and false when answer-only chat output hides sources "
                    "and diagnostics for non-evidence users."
                ),
            },
        },
    },
    "AIAuditEvent": {
        "type": "object",
        "properties": {
            "workflow": {"type": "string", "example": "general_chat"},
            "status": {"type": "string", "example": "openai_error"},
            "error_category": {"type": "string", "example": "rate_limit"},
            "confidence_score": {"type": "integer", "example": 72},
            "confidence_level": {"type": "string", "example": "high"},
            "retrieval_explainability": {"type": "object"},
            "total_tokens": {"type": "integer", "example": 842},
            "estimated_cost_usd": {"type": "number", "example": 0.0012},
        },
    },
    "AIProviderStatus": {
        "type": "object",
        "properties": {
            "provider": {"type": "string", "example": "openai_compatible"},
            "ready": {"type": "boolean", "example": False},
            "mode": {"type": "string", "example": "openai_compatible"},
            "reason": {"type": "string", "example": "base_url_missing"},
            "effective_provider": {"type": "string", "example": "mock"},
            "fallback_active": {"type": "boolean", "example": True},
            "production_default": {"type": "boolean", "example": False},
            "configuration_action": {
                "type": "string",
                "example": "set_ai_base_url",
            },
            "recommended_action": {
                "type": "string",
                "example": ("AI_BASE_URL fuer den OpenAI-kompatiblen Endpoint setzen."),
            },
            "api_key_configured": {"type": "boolean", "example": False},
            "base_url_configured": {"type": "boolean", "example": False},
            "model_configured": {"type": "boolean", "example": True},
            "dimensions": {"type": "integer", "example": 384},
        },
    },
    "AIStatus": {
        "type": "object",
        "properties": {
            "api_key_configured": {"type": "boolean", "example": False},
            "model": {"type": "string", "example": "gpt-4o-mini"},
            "provider": {"type": "string", "example": "gemini"},
            "provider_status": {"$ref": "#/components/schemas/AIProviderStatus"},
            "provider_catalog": {
                "type": "array",
                "items": {"type": "object"},
                "example": [
                    {
                        "provider": "openai",
                        "status": "supported",
                        "mode": "external",
                        "requires_credential": True,
                        "requires_base_url": False,
                        "effective_fallback": "mock",
                    },
                    {
                        "provider": "gemini",
                        "status": "planned",
                        "mode": "unsupported",
                        "requires_credential": True,
                        "requires_base_url": False,
                        "effective_fallback": "mock",
                    },
                ],
            },
            "embedding_provider_status": {
                "$ref": "#/components/schemas/AIProviderStatus",
            },
            "embedding_provider_catalog": {
                "type": "array",
                "items": {"type": "object"},
                "example": [
                    {
                        "provider": "hashing",
                        "status": "supported",
                        "mode": "local_hashing",
                        "requires_credential": False,
                        "requires_base_url": False,
                        "effective_fallback": "hashing",
                    },
                    {
                        "provider": "openai_compatible",
                        "status": "supported",
                        "mode": "openai_compatible",
                        "requires_credential": True,
                        "requires_base_url": True,
                        "effective_fallback": "hashing",
                    },
                ],
            },
            "streaming_enabled": {"type": "boolean", "example": True},
            "ready": {"type": "boolean", "example": False},
            "readiness": {
                "type": "object",
                "properties": {
                    "ready": {"type": "boolean", "example": False},
                    "status": {"type": "string", "example": "degraded"},
                    "degraded_components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["provider"],
                    },
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["unsupported_provider"],
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "component": {
                                    "type": "string",
                                    "example": "provider",
                                },
                                "reason": {
                                    "type": "string",
                                    "example": "unsupported_provider",
                                },
                                "configuration_action": {
                                    "type": "string",
                                    "example": "select_supported_provider",
                                },
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "AI_PROVIDER auf openai, "
                                        "openai_compatible oder mock setzen."
                                    ),
                                },
                            },
                        },
                    },
                    "next_action": {
                        "type": "object",
                        "nullable": True,
                        "properties": {
                            "component": {"type": "string", "example": "provider"},
                            "reason": {
                                "type": "string",
                                "example": "unsupported_provider",
                            },
                            "configuration_action": {
                                "type": "string",
                                "example": "select_supported_provider",
                            },
                            "recommended_action": {
                                "type": "string",
                                "example": (
                                    "AI_PROVIDER auf openai, openai_compatible " "oder mock setzen."
                                ),
                            },
                        },
                    },
                },
            },
            "last_error": {
                "type": "string",
                "nullable": True,
                "example": "configuration_missing",
            },
        },
    },
    "HealthReadiness": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "example": "ok"},
            "ready": {"type": "boolean", "example": False},
            "degraded_components": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["ai"],
            },
            "components": {
                "type": "object",
                "properties": {
                    "database": {
                        "type": "object",
                        "properties": {
                            "ok": {"type": "boolean", "example": True},
                            "dialect": {"type": "string", "example": "sqlite"},
                            "driver": {"type": "string", "example": "pysqlite"},
                            "schema": {"type": "object"},
                        },
                    },
                    "ai": {
                        "type": "object",
                        "properties": {
                            "ok": {"type": "boolean", "example": False},
                            "provider": {"type": "string", "example": "gemini"},
                            "api_key_configured": {
                                "type": "boolean",
                                "example": True,
                            },
                            "mode": {"type": "string", "example": "unsupported"},
                            "reason": {
                                "type": "string",
                                "example": "unsupported_provider",
                            },
                            "effective_provider": {
                                "type": "string",
                                "example": "mock",
                            },
                            "configuration_action": {
                                "type": "string",
                                "example": "select_supported_provider",
                            },
                            "recommended_action": {
                                "type": "string",
                                "example": (
                                    "AI_PROVIDER auf openai, openai_compatible " "oder mock setzen."
                                ),
                            },
                            "base_url_configured": {
                                "type": "boolean",
                                "example": False,
                            },
                            "embedding_provider": {
                                "$ref": "#/components/schemas/AIProviderStatus",
                            },
                        },
                    },
                    "rag": {
                        "type": "object",
                        "properties": {
                            "ok": {"type": "boolean", "example": True},
                            "enabled": {"type": "boolean", "example": True},
                            "ready": {"type": "boolean", "example": True},
                            "reason": {"type": "string", "example": ""},
                            "documents": {"type": "integer", "example": 12},
                            "indexed": {"type": "integer", "example": 12},
                            "chunks": {"type": "integer", "example": 84},
                            "vector_store": {"type": "string", "example": "local"},
                            "embedding_provider": {
                                "type": "string",
                                "example": "hashing",
                            },
                        },
                    },
                },
            },
        },
    },
    "KnowledgeDocument": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 5},
            "source_type": {"type": "string", "example": "upload"},
            "title": {"type": "string", "example": "CNC Manual"},
            "status": {"type": "string", "example": "indexed"},
            "quality_status": {"type": "string", "example": "draft"},
            "last_confirmed_at": {
                "type": "string",
                "format": "date-time",
                "nullable": True,
            },
            "confirmation_count": {"type": "integer", "example": 2},
            "aging_checked_at": {
                "type": "string",
                "format": "date-time",
                "nullable": True,
            },
            "chunk_count": {"type": "integer", "example": 18},
            "department": {"type": "string", "example": "Produktion"},
        },
    },
    "MissingInformation": {
        "type": "object",
        "properties": {
            "entry_type": {"type": "string", "example": "error_entry"},
            "status": {"type": "string", "example": "needs_information"},
            "missing_fields": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["machine", "error_code", "previous_checks"],
            },
            "detected_fields": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["symptoms", "affected_area"],
            },
            "completion_ratio": {"type": "number", "example": 0.5},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "example": "machine"},
                        "label": {"type": "string", "example": "Maschine oder Anlage"},
                        "question": {
                            "type": "string",
                            "example": "Welche Maschine, Anlage oder Linie ist betroffen?",
                        },
                        "required": {"type": "boolean", "example": True},
                    },
                },
            },
            "summary": {
                "type": "string",
                "example": "Es fehlen gezielte Angaben zu: Maschine oder Anlage.",
            },
        },
    },
    "ErrorAssistantResult": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "example": "Presse 42 zeigt Fehler P42-HYD und Druckverlust.",
            },
            "matches": {"type": "array", "items": {"type": "object"}},
            "causes": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["Hydraulikfilter verschmutzt"],
            },
            "fixes": {
                "type": "array",
                "items": {"type": "string"},
                "example": ["Filter pruefen und Druck messen"],
            },
            "root_cause_analysis": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "example": ("Wahrscheinlichste Hypothese: Hydraulikfilter " "verschmutzt."),
                    },
                    "possible_causes": {"type": "array", "items": {"type": "object"}},
                    "similar_cases": {"type": "array", "items": {"type": "object"}},
                    "next_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {
                                    "type": "string",
                                    "example": "Filter pruefen und Druck messen",
                                },
                                "priority": {"type": "string", "example": "high"},
                                "source": {
                                    "type": "string",
                                    "example": "similar_case_solution",
                                },
                                "source_id": {"type": "integer", "example": 7},
                                "title": {
                                    "type": "string",
                                    "example": "Hydraulikfilter Druckverlust",
                                },
                                "error_code": {"type": "string", "example": "P42-HYD"},
                                "due_date": {"type": "string", "format": "date"},
                            },
                        },
                    },
                    "confidence": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "integer", "example": 72},
                            "level": {"type": "string", "example": "medium"},
                            "uncertainty": {"type": "string", "example": "medium"},
                            "reason": {
                                "type": "string",
                                "example": "Teilweise passende Fehlerhistorie vorhanden",
                            },
                        },
                    },
                    "insufficient_evidence": {"type": "boolean", "example": False},
                    "evidence": {
                        "type": "object",
                        "properties": {
                            "catalog_match_count": {"type": "integer", "example": 2},
                            "rag_source_count": {"type": "integer", "example": 1},
                            "uses_only_visible_sources": {
                                "type": "boolean",
                                "example": True,
                            },
                            "similar_case_sources": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "example": "error"},
                                        "error_code": {
                                            "type": "string",
                                            "example": "P42-HYD",
                                        },
                                        "machine": {
                                            "type": "string",
                                            "example": "Presse 42",
                                        },
                                        "score": {"type": "integer", "example": 81},
                                    },
                                },
                            },
                            "rag_sources": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "example": "knowledge",
                                        },
                                        "source_type": {
                                            "type": "string",
                                            "example": "machine_manual",
                                        },
                                        "source_id": {"type": "integer", "example": 12},
                                        "chunk_id": {"type": "integer", "example": 42},
                                        "title": {
                                            "type": "string",
                                            "example": "Presse 42 Hydraulikhandbuch",
                                        },
                                        "module": {
                                            "type": "string",
                                            "example": "knowledge",
                                        },
                                        "machine_id": {"type": "integer", "example": 7},
                                        "role_visibility": {
                                            "type": "string",
                                            "example": "department:Instandhaltung",
                                        },
                                        "created_at": {
                                            "type": "string",
                                            "format": "date-time",
                                            "example": "2026-05-31T10:00:00+00:00",
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "sources": {"type": "array", "items": {"type": "object"}},
            "diagnostics": {"type": "object"},
        },
    },
    "KnowledgeGap": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 3},
            "question": {"type": "string", "example": "Wie behebe ich Fehler X999?"},
            "context": {"type": "string", "example": "Quellen: 0"},
            "machine": {"type": "string", "example": "Anlage 4"},
            "department": {"type": "string", "example": "Instandhaltung"},
            "status": {"type": "string", "example": "open"},
            "occurrence_count": {"type": "integer", "example": 2},
            "last_seen_at": {"type": "string", "format": "date-time"},
        },
    },
    "KnowledgeNetwork": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "example": "machine:1"},
                        "type": {"type": "string", "example": "machine"},
                        "label": {"type": "string", "example": "Anlage 4"},
                        "title": {"type": "string", "example": "Anlage 4"},
                        "url": {"type": "string", "example": "/machines"},
                        "weight": {"type": "number", "example": 12.5},
                        "evidence_count": {"type": "integer", "example": 3},
                        "metadata": {"type": "object"},
                        "explainability": {"type": "object"},
                    },
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "example": "document-1-machine-1"},
                        "source": {"type": "string", "example": "document:1"},
                        "target": {"type": "string", "example": "machine:1"},
                        "type": {"type": "string", "example": "source_relation"},
                        "label": {"type": "string", "example": "direct source"},
                        "weight": {"type": "number", "example": 9.0},
                        "evidence_count": {"type": "integer", "example": 1},
                        "explainability": {"type": "object"},
                    },
                },
            },
            "stats": {"type": "object"},
            "filters": {"type": "object"},
            "explainability": {"type": "object"},
            "privacy": {
                "type": "object",
                "example": {"mode": "metadata_only", "omitted": ["chunk_text"]},
            },
        },
    },
    "RetrievalDebug": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chat_message_id": {"type": "integer", "example": 12},
                        "audit_event_id": {"type": "integer", "example": 44},
                        "user_question": {"type": "string", "example": "Warum F-900?"},
                        "query_type": {"type": "string", "example": "error_analysis"},
                        "used_sources": {"type": "array", "items": {"type": "object"}},
                        "confidence": {"type": "object"},
                        "conflicts": {"type": "object"},
                        "safety": {"type": "object"},
                        "retrieval_duration_ms": {"type": "integer", "example": 42},
                    },
                },
            },
            "privacy": {"type": "object"},
        },
    },
    "RetrievalTelemetry": {
        "type": "object",
        "properties": {
            "window_days": {"type": "integer", "example": 30},
            "event_overview": {"type": "object"},
            "source_usage": {"type": "object"},
            "poor_sources": {"type": "array", "items": {"type": "object"}},
            "unsuccessful_questions": {"type": "object"},
            "reranking": {"type": "object"},
            "negative_feedback": {"type": "object"},
            "knowledge_gaps": {"type": "object"},
            "unused_chunks": {
                "type": "object",
                "properties": {
                    "total": {"type": "integer", "example": 7},
                    "referenced_chunk_count": {"type": "integer", "example": 12},
                    "chunk_size_metrics": {
                        "type": "object",
                        "properties": {
                            "measured_chunk_count": {
                                "type": "integer",
                                "example": 7,
                            },
                            "average_char_count": {
                                "type": "number",
                                "example": 840.5,
                            },
                            "average_token_count": {
                                "type": "number",
                                "example": 116,
                            },
                            "average_block_count": {
                                "type": "number",
                                "example": 2,
                            },
                            "max_block_count": {
                                "type": "integer",
                                "example": 4,
                            },
                            "block_kind_distribution": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "key": {
                                            "type": "string",
                                            "example": "list",
                                        },
                                        "count": {
                                            "type": "integer",
                                            "example": 3,
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "sample": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "chunk_id": {"type": "integer", "example": 42},
                                "document_id": {"type": "integer", "example": 9},
                                "chunk_index": {"type": "integer", "example": 0},
                                "chunk_block_count": {
                                    "type": "integer",
                                    "nullable": True,
                                    "example": 2,
                                },
                                "chunk_block_kinds": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "example": ["list", "paragraph"],
                                },
                                "chunking_mode": {
                                    "type": "string",
                                    "example": "hybrid_semantic",
                                },
                                "section_title": {
                                    "type": "string",
                                    "example": "Wartungsschritte",
                                },
                                "document_title": {
                                    "type": "string",
                                    "example": "Presse 42 Wartung",
                                },
                            },
                        },
                    },
                },
            },
            "privacy": {
                "type": "object",
                "example": {
                    "raw_questions_visible": False,
                    "raw_chunk_text_visible": False,
                    "source_metadata_visible": True,
                },
            },
        },
    },
    "RetrievalEvaluationRunResult": {
        "type": "object",
        "properties": {
            "query_count": {"type": "integer", "example": 12},
            "metric_query_count": {"type": "integer", "example": 8},
            "recall_at_k": {"type": "number", "example": 0.83},
            "mrr": {"type": "number", "example": 0.72},
            "ndcg_at_k": {"type": "number", "example": 0.78},
            "keyword_hit_rate": {"type": "number", "example": 0.75},
            "keyword_query_count": {"type": "integer", "example": 6},
            "keyword_miss_count": {"type": "integer", "example": 2},
            "permission_leak_count": {"type": "integer", "example": 0},
            "forbidden_source_hit_count": {"type": "integer", "example": 0},
            "no_result_count": {"type": "integer", "example": 1},
            "no_result_rate": {"type": "number", "example": 0.08},
            "expected_no_result_count": {"type": "integer", "example": 1},
            "expected_no_result_success_count": {"type": "integer", "example": 1},
            "expected_no_result_success_rate": {"type": "number", "example": 1.0},
            "unexpected_no_result_count": {"type": "integer", "example": 0},
            "unexpected_no_result_rate": {"type": "number", "example": 0.0},
            "min_source_count_fail_count": {"type": "integer", "example": 1},
            "min_source_count_pass_rate": {"type": "number", "example": 0.92},
            "query_type_expected_count": {"type": "integer", "example": 6},
            "query_type_match_count": {"type": "integer", "example": 5},
            "query_type_accuracy": {"type": "number", "example": 0.8333},
            "chunk_metadata_coverage": {
                "type": "object",
                "properties": {
                    "retrieved_chunk_count": {"type": "integer", "example": 8},
                    "measured_chunk_count": {"type": "integer", "example": 8},
                    "coverage_rate": {"type": "number", "example": 1.0},
                    "average_char_count": {"type": "number", "example": 842.5},
                    "average_token_count": {"type": "number", "example": 118.0},
                    "block_metadata_count": {"type": "integer", "example": 8},
                    "block_metadata_coverage_rate": {
                        "type": "number",
                        "example": 1.0,
                    },
                    "average_block_count": {"type": "number", "example": 2.0},
                    "block_kind_distribution": {
                        "type": "object",
                        "example": {"paragraph": 6, "list": 2},
                    },
                },
            },
            "source_metadata_coverage": {"type": "object"},
            "quality_gate": {
                "type": "object",
                "example": {
                    "status": "warning",
                    "passed": False,
                    "blocking": [],
                    "warnings": [
                        {
                            "metric": "recall_at_k",
                            "value": 0.7,
                            "threshold": 0.75,
                            "reason": "expected_sources_not_recalled",
                        },
                    ],
                },
            },
            "evaluation_run": {"type": "object"},
            "question_set": {"type": "string", "example": "demo"},
            "retrieval_mode": {"type": "string", "example": "full"},
            "privacy": {
                "type": "object",
                "example": {
                    "stores_query_text": False,
                    "stores_expected_sources": False,
                    "stores_expected_keywords": False,
                    "stores_retrieved_sources": False,
                    "stores_source_ids": False,
                    "stores_chunk_text": False,
                },
            },
        },
    },
    "TaskPrioritySuggestion": {
        "type": "object",
        "properties": {
            "task": {"type": "object"},
            "score": {"type": "integer", "example": 87},
            "risk_level": {"type": "string", "example": "high"},
            "reason": {
                "type": "string",
                "example": "Ueberfaellig und relevante Stoerhistorie vorhanden.",
            },
            "recommended_action": {
                "type": "string",
                "example": "Hydraulikfilter priorisiert pruefen.",
            },
            "confidence": {
                "type": "object",
                "properties": {
                    "score": {"type": "integer", "example": 78},
                    "level": {"type": "string", "example": "high"},
                    "uncertainty": {"type": "string", "example": "low"},
                    "reason": {
                        "type": "string",
                        "example": (
                            "Fehlerhistorie und Wartungsberichte stuetzen die " "Priorisierung."
                        ),
                    },
                    "uses_only_visible_sources": {
                        "type": "boolean",
                        "example": True,
                    },
                },
            },
            "next_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "example": "review_related_errors"},
                        "title": {"type": "string", "example": "Fehlerhistorie pruefen"},
                        "detail": {
                            "type": "string",
                            "example": (
                                "Sichtbare verwandte Fehler auf Ursache, "
                                "Wiederholung und Stillstand auswerten."
                            ),
                        },
                        "source_type": {"type": "string", "example": "error"},
                        "urgency": {"type": "string", "example": "high"},
                    },
                },
            },
            "evidence_counts": {
                "type": "object",
                "properties": {
                    "maintenance_reports": {"type": "integer", "example": 1},
                    "related_errors": {"type": "integer", "example": 2},
                    "recent_related_errors": {"type": "integer", "example": 1},
                    "machines": {"type": "integer", "example": 1},
                    "risk_signals": {"type": "integer", "example": 3},
                    "blocked": {"type": "boolean", "example": False},
                    "reopened_count": {"type": "integer", "example": 0},
                    "uses_only_visible_sources": {
                        "type": "boolean",
                        "example": True,
                    },
                },
            },
            "evidence_references": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "example": "error"},
                        "id": {"type": "integer", "example": 22},
                        "title": {
                            "type": "string",
                            "example": "Hydraulikdruck faellt ab",
                        },
                        "machine": {"type": "string", "example": "Presse 9"},
                        "machine_id": {"type": "integer", "nullable": True},
                        "role_visibility": {
                            "type": "string",
                            "example": "department:Instandhaltung",
                        },
                        "created_at": {
                            "type": "string",
                            "format": "date-time",
                            "example": "2026-05-31T10:00:00+00:00",
                        },
                        "due_date": {
                            "type": "string",
                            "format": "date",
                            "example": "2026-06-05",
                        },
                        "error_code": {"type": "string", "example": "HY-9"},
                        "shift_date": {
                            "type": "string",
                            "format": "date",
                            "example": "2026-05-31",
                        },
                    },
                },
            },
        },
    },
    "MaintenanceRecommendationLight": {
        "type": "object",
        "properties": {
            "machine": {"type": "object"},
            "score": {"type": "integer", "example": 82},
            "confidence": {"type": "integer", "example": 74},
            "confidence_level": {"type": "string", "example": "medium"},
            "confidence_uncertainty": {"type": "string", "example": "medium"},
            "confidence_reason": {
                "type": "string",
                "example": "Mehrere sichtbare Wartungssignale vorhanden.",
            },
            "recommendation_type": {
                "type": "string",
                "example": "maintenance_recommendation_light",
            },
            "risk_level": {"type": "string", "example": "high"},
            "reason": {
                "type": "string",
                "example": (
                    "2 sichtbare Tasks, 1 Fehler, 1 Wartungsbericht und "
                    "1 Wartungsplan deuten auf wiederkehrende Themen hin."
                ),
            },
            "recommended_action": {
                "type": "string",
                "example": "Wartungsplan pruefen und Inspektionsintervall festlegen.",
            },
            "next_steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "example": "error_history_review"},
                        "title": {"type": "string", "example": "Fehlerhistorie buendeln"},
                        "detail": {
                            "type": "string",
                            "example": (
                                "Sichtbare Fehler auf gemeinsame Ursachen und "
                                "Ersatzteilbedarf pruefen."
                            ),
                        },
                        "source_type": {"type": "string", "example": "error"},
                        "urgency": {"type": "string", "example": "high"},
                    },
                },
            },
            "source_counts": {
                "type": "object",
                "properties": {
                    "tasks": {"type": "integer", "example": 2},
                    "errors": {"type": "integer", "example": 1},
                    "maintenance_reports": {"type": "integer", "example": 1},
                    "maintenance_plans": {"type": "integer", "example": 1},
                    "shift_handovers": {"type": "integer", "example": 1},
                    "rag_sources": {"type": "integer", "example": 2},
                    "recurring_issues": {"type": "integer", "example": 0},
                },
            },
            "evidence_summary": {
                "type": "object",
                "properties": {
                    "uses_only_visible_sources": {
                        "type": "boolean",
                        "example": True,
                    },
                    "source_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": [
                            "error",
                            "maintenance_plan",
                            "maintenance_report",
                            "rag_source",
                            "shift_handover",
                            "task",
                        ],
                    },
                    "direct_source_count": {"type": "integer", "example": 5},
                    "rag_source_count": {"type": "integer", "example": 2},
                    "rag_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "example": "knowledge"},
                                "id": {"type": "integer", "example": 12},
                                "source_type": {
                                    "type": "string",
                                    "example": "maintenance_plan",
                                },
                                "source_id": {"type": "integer", "example": 7},
                                "chunk_id": {"type": "integer", "example": 42},
                                "title": {
                                    "type": "string",
                                    "example": "Hydraulik Preventive Wartung",
                                },
                                "module": {
                                    "type": "string",
                                    "example": "knowledge",
                                },
                                "machine_id": {"type": "integer", "example": 5},
                                "role_visibility": {
                                    "type": "string",
                                    "example": "department:Instandhaltung",
                                },
                                "created_at": {
                                    "type": "string",
                                    "format": "date-time",
                                    "example": "2026-05-31T10:00:00+00:00",
                                },
                                "score": {"type": "integer", "example": 74},
                            },
                        },
                    },
                    "recurring_issue_window_days": {"type": "integer", "example": 30},
                    "latest_signal_at": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "predictive_claim": {"type": "boolean", "example": False},
                },
            },
            "evidence": {"type": "array", "items": {"type": "object"}},
            "sources": {"type": "array", "items": {"type": "object"}},
            "recurring_issue": {"type": "object", "nullable": True},
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "limitations": {
                "type": "array",
                "items": {"type": "string"},
                "example": [
                    (
                        "Keine Prognose von Ausfallzeit, Restlebensdauer "
                        "oder Ausfallwahrscheinlichkeit."
                    )
                ],
            },
        },
    },
    "MaintenanceRecommendationLightResponse": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/MaintenanceRecommendationLight"},
            },
            "count": {"type": "integer", "example": 3},
            "total_candidates": {"type": "integer", "example": 5},
            "recommendation_type": {
                "type": "string",
                "example": "maintenance_recommendation_light",
            },
            "disclaimer": {
                "type": "string",
                "example": (
                    "Heuristische Empfehlung aus sichtbaren Fehlern, Wartungen, "
                    "Tasks und RAG-Quellen; keine Predictive-Maintenance-Prognose."
                ),
            },
            "recurring_issues": {"type": "object"},
        },
    },
    "ShiftHandoverSummary": {
        "type": "object",
        "properties": {
            "handover": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "example": 42},
                    "department": {"type": "string", "example": "Produktion"},
                    "area": {"type": "string", "example": "Linie 2"},
                    "machine_id": {"type": "integer", "nullable": True},
                    "machine": {"type": "string", "example": "Handover Presse"},
                    "shift_date": {"type": "string", "format": "date"},
                    "shift_type": {"type": "string", "example": "Spaet"},
                    "status": {"type": "string", "example": "open"},
                },
            },
            "summary": {
                "type": "string",
                "example": (
                    "Spaet-Uebergabe 2026-07-04 fuer Handover Presse: "
                    "3 kritische Punkte fuer die naechste Schicht."
                ),
            },
            "critical_points": {"type": "array", "items": {"type": "object"}},
            "next_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "example": "task"},
                        "source_id": {"type": "integer", "example": 18},
                        "title": {
                            "type": "string",
                            "example": "Hydraulikdruck pruefen",
                        },
                        "text": {
                            "type": "string",
                            "example": ("Hydraulikdruck pruefen bis 2026-07-04 bearbeiten."),
                        },
                        "priority": {"type": "string", "example": "high"},
                        "due_date": {"type": "string", "format": "date"},
                        "error_code": {"type": "string", "example": "HO-77"},
                    },
                },
            },
            "open_tasks": {"type": "array", "items": {"type": "object"}},
            "disruptions": {"type": "array", "items": {"type": "object"}},
            "maintenance_plans": {"type": "array", "items": {"type": "object"}},
            "confidence": {
                "type": "object",
                "properties": {
                    "score": {"type": "integer", "example": 76},
                    "level": {"type": "string", "example": "high"},
                    "uncertainty": {"type": "string", "example": "low"},
                    "reason": {
                        "type": "string",
                        "example": (
                            "Basiert auf Handover-Feldern, sichtbaren "
                            "offenen Tasks und Stoerungen."
                        ),
                    },
                },
            },
            "source_counts": {
                "type": "object",
                "properties": {
                    "handover_fields": {"type": "integer", "example": 4},
                    "open_tasks": {"type": "integer", "example": 1},
                    "disruptions": {"type": "integer", "example": 1},
                    "maintenance_plans": {"type": "integer", "example": 1},
                    "uses_only_visible_sources": {
                        "type": "boolean",
                        "example": True,
                    },
                },
            },
            "evidence_summary": {
                "type": "object",
                "properties": {
                    "workflow": {
                        "type": "string",
                        "example": "shift_handover_summary",
                    },
                    "provider": {"type": "string", "example": "local_rules"},
                    "uses_only_visible_sources": {
                        "type": "boolean",
                        "example": True,
                    },
                    "source_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": [
                            "error",
                            "maintenance_plan",
                            "shift_handover",
                            "task",
                        ],
                    },
                    "direct_source_count": {"type": "integer", "example": 6},
                    "has_open_task_context": {
                        "type": "boolean",
                        "example": True,
                    },
                    "has_disruption_context": {
                        "type": "boolean",
                        "example": True,
                    },
                    "has_maintenance_plan_context": {
                        "type": "boolean",
                        "example": True,
                    },
                    "source_references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "example": "task"},
                                "id": {"type": "integer", "example": 18},
                                "title": {
                                    "type": "string",
                                    "example": "Hydraulikdruck pruefen",
                                },
                                "machine": {
                                    "type": "string",
                                    "example": "Handover Presse",
                                },
                                "machine_id": {"type": "integer", "example": 5},
                                "role_visibility": {
                                    "type": "string",
                                    "example": "department:Produktion",
                                },
                                "created_at": {
                                    "type": "string",
                                    "format": "date-time",
                                    "example": "2026-05-31T10:00:00+00:00",
                                },
                                "due_date": {
                                    "type": "string",
                                    "format": "date",
                                    "example": "2026-07-04",
                                },
                                "error_code": {
                                    "type": "string",
                                    "example": "HO-77",
                                },
                            },
                        },
                    },
                    "scopes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["handover", "tasks", "errors", "machines"],
                    },
                    "latest_signal_at": {
                        "type": "string",
                        "format": "date-time",
                    },
                    "llm_call": {"type": "boolean", "example": False},
                },
            },
            "diagnostics": {"type": "object"},
        },
    },
    "AIObservability": {
        "type": "object",
        "properties": {
            "window_days": {"type": "integer", "example": 30},
            "provider_readiness": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string", "example": "gemini"},
                    "api_key_configured": {"type": "boolean", "example": True},
                    "provider_status": {
                        "$ref": "#/components/schemas/AIProviderStatus",
                    },
                    "embedding_provider_status": {
                        "$ref": "#/components/schemas/AIProviderStatus",
                    },
                    "ready": {"type": "boolean", "example": False},
                    "readiness": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "example": "degraded"},
                            "degraded_components": {
                                "type": "array",
                                "items": {"type": "string"},
                                "example": ["provider"],
                            },
                            "next_action": {
                                "type": "object",
                                "nullable": True,
                                "properties": {
                                    "component": {
                                        "type": "string",
                                        "example": "provider",
                                    },
                                    "configuration_action": {
                                        "type": "string",
                                        "example": "select_supported_provider",
                                    },
                                    "recommended_action": {
                                        "type": "string",
                                        "example": (
                                            "AI_PROVIDER auf openai, "
                                            "openai_compatible oder mock setzen."
                                        ),
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "metrics": {
                "type": "object",
                "properties": {
                    "total_requests": {"type": "integer", "example": 42},
                    "successful_requests": {"type": "integer", "example": 39},
                    "failed_requests": {"type": "integer", "example": 3},
                    "request_success_rate": {"type": "number", "example": 0.9286},
                    "frequent_questions": {"type": "array", "items": {"type": "object"}},
                    "frequent_search_terms": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "average_final_top_k": {"type": "number", "example": 4},
                    "average_tokens": {"type": "number", "example": 640},
                    "token_usage": {
                        "type": "object",
                        "properties": {
                            "input_tokens": {"type": "integer", "example": 12000},
                            "output_tokens": {"type": "integer", "example": 4800},
                            "cached_tokens": {"type": "integer", "example": 900},
                            "total_tokens": {"type": "integer", "example": 16800},
                            "average_tokens": {"type": "number", "example": 400},
                            "cache_rate": {"type": "number", "example": 0.075},
                        },
                    },
                    "cost_windows": {"type": "object"},
                    "costs": {
                        "type": "object",
                        "properties": {
                            "day": {"type": "number", "example": 0.12},
                            "week": {"type": "number", "example": 0.64},
                            "month": {"type": "number", "example": 2.31},
                            "estimated_cost_usd": {"type": "number", "example": 2.31},
                            "cost_per_1k_tokens": {"type": "number", "example": 0.1375},
                        },
                    },
                    "governance_status": {"type": "string", "example": "warning"},
                    "governance_alert_count": {"type": "integer", "example": 2},
                    "governance_critical_alert_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "governance_warning_alert_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "provider_ready": {"type": "boolean", "example": False},
                    "provider_readiness_status": {
                        "type": "string",
                        "example": "degraded",
                    },
                    "provider_degraded_component_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "provider_next_action_type": {
                        "type": "string",
                        "example": "select_supported_provider",
                    },
                    "p95_response_ms": {"type": "number", "example": 850},
                    "p95_retrieval_ms": {"type": "number", "example": 120},
                    "atlas_queries": {"type": "integer", "example": 24},
                    "atlas_errors": {"type": "integer", "example": 1},
                    "atlas_latency": {"type": "number", "example": 35.5},
                    "atlas_fallbacks": {"type": "integer", "example": 1},
                    "atlas_sync_failures": {"type": "integer", "example": 1},
                    "atlas_vector_count": {"type": "integer", "example": 1280},
                    "atlas_reindex_required": {"type": "boolean", "example": True},
                    "latency": {
                        "type": "object",
                        "properties": {
                            "average_response_ms": {"type": "number", "example": 420},
                            "p95_response_ms": {"type": "number", "example": 850},
                            "average_retrieval_ms": {"type": "number", "example": 80},
                            "p95_retrieval_ms": {"type": "number", "example": 120},
                        },
                    },
                    "failed_request_count": {"type": "integer", "example": 1},
                    "retrieval_hit_rate": {"type": "number", "example": 0.92},
                    "source_freshness": {
                        "type": "object",
                        "example": {
                            "stale_threshold_days": 180,
                            "measured_source_count": 12,
                            "undated_source_count": 1,
                            "average_source_age_days": 42.5,
                            "oldest_source_age_days": 365,
                            "stale_source_count": 2,
                            "stale_source_rate": 0.1667,
                        },
                    },
                    "stale_source_count": {"type": "integer", "example": 2},
                    "stale_source_rate": {"type": "number", "example": 0.1667},
                    "undated_source_count": {"type": "integer", "example": 1},
                    "retrieval_action_count": {"type": "integer", "example": 3},
                    "retrieval_critical_action_count": {
                        "type": "integer",
                        "example": 0,
                    },
                    "retrieval_high_action_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "evaluation_action_count": {"type": "integer", "example": 4},
                    "evaluation_critical_action_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "evaluation_high_action_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "evaluation_quality_gate_status": {
                        "type": "string",
                        "example": "fail",
                    },
                    "evaluation_quality_gate_passed": {
                        "type": "boolean",
                        "example": False,
                    },
                    "evaluation_quality_gate_issue_count": {
                        "type": "integer",
                        "example": 3,
                    },
                    "evaluation_blocking_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "evaluation_warning_count": {
                        "type": "integer",
                        "example": 2,
                    },
                    "source_metadata_gap_count": {
                        "type": "integer",
                        "example": 2,
                    },
                    "source_metadata_gap_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["source_pair", "metadata_pair"],
                    },
                    "source_metadata_min_coverage_rate": {
                        "type": "number",
                        "nullable": True,
                        "example": 0.5,
                    },
                    "no_answer_rate": {"type": "number", "example": 0.08},
                    "no_source_answers": {"type": "integer", "example": 3},
                    "no_source_answer_rate": {"type": "number", "example": 0.12},
                    "low_confidence_answers": {"type": "integer", "example": 4},
                    "low_confidence_rate": {"type": "number", "example": 0.16},
                    "source_conflict_count": {"type": "integer", "example": 1},
                    "source_conflict_rate": {"type": "number", "example": 0.04},
                    "answer_quality_distribution": {
                        "type": "object",
                        "example": {
                            "grounded": 12,
                            "no_answer": 2,
                            "conflicting_sources": 1,
                        },
                    },
                    "answer_quality_distribution_rows": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "answer_quality_reason_distribution": {
                        "type": "object",
                        "example": {
                            "sources_available": 12,
                            "empty_retrieval_hallucination_guard": 2,
                            "source_conflict_detected": 1,
                        },
                    },
                    "answer_quality_reason_distribution_rows": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "answer_quality_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "example": "review_no_answer_guarded_questions",
                                },
                                "priority": {"type": "string", "example": "high"},
                                "target": {
                                    "type": "string",
                                    "example": "empty_retrieval_hallucination_guard",
                                },
                                "count": {"type": "integer", "example": 2},
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "Knowledge Gaps, fehlende Dokumente und "
                                        "Retrieval-Filter fuer diese Fragen pruefen."
                                    ),
                                },
                            },
                        },
                    },
                    "answer_quality_action_count": {
                        "type": "integer",
                        "example": 2,
                    },
                    "answer_quality_action_summary": {
                        "type": "object",
                        "properties": {
                            "total": {"type": "integer", "example": 2},
                            "high_priority_count": {"type": "integer", "example": 1},
                            "next_action_type": {
                                "type": "string",
                                "example": "review_no_answer_guarded_questions",
                            },
                        },
                    },
                    "primary_warning_distribution": {
                        "type": "object",
                        "example": {
                            "none": 12,
                            "source_conflict": 1,
                            "hallucination_risk": 2,
                        },
                    },
                    "primary_warning_distribution_rows": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "uncertainty_distribution": {
                        "type": "object",
                        "example": {
                            "low": 12,
                            "medium": 3,
                            "high": 2,
                        },
                    },
                    "uncertainty_distribution_rows": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "high_uncertainty_count": {"type": "integer", "example": 2},
                    "high_uncertainty_rate": {"type": "number", "example": 0.08},
                    "uncertain_answer_count": {"type": "integer", "example": 5},
                    "uncertain_answer_rate": {"type": "number", "example": 0.2},
                    "feedback": {"type": "object"},
                    "most_used_documents": {"type": "array", "items": {"type": "object"}},
                    "knowledge_gaps": {
                        "type": "object",
                        "properties": {
                            "open_count": {"type": "integer", "example": 4},
                            "recurring_count": {"type": "integer", "example": 2},
                            "machine_gap_count": {"type": "integer", "example": 1},
                            "error_gap_count": {"type": "integer", "example": 1},
                            "uncovered_error_gap_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "critical_uncovered_error_gap_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "uncovered_machine_gap_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "critical_uncovered_machine_gap_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "department_gap_count": {"type": "integer", "example": 1},
                            "uncertain_question_gap_count": {
                                "type": "integer",
                                "example": 2,
                            },
                            "high_uncertainty_answer_count": {
                                "type": "integer",
                                "example": 5,
                            },
                            "uncertain_question_gaps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "question": {
                                            "type": "string",
                                            "example": ("Welche Ursache hat Fehler X999?"),
                                        },
                                        "count": {"type": "integer", "example": 3},
                                        "no_answer_count": {
                                            "type": "integer",
                                            "example": 2,
                                        },
                                        "average_confidence": {
                                            "type": "number",
                                            "nullable": True,
                                            "example": 18,
                                        },
                                        "answer_uncertainty": {
                                            "type": "string",
                                            "example": "high",
                                        },
                                        "knowledge_gap_id": {
                                            "type": "integer",
                                            "nullable": True,
                                            "example": 321,
                                        },
                                    },
                                },
                            },
                            "uncertain_question_action_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "uncertain_question_actions": {
                                "type": "array",
                                "items": {"type": "object"},
                                "example": [
                                    {
                                        "type": "review_uncertain_answer_gap",
                                        "priority": "high",
                                        "target_type": "ai_question",
                                        "target": "Welche Ursache hat Fehler X999?",
                                    }
                                ],
                            },
                            "machine_gaps": {"type": "array", "items": {"type": "object"}},
                            "uncovered_machine_gaps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "machine": {
                                            "type": "string",
                                            "example": "Presse 42",
                                        },
                                        "criticality": {
                                            "type": "string",
                                            "example": "critical",
                                        },
                                        "status": {
                                            "type": "string",
                                            "example": "offline",
                                        },
                                        "priority": {
                                            "type": "string",
                                            "example": "high",
                                        },
                                        "reason": {
                                            "type": "string",
                                            "example": (
                                                "Kritikalitaet critical, aber keine "
                                                "maschinenspezifische Knowledge-Quelle gefunden."
                                            ),
                                        },
                                    },
                                },
                            },
                            "error_gaps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "error_code": {
                                            "type": "string",
                                            "example": "P42-HYD",
                                        },
                                        "machine": {
                                            "type": "string",
                                            "example": "Presse 42",
                                        },
                                        "coverage": {
                                            "type": "string",
                                            "example": "missing",
                                        },
                                        "open_gap_count": {
                                            "type": "integer",
                                            "example": 2,
                                        },
                                    },
                                },
                            },
                            "uncovered_error_gaps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "error_code": {
                                            "type": "string",
                                            "example": "P42-HYD",
                                        },
                                        "machine": {
                                            "type": "string",
                                            "example": "Presse 42",
                                        },
                                        "priority": {
                                            "type": "string",
                                            "example": "high",
                                        },
                                        "reason": {
                                            "type": "string",
                                            "example": (
                                                "Schweregrad high, aber kein passendes "
                                                "Fehler-Knowledge-Dokument gefunden."
                                            ),
                                        },
                                    },
                                },
                            },
                            "department_gaps": {"type": "array", "items": {"type": "object"}},
                            "action_count": {"type": "integer", "example": 3},
                            "high_priority_action_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "action_priority_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                                "example": [{"key": "high", "count": 1}],
                            },
                            "action_type_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                                "example": [
                                    {
                                        "key": "missing_error_documentation",
                                        "count": 1,
                                    }
                                ],
                            },
                            "recommended_actions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "example": "missing_error_documentation",
                                        },
                                        "priority": {
                                            "type": "string",
                                            "example": "high",
                                        },
                                        "target_type": {
                                            "type": "string",
                                            "example": "error_entry",
                                        },
                                        "target_id": {
                                            "type": "integer",
                                            "nullable": True,
                                            "example": 42,
                                        },
                                        "target": {
                                            "type": "string",
                                            "example": "P42-HYD",
                                        },
                                        "machine": {
                                            "type": "string",
                                            "example": "Presse 42",
                                        },
                                        "title": {
                                            "type": "string",
                                            "example": "Hydraulikdruck faellt ab",
                                        },
                                        "reason": {
                                            "type": "string",
                                            "example": (
                                                "2 offene Gap(s), 0 passende Fehlerdokumente"
                                            ),
                                        },
                                        "recommended_action": {
                                            "type": "string",
                                            "example": (
                                                "Fehlercode, Ursachen und bestaetigte "
                                                "Loesung dokumentieren."
                                            ),
                                        },
                                        "next_steps": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "example": [
                                                (
                                                    "Fehler P42-HYD mit bestaetigter "
                                                    "Ursache dokumentieren."
                                                )
                                            ],
                                        },
                                        "success_criteria": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "example": [
                                                (
                                                    "RAG-Antwort nennt Ursache, "
                                                    "naechste Schritte und Quelle."
                                                )
                                            ],
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "retrieval_monitoring": {
                "type": "object",
                "properties": {
                    "top_hits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_type": {
                                    "type": "string",
                                    "example": "knowledge",
                                },
                                "source_id": {"type": "integer", "example": 12},
                                "source_record_id": {
                                    "type": "integer",
                                    "nullable": True,
                                    "example": 123,
                                },
                                "title": {
                                    "type": "string",
                                    "example": "Presse 42 Hydraulikhandbuch",
                                },
                                "module": {"type": "string", "example": "knowledge"},
                                "machine_id": {"type": "integer", "example": 42},
                                "role_visibility": {
                                    "type": "string",
                                    "example": "department:Instandhaltung",
                                },
                                "source_created_at": {
                                    "type": "string",
                                    "format": "date-time",
                                },
                                "source_age_days": {
                                    "type": "integer",
                                    "example": 365,
                                },
                                "retrieved_at": {
                                    "type": "string",
                                    "format": "date-time",
                                },
                            },
                        },
                    },
                    "poor_hits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_type": {
                                    "type": "string",
                                    "example": "knowledge",
                                },
                                "source_id": {"type": "integer", "example": 12},
                                "title": {
                                    "type": "string",
                                    "example": "Presse 42 Hydraulikhandbuch",
                                },
                                "score": {"type": "number", "example": 28},
                                "similarity": {"type": "number", "example": 0.31},
                            },
                        },
                    },
                    "score_summary": {"type": "object"},
                    "retrieval_quality_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "example": "review_low_quality_retrieval_hits",
                                },
                                "priority": {
                                    "type": "string",
                                    "example": "high",
                                },
                                "target_type": {
                                    "type": "string",
                                    "example": "retrieval_quality",
                                },
                                "target": {
                                    "type": "string",
                                    "example": "poor_hits",
                                },
                                "count": {"type": "integer", "example": 4},
                                "low_score_count": {"type": "integer", "example": 2},
                                "low_similarity_count": {
                                    "type": "integer",
                                    "example": 1,
                                },
                                "sample_sources": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                },
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "Schlechte Treffer pruefen, Chunk-Zuschnitt "
                                        "und Metadaten verbessern."
                                    ),
                                },
                                "next_steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "success_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "stale_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_type": {
                                    "type": "string",
                                    "example": "knowledge",
                                },
                                "source_id": {"type": "integer", "example": 12},
                                "title": {
                                    "type": "string",
                                    "example": "Presse 42 Hydraulikhandbuch",
                                },
                                "source_created_at": {
                                    "type": "string",
                                    "format": "date-time",
                                },
                                "source_age_days": {
                                    "type": "integer",
                                    "example": 365,
                                },
                                "stale_threshold_days": {
                                    "type": "integer",
                                    "example": 180,
                                },
                                "retrieved_at": {
                                    "type": "string",
                                    "format": "date-time",
                                },
                            },
                        },
                    },
                    "undated_sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_type": {
                                    "type": "string",
                                    "example": "knowledge",
                                },
                                "source_id": {"type": "integer", "example": 12},
                                "source_record_id": {
                                    "type": "integer",
                                    "nullable": True,
                                    "example": 124,
                                },
                                "title": {
                                    "type": "string",
                                    "example": "Presse 42 Wartungsnotiz ohne Datum",
                                },
                                "source_created_at": {
                                    "type": "string",
                                    "nullable": True,
                                    "example": "",
                                },
                                "source_age_days": {
                                    "type": "integer",
                                    "nullable": True,
                                    "example": None,
                                },
                                "retrieved_at": {
                                    "type": "string",
                                    "format": "date-time",
                                },
                            },
                        },
                    },
                    "metadata_quality_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "example": "complete_source_dates",
                                },
                                "priority": {
                                    "type": "string",
                                    "example": "medium",
                                },
                                "target_type": {
                                    "type": "string",
                                    "example": "retrieval_source_metadata",
                                },
                                "target": {
                                    "type": "string",
                                    "example": "undated_sources",
                                },
                                "count": {"type": "integer", "example": 3},
                                "stale_threshold_days": {
                                    "type": "integer",
                                    "nullable": True,
                                    "example": 180,
                                },
                                "sample_sources": {
                                    "type": "array",
                                    "items": {"type": "object"},
                                },
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "Fehlende created_at/source_created_at "
                                        "Metadaten ergaenzen."
                                    ),
                                },
                                "next_steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "success_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "action_summary": {
                        "type": "object",
                        "properties": {
                            "total": {"type": "integer", "example": 3},
                            "critical_priority_count": {
                                "type": "integer",
                                "example": 0,
                            },
                            "high_priority_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "medium_priority_count": {
                                "type": "integer",
                                "example": 2,
                            },
                            "next_action_type": {
                                "type": "string",
                                "example": "review_low_quality_retrieval_hits",
                            },
                            "next_action_priority": {
                                "type": "string",
                                "example": "high",
                            },
                            "priority_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "type_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                        },
                    },
                    "source_freshness": {
                        "type": "object",
                        "properties": {
                            "stale_threshold_days": {
                                "type": "integer",
                                "example": 180,
                            },
                            "measured_source_count": {
                                "type": "integer",
                                "example": 12,
                            },
                            "undated_source_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "average_source_age_days": {
                                "type": "number",
                                "example": 42.5,
                            },
                            "oldest_source_age_days": {
                                "type": "integer",
                                "example": 365,
                            },
                            "stale_source_count": {
                                "type": "integer",
                                "example": 2,
                            },
                            "stale_source_rate": {
                                "type": "number",
                                "example": 0.1667,
                            },
                        },
                    },
                    "chunk_usage": {"type": "array", "items": {"type": "object"}},
                    "frequently_used_documents": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            },
            "quality_metrics": {
                "type": "object",
                "properties": {
                    "recall_at_k": {"type": "number", "example": 0.83},
                    "mrr": {"type": "number", "example": 0.72},
                    "keyword_hit_rate": {"type": "number", "example": 0.75},
                    "no_result_rate": {"type": "number", "example": 0.08},
                    "no_result_count": {"type": "integer", "example": 1},
                    "expected_no_result_count": {"type": "integer", "example": 1},
                    "expected_no_result_success_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "expected_no_result_success_rate": {
                        "type": "number",
                        "example": 1.0,
                    },
                    "unexpected_no_result_count": {"type": "integer", "example": 0},
                    "unexpected_no_result_rate": {"type": "number", "example": 0.0},
                    "min_source_count_fail_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "min_source_count_pass_rate": {
                        "type": "number",
                        "example": 0.92,
                    },
                    "query_type_expected_count": {"type": "integer", "example": 6},
                    "query_type_match_count": {"type": "integer", "example": 5},
                    "query_type_accuracy": {"type": "number", "example": 0.8333},
                    "permission_leak_count": {"type": "integer", "example": 0},
                    "source_metadata_gaps": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "evaluation_quality_gate": {
                        "type": "object",
                        "example": {
                            "status": "warning",
                            "passed": False,
                            "blocking": [],
                            "warnings": [
                                {
                                    "metric": "recall_at_k",
                                    "value": 0.7,
                                    "threshold": 0.75,
                                    "reason": "expected_sources_not_recalled",
                                },
                            ],
                        },
                    },
                    "evaluation_warning_count": {
                        "type": "integer",
                        "example": 2,
                    },
                    "evaluation_blocking_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "evaluation_blocking_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["permission_leak_count"],
                    },
                    "evaluation_blocking_rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {
                                    "type": "string",
                                    "example": "permission_leak_count",
                                },
                                "value": {"type": "number", "example": 1},
                                "threshold": {"type": "number", "example": 0},
                                "reason": {
                                    "type": "string",
                                    "example": ("retrieved_forbidden_or_invisible_source"),
                                },
                            },
                        },
                    },
                    "evaluation_warning_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "example": ["keyword_hit_rate", "query_type_accuracy"],
                    },
                    "evaluation_warning_rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {
                                    "type": "string",
                                    "example": "keyword_hit_rate",
                                },
                                "value": {"type": "number", "example": 0.5},
                                "threshold": {"type": "number", "example": 0.6},
                                "reason": {
                                    "type": "string",
                                    "example": "expected_keywords_missing",
                                },
                            },
                        },
                    },
                    "evaluation_actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "example": "fix_permission_leaks",
                                },
                                "priority": {
                                    "type": "string",
                                    "example": "critical",
                                },
                                "target_type": {
                                    "type": "string",
                                    "example": "retrieval_evaluation",
                                },
                                "target": {
                                    "type": "string",
                                    "example": "permission_leak_count",
                                },
                                "count": {"type": "integer", "example": 1},
                                "warning_metrics": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "example": ["block_metadata_coverage_rate"],
                                },
                                "focus_areas": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "example": ["chunk_structure_metadata"],
                                },
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "Chunk-Strukturmetadaten im Index pruefen "
                                        "und betroffene Dokumente mit aktuellem "
                                        "Chunking neu indexieren."
                                    ),
                                },
                                "next_steps": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "example": [
                                        "Evaluation-Warnungen nach "
                                        "block_metadata_coverage_rate filtern.",
                                        "Index-Metadaten chunk_block_count und "
                                        "chunk_block_kinds pruefen.",
                                    ],
                                },
                                "success_criteria": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "example": [
                                        "block_metadata_coverage_rate liegt " "mindestens bei 0.8.",
                                    ],
                                },
                            },
                        },
                    },
                    "evaluation_action_summary": {
                        "type": "object",
                        "properties": {
                            "total": {"type": "integer", "example": 4},
                            "critical_priority_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "high_priority_count": {
                                "type": "integer",
                                "example": 1,
                            },
                            "medium_priority_count": {
                                "type": "integer",
                                "example": 2,
                            },
                            "next_action_type": {
                                "type": "string",
                                "example": "fix_permission_leaks",
                            },
                            "next_action_priority": {
                                "type": "string",
                                "example": "critical",
                            },
                            "priority_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "type_distribution": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                        },
                    },
                },
            },
            "recommended_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "example": "fix_permission_leaks",
                        },
                        "rank": {"type": "integer", "example": 1},
                        "rank_label": {"type": "string", "example": "P1"},
                        "priority": {
                            "type": "string",
                            "example": "critical",
                        },
                        "action_source": {
                            "type": "string",
                            "example": "evaluation",
                        },
                        "target_type": {
                            "type": "string",
                            "example": "retrieval_evaluation",
                        },
                        "target": {
                            "type": "string",
                            "example": "permission_leak_count",
                        },
                        "recommended_action": {
                            "type": "string",
                            "example": (
                                "Metadatenfilter, Rollen-/Department-Sichtbarkeit "
                                "und Permission-Leak-Golden-Tests pruefen."
                            ),
                        },
                    },
                },
            },
            "next_best_action": {
                "type": "object",
                "nullable": True,
                "properties": {
                    "type": {
                        "type": "string",
                        "example": "fix_permission_leaks",
                    },
                    "rank": {"type": "integer", "example": 1},
                    "rank_label": {"type": "string", "example": "P1"},
                    "priority": {
                        "type": "string",
                        "example": "critical",
                    },
                    "action_source": {
                        "type": "string",
                        "example": "evaluation",
                    },
                    "recommended_action": {
                        "type": "string",
                        "example": (
                            "Metadatenfilter, Rollen-/Department-Sichtbarkeit "
                            "und Permission-Leak-Golden-Tests pruefen."
                        ),
                    },
                },
            },
            "governance": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "example": "warning"},
                    "alert_count": {"type": "integer", "example": 2},
                    "critical_count": {"type": "integer", "example": 1},
                    "warning_count": {"type": "integer", "example": 1},
                    "alerts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rule": {
                                    "type": "string",
                                    "example": "high_no_source_rate",
                                },
                                "metric": {"type": "string", "example": "no_source_rate"},
                                "severity": {"type": "string", "example": "warning"},
                                "title": {
                                    "type": "string",
                                    "example": "Hohe No-Source-Rate",
                                },
                                "value": {"type": "number", "example": 0.25},
                                "threshold": {"type": "number", "example": 0.2},
                                "recommended_action": {
                                    "type": "string",
                                    "example": (
                                        "Knowledge-Gaps, Berechtigungen und "
                                        "strukturierte Datenabdeckung pruefen."
                                    ),
                                },
                            },
                        },
                    },
                    "rules": {"type": "array", "items": {"type": "object"}},
                    "config": {"type": "object"},
                    "privacy": {"type": "object"},
                },
            },
            "alerts": {
                "type": "array",
                "items": {"type": "object"},
            },
            "recommended_action_summary": {
                "type": "object",
                "properties": {
                    "total": {"type": "integer", "example": 5},
                    "critical_priority_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "high_priority_count": {
                        "type": "integer",
                        "example": 3,
                    },
                    "medium_priority_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "next_action_type": {
                        "type": "string",
                        "example": "fix_permission_leaks",
                    },
                    "next_action_priority": {
                        "type": "string",
                        "example": "critical",
                    },
                    "next_action_source": {
                        "type": "string",
                        "example": "evaluation",
                    },
                    "answer_quality_action_count": {
                        "type": "integer",
                        "example": 2,
                    },
                    "answer_quality_high_action_count": {
                        "type": "integer",
                        "example": 1,
                    },
                    "answer_quality_next_action_type": {
                        "type": "string",
                        "example": "review_no_answer_guarded_questions",
                    },
                    "answer_quality_next_action_priority": {
                        "type": "string",
                        "example": "high",
                    },
                    "priority_distribution": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "type_distribution": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "source_distribution": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
            },
            "metric_catalog": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "example": "retrieval_hit_rate"},
                        "label": {"type": "string", "example": "Retrieval-Erfolgsquote"},
                        "category": {"type": "string", "example": "quality"},
                        "unit": {"type": "string", "example": "rate"},
                    },
                    "required": ["key", "label", "category", "unit"],
                },
            },
            "ai_logs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chat_message_id": {"type": "integer", "example": 21},
                        "audit_event_id": {"type": "integer", "example": 44},
                        "created_at": {"type": "string", "format": "date-time"},
                        "user_question": {
                            "type": "string",
                            "example": "Wie behebe ich Fehler X999?",
                        },
                        "answer_preview": {
                            "type": "string",
                            "example": "Keine belegte Antwort vorhanden.",
                        },
                        "response_type": {"type": "string", "example": "assistant"},
                        "answer_quality": {"type": "object"},
                        "answer_quality_label": {"type": "string", "example": "risk"},
                        "confidence": {
                            "type": "object",
                            "properties": {
                                "score": {"type": "integer", "example": 42},
                                "level": {"type": "string", "example": "low"},
                                "uncertainty": {"type": "string", "example": "high"},
                            },
                        },
                        "source_count": {"type": "integer", "example": 0},
                        "knowledge_gap_id": {"type": "integer", "example": 321},
                        "knowledge_gap_created": {"type": "boolean", "example": True},
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "example": "knowledge"},
                                    "id": {"type": "integer", "example": 12},
                                    "title": {
                                        "type": "string",
                                        "example": "Presse 42 Hydraulikhandbuch",
                                    },
                                    "source_record_id": {
                                        "type": "integer",
                                        "nullable": True,
                                        "example": 123,
                                    },
                                    "module": {
                                        "type": "string",
                                        "example": "knowledge",
                                    },
                                    "machine_id": {"type": "integer", "example": 42},
                                    "role_visibility": {
                                        "type": "string",
                                        "example": "department:Instandhaltung",
                                    },
                                    "created_at": {
                                        "type": "string",
                                        "format": "date-time",
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "failed_requests": {"type": "array", "items": {"type": "object"}},
            "langfuse_metrics": {"type": "object"},
            "privacy": {
                "type": "object",
                "example": {
                    "raw_chunk_text_visible": False,
                    "source_metadata_aggregates_visible": True,
                },
            },
        },
    },
    "IncidentTimeline": {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object"}},
            "sequences": {"type": "array", "items": {"type": "object"}},
            "stats": {"type": "object"},
            "filters": {"type": "object"},
            "explainability": {"type": "object"},
        },
    },
    "ChatTemplate": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "example": "Fehler analysieren"},
            "prompt": {"type": "string", "example": "Welche Ursache hat Fehler F-100?"},
            "category": {"type": "string", "example": "Stoerung"},
            "sort_order": {"type": "integer", "example": 10},
        },
    },
    "Site": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 1},
            "code": {"type": "string", "example": "werk-1"},
            "name": {"type": "string", "example": "Werk 1"},
            "timezone": {"type": "string", "example": "Europe/Berlin"},
            "is_active": {"type": "boolean", "example": True},
        },
    },
    "OperationalEvent": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 42},
            "event_type": {"type": "string", "example": "task.completed"},
            "feature": {"type": "string", "example": "tasks"},
            "entity_type": {"type": "string", "example": "task"},
            "entity_id": {"type": "integer", "example": 12},
            "site_id": {"type": "integer", "example": 1},
            "department_id": {"type": "integer", "example": 3},
            "machine_id": {"type": "integer", "nullable": True},
            "task_id": {"type": "integer", "nullable": True},
            "actor_hash": {"type": "string", "example": "pseudonymous-hmac"},
            "actor_role": {"type": "string", "example": "instandhaltung"},
            "source": {"type": "string", "example": "app"},
            "old_value": {"type": "object", "nullable": True},
            "new_value": {"type": "object", "nullable": True},
            "description": {
                "type": "string",
                "example": "Task wurde abgeschlossen.",
            },
            "metadata": {"type": "object"},
            "occurred_at": {"type": "string", "format": "date-time"},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
    "OperationsSummary": {
        "type": "object",
        "properties": {
            "filters": {"type": "object"},
            "tasks": {"type": "object"},
            "machines": {"type": "object"},
            "inventory": {"type": "object"},
            "workforce": {"type": "object"},
            "documents": {"type": "object"},
            "ai_quality": {"type": "object"},
            "events": {"type": "object"},
        },
    },
    "AssistantTrainingEntry": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 7},
            "title": {"type": "string", "example": "Hydraulik X900"},
            "question": {"type": "string", "example": "Was tun bei X900?"},
            "answer": {"type": "string", "example": "Druck pruefen und Ventil reinigen."},
            "keywords": {"type": "string", "example": "X900, Hydraulik"},
            "category": {"type": "string", "example": "Stoerung"},
            "department": {"type": "string", "example": "Instandhaltung"},
            "is_active": {"type": "boolean", "example": True},
            "priority": {"type": "integer", "example": 50},
            "missing_information": {
                "$ref": "#/components/schemas/MissingInformation",
            },
        },
    },
}


ADDITIONAL_PATHS = {
    "/health/ready": {
        "get": {
            "tags": ["Health"],
            "summary": "Inspect readiness for database, AI provider and RAG index",
            "responses": {
                "200": {
                    "description": "Readiness diagnostics loaded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/HealthReadiness"}
                        }
                    },
                },
                "503": {"description": "Database unavailable"},
            },
        }
    },
    "/api/v1/ai/status": {
        "get": {
            "tags": ["AI", "Admin"],
            "summary": "Inspect redacted AI provider and fallback readiness",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {
                    "description": "AI status loaded without secrets",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/AIStatus"}}
                    },
                },
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/ai/chat": {
        "post": {
            "tags": ["AI"],
            "summary": "Ask the maintenance assistant with permission-aware RAG context",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "message": "Welche Maschinen sind sichtbar?",
                            "session_id": "chat-widget",
                            "response_mode": "answer_only",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": (
                        "AI response with answer quality, confidence, and "
                        "prompt-safe source metadata when visible"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AIChatResponse"}
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
            },
        }
    },
    "/api/v1/ai/agent": {
        "post": {
            "tags": ["AI"],
            "summary": "Ask the tool-using maintenance agent",
            "description": (
                "Runs the LangGraph agent loop: deterministic safety guard, provider "
                "tool selection, permission-gated tool execution, validation. Write "
                "tools return a signed pending_action that must be confirmed."
            ),
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "message": "Welche offenen Tasks gibt es an Presse 3?",
                            "session_id": "chat-widget",
                            "response_mode": "answer_only",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": (
                        "Agent answer with tool trace, sources, confidence and optional "
                        "pending_action for confirmable write tools"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AIChatResponse"},
                            "example": {
                                "type": "agent",
                                "answer": "## Ergebnis\n- Dichtung an Presse 3 pruefen (open)",
                                "tool_trace": [
                                    {
                                        "tool": "search_tasks",
                                        "status": "ok",
                                        "summary": "1 Treffer in tasks",
                                        "source_count": 1,
                                        "duration_ms": 12,
                                    }
                                ],
                                "pending_action": None,
                                "diagnostics": {
                                    "status": "openai_used",
                                    "workflow": "agent",
                                    "agent_iterations": 2,
                                    "agent_tool_calls": ["search_tasks"],
                                },
                            },
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "429": {"description": "Per-user rate limit or daily token budget exceeded"},
            },
        }
    },
    "/api/v1/ai/agent/confirm": {
        "post": {
            "tags": ["AI"],
            "summary": "Confirm a pending agent write action",
            "description": (
                "Executes one signed pending action (for example create_task) once. "
                "Tokens are bound to the requesting user and expire after "
                "AI_AGENT_ACTION_TTL_SECONDS."
            ),
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {"token": "<signed-token>", "session_id": "chat-widget"}
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Action executed",
                    "content": {
                        "application/json": {
                            "example": {
                                "type": "agent_action",
                                "tool": "create_task",
                                "answer": "## Aktion ausgefuehrt\n- **Aktion:** Task anlegen",
                                "data": {"task": {"id": 42, "title": "Filter tauschen"}},
                            }
                        }
                    },
                },
                "400": {"description": "Invalid or expired action token"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"description": "Action belongs to another user or lacks permission"},
            },
        }
    },
    "/api/v1/ai/agent/tools": {
        "get": {
            "tags": ["AI"],
            "summary": "List agent tools available to the current user",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {
                    "description": "Permission-filtered tool catalog",
                    "content": {
                        "application/json": {
                            "example": {
                                "tool_count": 9,
                                "max_iterations": 4,
                                "confirmation_required_tools": ["create_task"],
                                "tools": [
                                    {
                                        "name": "search_tasks",
                                        "label": "Search Tasks",
                                        "requires_confirmation": False,
                                        "write": False,
                                        "scopes": ["tasks"],
                                    }
                                ],
                            }
                        }
                    },
                },
                "401": {"$ref": "#/components/responses/Unauthorized"},
            },
        }
    },
    "/api/v1/ai/chat/history": {
        "get": {
            "tags": ["AI"],
            "summary": "Search own AI chat history",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Chat history loaded"}},
        }
    },
    "/api/v1/ai/chat/templates": {
        "get": {
            "tags": ["AI"],
            "summary": "Load permission-aware chat templates",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Chat templates loaded"}},
        }
    },
    "/api/v1/ai/error-assistant": {
        "post": {
            "tags": ["AI"],
            "summary": "Run root cause analysis for a visible machine fault",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "query": "Presse 42 meldet P42-HYD und Druckverlust",
                            "limit": 5,
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": (
                        "Root cause analysis with similar cases, next steps, "
                        "confidence and prompt-safe evidence sources"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorAssistantResult"}
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/tasks/prioritize": {
        "post": {
            "tags": ["Tasks", "AI"],
            "summary": "Prioritize visible tasks with AI-backed maintenance evidence",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "example": {
                            "status": "open",
                            "limit": 20,
                            "mode": "ai",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": (
                        "Task priorities with risk rationale and aggregated "
                        "visible evidence counts"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {
                                    "$ref": ("#/components/schemas/" "TaskPrioritySuggestion")
                                },
                            }
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/machines/maintenance-recommendations": {
        "get": {
            "tags": ["Machines", "AI"],
            "summary": ("Return light maintenance recommendations from visible history"),
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 5, "minimum": 1},
                },
            ],
            "responses": {
                "200": {
                    "description": (
                        "Read-only maintenance recommendations with evidence "
                        "summary and explicit non-predictive limitations"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": (
                                    "#/components/schemas/" "MaintenanceRecommendationLightResponse"
                                )
                            }
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/handover/{handover_id}/summary": {
        "get": {
            "tags": ["Shift Handover", "AI"],
            "summary": ("Summarize a visible shift handover with tasks and disruptions"),
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "handover_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                },
            ],
            "responses": {
                "200": {
                    "description": (
                        "Local AI-ready handover summary with confidence, "
                        "next actions and prompt-safe evidence metadata"
                    ),
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ShiftHandoverSummary"}
                        }
                    },
                },
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
                "404": {"description": "Handover not found"},
            },
        }
    },
    "/api/v1/ai/feedback": {
        "post": {
            "tags": ["AI"],
            "summary": "Store feedback for an AI answer",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "chat_message_id": 42,
                            "rating": "partially_helpful",
                            "comment": "Quelle passt, Antwort war zu knapp.",
                            "sources": [
                                {
                                    "type": "knowledge",
                                    "id": 7,
                                    "chunk_id": 13,
                                    "title": "CNC Manual",
                                }
                            ],
                        }
                    }
                },
            },
            "responses": {
                "201": {"description": "Feedback saved"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
            },
        }
    },
    "/api/v1/ai/order-plan": {
        "post": {
            "tags": ["AI"],
            "summary": "Plan a production order with machine, material and staffing checks",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "product": "Deckel",
                            "quantity": 100,
                            "department": "Produktion",
                            "work_date": "2026-05-18",
                        }
                    }
                },
            },
            "responses": {
                "200": {"description": "Order plan generated"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/sites": {
        "get": {
            "tags": ["Sites"],
            "summary": "List active plants/sites for selectors",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Sites loaded"}},
        }
    },
    "/api/v1/operations/summary": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load cross-feature operations KPIs",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {"name": "from", "in": "query", "schema": {"type": "string", "format": "date"}},
                {"name": "to", "in": "query", "schema": {"type": "string", "format": "date"}},
                {"name": "site_id", "in": "query", "schema": {"type": "integer"}},
                {"name": "department_id", "in": "query", "schema": {"type": "integer"}},
                {"name": "machine_id", "in": "query", "schema": {"type": "integer"}},
            ],
            "responses": {"200": {"description": "Operations summary loaded"}},
        }
    },
    "/api/v1/operations/events": {
        "get": {
            "tags": ["Operations"],
            "summary": "List pseudonymized operational events",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Operations events loaded"}},
        }
    },
    "/api/v1/operations/tasks": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load task lifecycle KPI drilldown",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Task operations loaded"}},
        }
    },
    "/api/v1/operations/machines": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load machine downtime and fault KPIs",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Machine operations loaded"}},
        }
    },
    "/api/v1/operations/inventory": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load inventory risk KPIs",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Inventory operations loaded"}},
        }
    },
    "/api/v1/operations/workforce": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load shift coverage and conflict KPIs",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Workforce operations loaded"}},
        }
    },
    "/api/v1/operations/ai-quality": {
        "get": {
            "tags": ["Operations"],
            "summary": "Load AI latency, cost and feedback KPIs",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "AI quality operations loaded"}},
        }
    },
    "/api/v1/admin/sites": {
        "get": {
            "tags": ["Sites", "Admin"],
            "summary": "List all sites as master admin",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Sites loaded"}},
        },
        "post": {
            "tags": ["Sites", "Admin"],
            "summary": "Create a site",
            "security": [{"bearerAuth": []}],
            "responses": {
                "201": {"description": "Site created"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "409": {"$ref": "#/components/responses/ValidationError"},
            },
        },
    },
    "/api/v1/admin/sites/{site_id}": {
        "put": {
            "tags": ["Sites", "Admin"],
            "summary": "Update a site",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {"description": "Site updated"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "404": {"description": "Site not found"},
            },
        }
    },
    "/api/v1/admin/operations/aggregate": {
        "post": {
            "tags": ["Operations", "Admin"],
            "summary": "Rebuild persisted operations aggregates",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Operations aggregates rebuilt"}},
        }
    },
    "/api/v1/admin/ai/chats": {
        "get": {
            "tags": ["Admin"],
            "summary": "Search all AI chats as master admin",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "AI chats loaded"}},
        }
    },
    "/api/v1/admin/ai/events": {
        "get": {
            "tags": ["Admin"],
            "summary": "Search metadata-only AI audit events",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "AI events loaded"}},
        }
    },
    "/api/v1/admin/ai/training": {
        "get": {
            "tags": ["Admin"],
            "summary": "List manual assistant training entries",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Training entries loaded"}},
        },
        "post": {
            "tags": ["Admin"],
            "summary": "Create a manual assistant training entry",
            "security": [{"bearerAuth": []}],
            "responses": {
                "201": {"description": "Training entry created"},
                "400": {"$ref": "#/components/responses/ValidationError"},
            },
        },
    },
    "/api/v1/admin/ai/training/{entry_id}": {
        "put": {
            "tags": ["Admin"],
            "summary": "Update a manual assistant training entry",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {"description": "Training entry updated"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "404": {"description": "Training entry not found"},
            },
        },
        "delete": {
            "tags": ["Admin"],
            "summary": "Delete a manual assistant training entry",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {"description": "Training entry deleted"},
                "404": {"description": "Training entry not found"},
            },
        },
    },
    "/api/v1/admin/ai/knowledge/upload": {
        "post": {
            "tags": ["Admin"],
            "summary": "Upload, chunk and index a knowledge document",
            "security": [{"bearerAuth": []}],
            "responses": {"201": {"description": "Knowledge document uploaded"}},
        }
    },
    "/api/v1/admin/ai/knowledge": {
        "get": {
            "tags": ["Admin"],
            "summary": "List knowledge documents",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge documents loaded"}},
        }
    },
    "/api/v1/admin/ai/knowledge/status": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect RAG index status and source diagnostics",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge status loaded"}},
        }
    },
    "/api/v1/admin/ai/knowledge-network": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect the read-only maintenance knowledge network",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {"name": "q", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "source_type",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                {
                    "name": "quality_status",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                {
                    "name": "days",
                    "in": "query",
                    "schema": {"type": "integer", "default": 30},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 120},
                },
                {"name": "focus", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {
                "200": {
                    "description": "Knowledge network loaded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/KnowledgeNetwork"}
                        }
                    },
                }
            },
        }
    },
    "/api/v1/admin/ai/retrieval-telemetry": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect retrieval telemetry and quality analytics",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "days",
                    "in": "query",
                    "schema": {"type": "integer", "default": 30},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 10},
                },
            ],
            "responses": {
                "200": {
                    "description": "Retrieval telemetry loaded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/RetrievalTelemetry"}
                        }
                    },
                }
            },
        }
    },
    "/api/v1/admin/ai/retrieval-debug": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect prompt-safe retrieval debug records",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {"name": "q", "in": "query", "schema": {"type": "string"}},
                {
                    "name": "query_type",
                    "in": "query",
                    "schema": {"type": "string"},
                },
                {
                    "name": "days",
                    "in": "query",
                    "schema": {"type": "integer", "default": 30},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 30},
                },
            ],
            "responses": {
                "200": {
                    "description": "Retrieval debug loaded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/RetrievalDebug"}
                        }
                    },
                }
            },
        }
    },
    "/api/v1/admin/ai/retrieval-evaluations": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect prompt-safe golden retrieval evaluation history",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 10},
                },
            ],
            "responses": {
                "200": {
                    "description": (
                        "Retrieval evaluation history loaded without query text "
                        "or source identifiers"
                    )
                }
            },
        }
    },
    "/api/v1/admin/ai/retrieval-evaluations/run": {
        "post": {
            "tags": ["Admin"],
            "summary": "Run the bounded golden retrieval evaluation suite",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "example": {"limit": 20},
                    }
                },
            },
            "responses": {
                "201": {
                    "description": ("Retrieval evaluation persisted as aggregate metrics only"),
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": ("#/components/schemas/" "RetrievalEvaluationRunResult")
                            }
                        }
                    },
                }
            },
        }
    },
    "/api/v1/admin/ai/observability": {
        "get": {
            "tags": ["Admin"],
            "summary": "Inspect AI monitoring, logs, quality metrics and debug blueprints",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "days",
                    "in": "query",
                    "schema": {"type": "integer", "default": 30},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "schema": {"type": "integer", "default": 10},
                },
                {
                    "name": "chat_message_id",
                    "in": "query",
                    "schema": {"type": "integer"},
                },
            ],
            "responses": {
                "200": {
                    "description": "AI observability loaded",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AIObservability"}
                        }
                    },
                }
            },
        }
    },
    "/api/v1/admin/ai/knowledge-gaps": {
        "get": {
            "tags": ["Admin"],
            "summary": "List AI knowledge gaps from unanswered questions",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge gaps loaded"}},
        }
    },
    "/api/v1/admin/jobs": {
        "get": {
            "tags": ["Admin"],
            "summary": "List background jobs",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Background jobs loaded"}},
        }
    },
    "/api/v1/health/operations": {
        "get": {
            "tags": ["Health", "Admin"],
            "summary": "Inspect operations metrics for administrators",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Operations metrics loaded"}},
        }
    },
    "/api/v1/admin/ai/knowledge/reindex/jobs": {
        "post": {
            "tags": ["Admin"],
            "summary": "Queue a RAG reindex background job",
            "security": [{"bearerAuth": []}],
            "responses": {"202": {"description": "Background job queued"}},
        }
    },
    "/api/v1/admin/ai/knowledge/aging/jobs": {
        "post": {
            "tags": ["Admin"],
            "summary": "Queue a knowledge aging review background job",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": False,
                "content": {"application/json": {"example": {"dry_run": True, "limit": 100}}},
            },
            "responses": {"202": {"description": "Background job queued"}},
        }
    },
    "/api/v1/admin/ai/knowledge/reindex": {
        "post": {
            "tags": ["Admin"],
            "summary": "Rebuild local knowledge chunks, optionally stale only",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge reindexed"}},
        }
    },
    "/api/v1/admin/ai/knowledge/{id}/reindex": {
        "post": {
            "tags": ["Admin"],
            "summary": "Reindex one knowledge document",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge document reindexed"}},
        }
    },
    "/api/v1/admin/ai/knowledge/{id}/quality-status": {
        "put": {
            "tags": ["Admin"],
            "summary": "Update the quality workflow status for one knowledge document",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"example": {"quality_status": "technician_confirmed"}}
                },
            },
            "responses": {
                "200": {"description": "Knowledge quality status updated"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/admin/ai/knowledge/{id}": {
        "delete": {
            "tags": ["Admin"],
            "summary": "Delete a knowledge document",
            "security": [{"bearerAuth": []}],
            "responses": {"200": {"description": "Knowledge document deleted"}},
        }
    },
}
