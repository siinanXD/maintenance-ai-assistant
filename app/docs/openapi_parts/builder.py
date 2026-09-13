"""Build the curated OpenAPI specification from small fragments."""

from copy import deepcopy

from app.docs.openapi_extensions import ADDITIONAL_PATHS, ADDITIONAL_SCHEMAS
from app.docs.openapi_parts.base import BASE_OPENAPI_SPEC
from app.docs.openapi_parts.paths_auth_admin import PATHS_AUTH_ADMIN
from app.docs.openapi_parts.paths_documents_inventory import PATHS_DOCUMENTS_INVENTORY
from app.docs.openapi_parts.paths_field_work import PATHS_FIELD_WORK, SCHEMAS_FIELD_WORK
from app.docs.openapi_parts.paths_tasks_errors_ai import PATHS_TASKS_ERRORS_AI
from app.docs.openapi_parts.paths_workforce_shiftplans import PATHS_WORKFORCE_SHIFTPLANS
from app.docs.openapi_parts.schemas_1 import SCHEMAS_1
from app.docs.openapi_parts.schemas_2 import SCHEMAS_2
from app.docs.openapi_parts.schemas_3 import SCHEMAS_3
from app.docs.openapi_parts.schemas_4 import SCHEMAS_4


def build_openapi_spec():
    """Return a fresh OpenAPI specification dictionary."""
    spec = deepcopy(BASE_OPENAPI_SPEC)
    schemas = spec["components"].setdefault("schemas", {})
    schemas.update(SCHEMAS_1)
    schemas.update(SCHEMAS_2)
    schemas.update(SCHEMAS_3)
    schemas.update(SCHEMAS_4)
    schemas.update(ADDITIONAL_SCHEMAS)
    schemas.update(SCHEMAS_FIELD_WORK)
    paths = spec.setdefault("paths", {})
    paths.update(PATHS_AUTH_ADMIN)
    paths.update(PATHS_TASKS_ERRORS_AI)
    paths.update(PATHS_WORKFORCE_SHIFTPLANS)
    paths.update(PATHS_DOCUMENTS_INVENTORY)
    paths.update(ADDITIONAL_PATHS)
    paths.update(PATHS_FIELD_WORK)
    return spec
