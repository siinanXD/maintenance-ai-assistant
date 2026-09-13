"""OpenAPI paths for shop-floor work: photos, QR labels, spare parts and inspections."""

_AUTH = [{"bearerAuth": []}]


def _path_id(name):
    """Return an integer path parameter definition."""
    return {"name": name, "in": "path", "required": True, "schema": {"type": "integer"}}


def _json_body(properties, required):
    """Return a required JSON request body definition."""
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "required": required, "properties": properties}
            }
        },
    }


_ERRORS = {
    "401": {"$ref": "#/components/responses/Unauthorized"},
    "403": {"$ref": "#/components/responses/Forbidden"},
}

SCHEMAS_FIELD_WORK = {
    "StockMovement": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "material_id": {"type": "integer"},
            "material_name": {"type": "string", "example": "Rillenkugellager 6205"},
            "task_id": {"type": "integer", "nullable": True},
            "quantity_change": {"type": "integer", "example": -2},
            "reason": {"type": "string", "enum": ["withdrawal", "receipt"]},
            "note": {"type": "string"},
            "value": {"type": "number", "example": 25.0},
            "created_at": {"type": "string", "format": "date-time"},
        },
    },
    "Attachment": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "example": 12},
            "entity_type": {"type": "string", "enum": ["error", "task"]},
            "entity_id": {"type": "integer", "example": 81},
            "filename": {"type": "string", "example": "leckage.png"},
            "content_type": {"type": "string", "example": "image/png"},
            "size_bytes": {"type": "integer", "example": 8342},
            "is_image": {"type": "boolean", "example": True},
            "uploaded_by": {"type": "object", "nullable": True},
            "created_at": {"type": "string", "format": "date-time"},
            "file_url": {"type": "string", "example": "/api/v1/attachments/12/file"},
        },
    },
}

