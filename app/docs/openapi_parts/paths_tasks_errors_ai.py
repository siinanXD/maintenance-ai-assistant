"""OpenAPI path fragment for tasks errors ai."""

PATHS_TASKS_ERRORS_AI = {
    "/api/v1/tasks": {
        "get": {
            "tags": ["Tasks"],
            "summary": "List visible tasks",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "status",
                    "in": "query",
                    "schema": {
                        "type": "string",
                        "enum": ["open", "in_progress", "done", "cancelled"],
                    },
                },
                {
                    "name": "priority",
                    "in": "query",
                    "schema": {"type": "string", "enum": ["urgent", "soon", "normal"]},
                },
            ],
            "responses": {
                "200": {
                    "description": "Visible tasks",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Task"},
                            }
                        }
                    },
                },
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        },
        "post": {
            "tags": ["Tasks"],
            "summary": "Create a task",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/TaskCreateRequest"},
                        "example": {
                            "title": "CNC-Fraese " "Spindellager " "pruefen",
                            "description": "Vibrationen "
                            "dokumentieren "
                            "und "
                            "Lager "
                            "pruefen.",
                            "priority": "urgent",
                            "status": "open",
                            "due_date": "2026-05-04",
                            "department": "Instandhaltung",
                        },
                    }
                },
            },
            "responses": {
                "201": {
                    "description": "Task created",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Task"}}
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
                "500": {"$ref": "#/components/responses/ValidationError"},
            },
        },
    },
    "/api/v1/tasks/{task_id}/start": {
        "post": {
            "tags": ["Tasks"],
            "summary": "Start a task",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {"name": "task_id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "requestBody": {"required": False, "content": {"application/json": {"example": {}}}},
            "responses": {
                "200": {
                    "description": "Task moved to " "in_progress",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Task"},
                            "example": {
                                "id": 42,
                                "title": "CNC-Fraese " "Spindellager " "pruefen",
                                "status": "in_progress",
                                "current_worker_id": 3,
                            },
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
                "404": {"$ref": "#/components/responses/ValidationError"},
                "409": {"$ref": "#/components/responses/ValidationError"},
            },
        }
    },
    "/api/v1/tasks/{task_id}/complete": {
        "post": {
            "tags": ["Tasks"],
            "summary": "Complete a task",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {"name": "task_id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ],
            "requestBody": {
                "required": False,
                "content": {
                    "application/json": {
                        "example": {
                            "generate_report": True,
                            "notes": "Lager " "geprueft, " "Probelauf " "ohne " "Auffaelligkeiten.",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Task "
                    "completed, "
                    "optionally "
                    "with "
                    "generated "
                    "document "
                    "metadata",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Task"},
                            "example": {
                                "id": 42,
                                "title": "CNC-Fraese " "Spindellager " "pruefen",
                                "status": "done",
                                "completed_by": 3,
                                "generated_document": {
                                    "id": 8,
                                    "download_url": "/api/v1/documents/8/download",
                                },
                            },
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
                "404": {"$ref": "#/components/responses/ValidationError"},
                "409": {"$ref": "#/components/responses/ValidationError"},
            },
        }
    },
    "/api/v1/tasks/prioritize": {
        "post": {
            "tags": ["AI", "Tasks"],
            "summary": "Prioritize visible tasks",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": False,
                "content": {"application/json": {"example": {"status": "open", "limit": 10}}},
            },
            "responses": {
                "200": {
                    "description": "Non-persisted AI or " "fallback priorities",
                    "content": {
                        "application/json": {
                            "example": [
                                {
                                    "task": {"id": 42, "title": "CNC-Fraese " "pruefen"},
                                    "score": 88,
                                    "risk_level": "high",
                                    "reason": "Faelligkeit " "und " "Anlagenbezug " "kritisch.",
                                    "recommended_action": "Heute " "starten.",
                                }
                            ]
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/errors": {
        "post": {
            "tags": ["Errors"],
            "summary": "Create an error catalog entry",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorCreateRequest"},
                        "example": {
                            "machine": "CNC-Fraese " "01",
                            "error_code": "CNC-E-104",
                            "title": "Temperatur " "ausserhalb " "Toleranz",
                            "description": "Spindeltemperatur " "steigt " "nach " "20 " "Minuten.",
                            "possible_causes": "Kuehlung, " "Sensor " "oder " "Lager " "pruefen.",
                            "solution": "Kuehlkreislauf "
                            "pruefen "
                            "und "
                            "Probelauf "
                            "dokumentieren.",
                            "department": "Instandhaltung",
                        },
                    }
                },
            },
            "responses": {
                "201": {
                    "description": "Error entry created",
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/ErrorEntry"}}
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/errors/search": {
        "get": {
            "tags": ["Errors"],
            "summary": "Search the visible error catalog",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "query",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "example": "Temperatur CNC",
                }
            ],
            "responses": {
                "200": {
                    "description": "Matching error entries",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/ErrorEntry"},
                            },
                            "example": [
                                {
                                    "id": 9,
                                    "machine": "CNC-Fraese " "01",
                                    "error_code": "CNC-E-104",
                                    "title": "Temperatur " "ausserhalb " "Toleranz",
                                    "possible_causes": "Kuehlung, "
                                    "Sensor "
                                    "oder "
                                    "Lager "
                                    "pruefen.",
                                    "solution": "Kuehlkreislauf "
                                    "pruefen "
                                    "und "
                                    "Probelauf "
                                    "dokumentieren.",
                                }
                            ],
                        }
                    },
                },
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
            },
        }
    },
    "/api/v1/errors/similar": {
        "post": {
            "tags": ["AI", "Errors"],
            "summary": "Suggest similar error catalog entries",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "description": "CNC-Fraese "
                            "meldet "
                            "hohe "
                            "Temperatur "
                            "an "
                            "der "
                            "Spindel",
                            "machine": "CNC-Fraese " "01",
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Similar error " "suggestions",
                    "content": {
                        "application/json": {
                            "example": {
                                "items": [
                                    {
                                        "entry": {
                                            "error_code": "CNC-E-104",
                                            "title": "Temperatur " "ausserhalb " "Toleranz",
                                        },
                                        "score": 91,
                                        "reason": "Maschine " "und " "Temperaturbegriff " "passen.",
                                    }
                                ]
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
    "/api/v1/errors/analyze": {
        "post": {
            "tags": ["AI", "Errors"],
            "summary": "Analyze an error description",
            "security": [{"bearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "description": "CNC-Fraese "
                            "stoppt "
                            "mit "
                            "Temperaturwarnung "
                            "an "
                            "der "
                            "Spindel"
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Non-persisted error " "analysis",
                    "content": {
                        "application/json": {
                            "example": {
                                "machine": "CNC-Fraese " "01",
                                "error_code": "AI-001",
                                "title": "Temperaturwarnung " "Spindel",
                                "possible_causes": "Kuehlung, " "Sensor " "oder " "Lager.",
                                "solution": "Kuehlung "
                                "pruefen "
                                "und "
                                "Probelauf "
                                "dokumentieren.",
                                "missing_information": {
                                    "status": "needs_information",
                                    "missing_fields": ["previous_checks"],
                                    "questions": [
                                        {
                                            "field": "previous_checks",
                                            "question": "Was "
                                            "wurde "
                                            "bereits "
                                            "geprueft, "
                                            "gemessen, "
                                            "gereinigt "
                                            "oder "
                                            "getauscht?",
                                        }
                                    ],
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
    "/api/v1/ai/daily-briefing": {
        "get": {
            "tags": ["AI"],
            "summary": "Get the daily briefing",
            "security": [{"bearerAuth": []}],
            "responses": {
                "200": {
                    "description": "Daily maintenance " "briefing",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/DailyBriefing"},
                            "example": {
                                "date": "2026-05-01",
                                "sections": [
                                    {
                                        "title": "Heute",
                                        "items": ["3 " "offene " "Tasks, " "1 " "kritisch"],
                                    }
                                ],
                                "diagnostics": {"status": "fallback_used"},
                            },
                        }
                    },
                },
                "401": {"$ref": "#/components/responses/Unauthorized"},
            },
        }
    },
    "/api/v1/machines/{machine_id}/assistant": {
        "post": {
            "tags": ["AI", "Machines"],
            "summary": "Ask the machine assistant",
            "security": [{"bearerAuth": []}],
            "parameters": [
                {
                    "name": "machine_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {
                            "question": "Welche "
                            "Wartung "
                            "ist "
                            "vor "
                            "Schichtbeginn "
                            "wichtig?"
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Machine-specific " "assistant " "answer",
                    "content": {
                        "application/json": {
                            "example": {
                                "answer": "Pruefe "
                                "offene "
                                "Tasks "
                                "und "
                                "knappe "
                                "Ersatzteile.",
                                "diagnostics": {"status": "local_answer"},
                            }
                        }
                    },
                },
                "400": {"$ref": "#/components/responses/ValidationError"},
                "401": {"$ref": "#/components/responses/Unauthorized"},
                "403": {"$ref": "#/components/responses/Forbidden"},
                "404": {"$ref": "#/components/responses/ValidationError"},
            },
        }
    },
}
