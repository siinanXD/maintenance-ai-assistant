"""Base OpenAPI document metadata and shared components."""

BASE_OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Maintenance Assistant API",
        "version": "1.0.0",
        "description": "Backend API for authentication, task workflows, error catalog, AI "
        "assistance, inventory forecasting and administration. The stable public "
        "API lives under /api/v1; breaking changes use a new major prefix such as "
        "/api/v2.",
    },
    "servers": [
        {"url": "http://127.0.0.1:5050/api/v1", "description": "Local development server (v1)"}
    ],
    "tags": [
        {"name": "Auth", "description": "Login and user registration"},
        {"name": "Tasks", "description": "Task lifecycle and prioritization"},
        {"name": "Errors", "description": "Error catalog and AI suggestions"},
        {"name": "Attachments", "description": "Photos and PDFs on incidents and tasks"},
        {"name": "AI", "description": "Daily briefing and AI assistant endpoints"},
        {"name": "Machines", "description": "Machine records and assistant"},
        {"name": "Inventory", "description": "Inventory and spare-part forecasts"},
        {"name": "Employees", "description": "Employee records and document management"},
        {"name": "ShiftPlans", "description": "AI-generated shift plans and calendar"},
        {"name": "Notifications", "description": "User-facing in-app notifications"},
        {"name": "Documents", "description": "Generated maintenance reports and quality reviews"},
        {"name": "Sites", "description": "Plant/site selectors for multi-plant operations"},
        {"name": "Operations", "description": "Pseudonymized event tracking and KPI summaries"},
        {"name": "Admin", "description": "Users, permissions, audit log and backups"},
        {"name": "Health", "description": "Service health probes"},
    ],
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        },
        "responses": {
            "Unauthorized": {
                "description": "Missing or invalid JWT token",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            },
            "Forbidden": {
                "description": "User lacks the required role or " "dashboard permission",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            },
            "ValidationError": {
                "description": "Invalid or incomplete request " "payload",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            },
        },
    },
}