PATHS_FIELD_WORK = {
    "/api/v1/attachments": {
        "get": {
            "tags": ["Attachments"],
            "summary": "List photos and PDFs of one incident or task",
            "security": _AUTH,
            "parameters": [
                {
                    "name": "entity_type",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string", "enum": ["error", "task"]},
                },
                {
                    "name": "entity_id",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "integer"},
                },
            ],
            "responses": {
                "200": {
                    "description": "Attachments, newest first",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "data": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Attachment"},
                                    }
                                },
                            }
                        }
                    },
                },
                "404": {"description": "Record not found or not visible"},
                **_ERRORS,
            },
        },
        "post": {
            "tags": ["Attachments"],
            "summary": "Upload a photo (JPG, PNG, WebP) or PDF",
            "description": (
                "The file type is detected from its content, not from the name. "
                "Requires write permission on the owning dashboard. Limit: "
                "ATTACHMENT_MAX_BYTES (default 10 MB), 20 files per record."
            ),
            "security": _AUTH,
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["entity_type", "entity_id", "file"],
                            "properties": {
                                "entity_type": {"type": "string", "enum": ["error", "task"]},
                                "entity_id": {"type": "integer"},
                                "file": {"type": "string", "format": "binary"},
                            },
                        }
                    }
                },
            },
            "responses": {
                "201": {
                    "description": "Stored attachment",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"data": {"$ref": "#/components/schemas/Attachment"}},
                            }
                        }
                    },
                },
                "409": {"description": "Too many files on this record"},
                "413": {"description": "File too large"},
                "415": {"description": "Unsupported file type"},
                **_ERRORS,
            },
        },
    },
    "/api/v1/attachments/{attachment_id}/file": {
        "get": {
            "tags": ["Attachments"],
            "summary": "Download the stored file",
            "security": _AUTH,
            "parameters": [
                {
                    "name": "attachment_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ],
            "responses": {"200": {"description": "File content"}, **_ERRORS},
        }
    },
    "/api/v1/attachments/{attachment_id}": {
        "delete": {
            "tags": ["Attachments"],
            "summary": "Delete an attachment",
            "security": _AUTH,
            "parameters": [
                {
                    "name": "attachment_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ],
            "responses": {"204": {"description": "Deleted"}, **_ERRORS},
        }
    },
    "/api/v1/machines/{machine_id}/qr.svg": {
        "get": {
            "tags": ["Machines"],
            "summary": "QR label that opens the machine page",
            "description": "Encodes PUBLIC_BASE_URL (or the request host) + /m/{machine_id}.",
            "security": _AUTH,
            "parameters": [
                {
                    "name": "machine_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                }
            ],
            "responses": {
                "200": {"description": "SVG image", "content": {"image/svg+xml": {}}},
                **_ERRORS,
            },
        }
    },
    "/api/v1/tasks/{task_id}/materials": {
        "get": {
            "tags": ["Tasks", "Inventory"],
            "summary": "Spare parts withdrawn for a work order",
            "security": _AUTH,
            "parameters": [_path_id("task_id")],
            "responses": {
                "200": {
                    "description": "Movements with total value",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "data": {
                                        "type": "object",
                                        "properties": {
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "$ref": "#/components/schemas/StockMovement"
                                                },
                                            },
                                            "total_value": {"type": "number", "example": 25.0},
                                        },
                                    }
                                },
                            }
                        }
                    },
                },
                **_ERRORS,
            },
        },
        "post": {
            "tags": ["Tasks", "Inventory"],
            "summary": "Withdraw spare parts for an open work order",
            "description": "Needs tasks write and inventory view. Stock never goes below zero.",
            "security": _AUTH,
            "parameters": [_path_id("task_id")],
            "requestBody": _json_body(
                {
                    "material_id": {"type": "integer", "example": 7},
                    "quantity": {"type": "integer", "minimum": 1, "example": 2},
                    "note": {"type": "string", "example": "Antriebsseite"},
                },
                required=["material_id", "quantity"],
            ),
            "responses": {
                "201": {"description": "Booked withdrawal"},
                "409": {"description": "Not enough stock or work order already closed"},
                **_ERRORS,
            },
        },
    },
    "/api/v1/inventory/reorder": {
        "get": {
            "tags": ["Inventory"],
            "summary": "Materials at or below minimum stock with order quantities",
            "description": (
                "Order quantity refills to twice the minimum and covers the parts consumed "
                "during the supplier lead time, based on withdrawals of the last 90 days."
            ),
            "security": _AUTH,
            "responses": {"200": {"description": "Reorder suggestions"}, **_ERRORS},
        }
    },
    "/api/v1/inventory/{material_id}/movements": {
        "get": {
            "tags": ["Inventory"],
            "summary": "Latest stock movements of one material",
            "security": _AUTH,
            "parameters": [_path_id("material_id")],
            "responses": {"200": {"description": "Movements, newest first"}, **_ERRORS},
        }
    },
    "/api/v1/inventory/{material_id}/receipts": {
        "post": {
            "tags": ["Inventory"],
            "summary": "Book a goods receipt",
            "security": _AUTH,
            "parameters": [_path_id("material_id")],
            "requestBody": _json_body(
                {
                    "quantity": {"type": "integer", "minimum": 1, "example": 10},
                    "note": {"type": "string", "example": "LS 4711"},
                },
                required=["quantity"],
            ),
            "responses": {"201": {"description": "Updated material and movement"}, **_ERRORS},
        }
    },
    "/api/v1/machines/maintenance-plans/{plan_id}/records": {
        "get": {
            "tags": ["Machines"],
            "summary": "Documented executions of a maintenance or inspection plan",
            "security": _AUTH,
            "parameters": [_path_id("plan_id")],
            "responses": {"200": {"description": "Records, newest first"}, **_ERRORS},
        },
        "post": {
            "tags": ["Machines"],
            "summary": "Document an execution and schedule the next due date",
            "description": (
                "passed/defects move next_due_date one interval past performed_on; failed "
                "schedules a re-test after 7 days. defects/failed create a follow-up task "
                "unless create_follow_up is false (needs tasks write)."
            ),
            "security": _AUTH,
            "parameters": [_path_id("plan_id")],
            "requestBody": _json_body(
                {
                    "performed_on": {"type": "string", "format": "date"},
                    "performed_by": {"type": "string", "example": "TÜV Süd Industrie Service"},
                    "result": {"type": "string", "enum": ["passed", "defects", "failed"]},
                    "notes": {"type": "string", "example": "Prüfprotokoll E-2026-0412"},
                    "create_follow_up": {"type": "boolean", "default": True},
                },
                required=["performed_by", "result"],
            ),
            "responses": {
                "201": {"description": "Record and updated plan"},
                "400": {"$ref": "#/components/responses/ValidationError"},
                **_ERRORS,
            },
        },
    },
}
