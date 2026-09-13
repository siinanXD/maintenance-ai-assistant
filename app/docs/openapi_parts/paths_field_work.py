"""OpenAPI paths for shop-floor work: photos, QR labels, spare parts and inspections."""

_AUTH = [{"bearerAuth": []}]
_ERRORS = {
    "401": {"$ref": "#/components/responses/Unauthorized"},
    "403": {"$ref": "#/components/responses/Forbidden"},
}

SCHEMAS_FIELD_WORK = {
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
}
