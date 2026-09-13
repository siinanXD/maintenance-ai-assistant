"""Admin prompt template management and runtime resolution services."""

import json
from dataclasses import dataclass
from string import Formatter

from flask import has_app_context
from sqlalchemy.exc import SQLAlchemyError

from app.domain_models.common import utc_now
from app.extensions import db
from app.models import AIPromptTemplate, AIPromptVersion

PROMPT_STATUSES = {"draft", "active", "archived"}


@dataclass(frozen=True)
class ResolvedPrompt:
    """Resolved prompt text and metadata for one AI workflow."""

    workflow_key: str
    system_prompt: str
    user_prompt_template: str
    template_id: int | None = None
    version_id: int | None = None
    version_number: int | None = None
    source: str = "fallback"

    def metadata(self):
        """Return prompt metadata safe for diagnostics and audit storage."""
        return {
            "prompt_template_key": self.workflow_key,
            "prompt_template_id": self.template_id,
            "prompt_version_id": self.version_id,
            "prompt_version_number": self.version_number,
            "prompt_source": self.source,
        }


def default_prompt_definitions():
    """Return default prompt templates seeded from code-level prompts."""
    from app.services.ai_prompting import (
        GENERAL_SYSTEM_PROMPT,
        json_system_prompt,
        text_system_prompt,
    )
    from app.services.ai_routing import WORKFLOW_PROFILES

    definitions = []
    for workflow_key in WORKFLOW_PROFILES:
        response_mode = (
            "text"
            if workflow_key
            in {
                "chat",
                "general_chat",
                "machine_assistant",
                "machine_summary",
                "document_text",
            }
            else "json"
        )
        system_prompt = (
            GENERAL_SYSTEM_PROMPT
            if workflow_key == "general_chat"
            else (text_system_prompt() if response_mode == "text" else json_system_prompt())
        )
        user_prompt = (
            "Kontext:\n{context}\n\nFrage:\n{question}"
            if response_mode == "text"
            else "{payload_json}"
        )
        definitions.append(
            {
                "workflow_key": workflow_key,
                "name": workflow_label(workflow_key),
                "purpose": workflow_purpose(workflow_key),
                "response_mode": response_mode,
                "variables": default_variables(response_mode),
                "system_prompt": system_prompt,
                "user_prompt_template": user_prompt,
            }
        )
    return definitions


def ensure_default_prompt_templates():
    """Create default prompt templates if the prompt tables are available."""
    if not has_app_context():
        return []
    try:
        existing = {
            template.workflow_key
            for template in AIPromptTemplate.query.with_entities(
                AIPromptTemplate.workflow_key,
            ).all()
        }
        created = []
        for definition in default_prompt_definitions():
            if definition["workflow_key"] in existing:
                continue
            template = AIPromptTemplate(
                workflow_key=definition["workflow_key"],
                name=definition["name"],
                purpose=definition["purpose"],
                response_mode=definition["response_mode"],
                variables_json=json.dumps(definition["variables"], ensure_ascii=True),
                is_active=True,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.session.add(template)
            db.session.flush()
            db.session.add(
                AIPromptVersion(
                    template_id=template.id,
                    version=1,
                    status="active",
                    system_prompt=definition["system_prompt"],
                    user_prompt_template=definition["user_prompt_template"],
                    change_note="Initialer Code-Default",
                    activated_at=utc_now(),
                    created_at=utc_now(),
                )
            )
            created.append(template)
        if created:
            db.session.commit()
        return created
    except SQLAlchemyError:
        db.session.rollback()
        return []


def list_prompt_templates(include_versions=True):
    """Return all prompt templates, creating defaults when possible."""
    ensure_default_prompt_templates()
    templates = AIPromptTemplate.query.order_by(AIPromptTemplate.workflow_key.asc()).all()
    return [template.to_dict(include_versions=include_versions) for template in templates]


def get_prompt_template(template_id):
    """Return one prompt template or raise a 404 through Flask-SQLAlchemy."""
    return db.get_or_404(AIPromptTemplate, template_id)


def create_prompt_version(template, data, user):
    """Create a draft prompt version for one template."""
    payload = normalize_prompt_version_payload(data)
    next_version = max((version.version for version in template.versions), default=0) + 1
    version = AIPromptVersion(
        template_id=template.id,
        version=next_version,
        status=payload.get("status", "draft"),
        system_prompt=payload["system_prompt"],
        user_prompt_template=payload["user_prompt_template"],
        json_schema=payload.get("json_schema", ""),
        rules_json=json.dumps(payload.get("rules", []), ensure_ascii=True),
        change_note=payload.get("change_note", ""),
        created_by=getattr(user, "id", None),
        activated_at=utc_now() if payload.get("status") == "active" else None,
        created_at=utc_now(),
    )
    db.session.add(version)
    if version.status == "active":
        archive_active_versions(template, except_version=version)
    db.session.commit()
    return version.to_dict(include_prompt=True), None, 201


def activate_prompt_version(template, version_id, user=None):
    """Activate one prompt version and archive the previous active version."""
    version = db.get_or_404(AIPromptVersion, version_id)
    if version.template_id != template.id:
        return None, {"message": "Prompt-Version gehoert nicht zu diesem Template"}, 400
    archive_active_versions(template, except_version=version)
    version.status = "active"
    version.activated_at = utc_now()
    template.is_active = True
    template.updated_at = utc_now()
    db.session.commit()
    return template.to_dict(include_versions=True), None, 200


def archive_active_versions(template, except_version=None):
    """Archive all active versions except the supplied version."""
    for version in template.versions:
        if except_version is not None and version is except_version:
            continue
        if version.status == "active":
            version.status = "archived"


def resolve_prompt(workflow_key, fallback_system_prompt, fallback_user_prompt=""):
    """Resolve the active prompt version for a workflow with a code fallback."""
    safe_workflow = str(workflow_key or "chat")[:80]
    if not has_app_context():
        return ResolvedPrompt(safe_workflow, fallback_system_prompt, fallback_user_prompt)
    try:
        template = AIPromptTemplate.query.filter_by(
            workflow_key=safe_workflow,
            is_active=True,
        ).first()
        if not template:
            return ResolvedPrompt(safe_workflow, fallback_system_prompt, fallback_user_prompt)
        version = (
            AIPromptVersion.query.filter_by(template_id=template.id, status="active")
            .order_by(AIPromptVersion.version.desc())
            .first()
        )
        if not version:
            return ResolvedPrompt(safe_workflow, fallback_system_prompt, fallback_user_prompt)
        return ResolvedPrompt(
            workflow_key=template.workflow_key,
            system_prompt=version.system_prompt or fallback_system_prompt,
            user_prompt_template=version.user_prompt_template or fallback_user_prompt,
            template_id=template.id,
            version_id=version.id,
            version_number=version.version,
            source="database",
        )
    except SQLAlchemyError:
        db.session.rollback()
        return ResolvedPrompt(safe_workflow, fallback_system_prompt, fallback_user_prompt)


def render_prompt_template(template, variables):
    """Render a prompt template with safe missing-variable behavior."""
    mapping = SafeFormatDict(
        {key: "" if value is None else value for key, value in variables.items()},
    )
    return Formatter().vformat(str(template or ""), (), mapping)


def normalize_prompt_version_payload(data):
    """Validate and normalize prompt version input."""
    payload = data if isinstance(data, dict) else {}
    system_prompt = str(payload.get("system_prompt") or "").strip()
    user_prompt_template = str(payload.get("user_prompt_template") or "").strip()
    if not system_prompt:
        raise ValueError("system_prompt is required")
    if not user_prompt_template:
        raise ValueError("user_prompt_template is required")
    status = str(payload.get("status") or "draft").strip().lower()
    if status not in PROMPT_STATUSES:
        raise ValueError("status must be draft, active or archived")
    rules = payload.get("rules") or []
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    return {
        "system_prompt": system_prompt,
        "user_prompt_template": user_prompt_template,
        "json_schema": str(payload.get("json_schema") or "").strip(),
        "rules": [str(rule)[:1000] for rule in rules],
        "change_note": str(payload.get("change_note") or "").strip()[:1000],
        "status": status,
    }


def prompt_test_preview(data):
    """Return a dry-run prompt preview for the admin test lab."""
    from app.services.ai_prompting import json_system_prompt, text_system_prompt

    payload = data if isinstance(data, dict) else {}
    workflow = str(payload.get("workflow") or "chat")
    mode = str(payload.get("mode") or "text")
    question = str(payload.get("question") or "")
    context = str(payload.get("context") or "")
    fallback_system = text_system_prompt() if mode != "json" else json_system_prompt()
    fallback_user = (
        "Kontext:\n{context}\n\nFrage:\n{question}" if mode != "json" else "{payload_json}"
    )
    resolved = resolve_prompt(workflow, fallback_system, fallback_user)
    variables = {
        "question": question,
        "context": context,
        "payload_json": json.dumps(payload.get("payload") or {}, ensure_ascii=True),
    }
    messages = [
        {"role": "system", "content": resolved.system_prompt},
        {
            "role": "user",
            "content": render_prompt_template(resolved.user_prompt_template, variables),
        },
    ]
    return {
        "workflow": workflow,
        "mode": mode,
        "messages": messages,
        "prompt": resolved.metadata(),
        "estimated_prompt_characters": sum(len(message["content"]) for message in messages),
        "live_supported": True,
    }


def workflow_label(workflow_key):
    """Return a readable label for a workflow key."""
    labels = {
        "chat": "Wartungs-Chat",
        "general_chat": "Allgemeiner Chat",
        "machine_assistant": "Maschinen-Assistent",
        "machine_summary": "Maschinen-Zusammenfassung",
        "error_analysis": "Fehleranalyse",
        "error_assistant": "Fehler-Assistent",
        "task_suggestion": "Aufgaben-Vorschlag",
        "task_prioritization": "Aufgaben-Priorisierung",
        "document_text": "Dokument-Text",
        "document_review": "Dokument-Pruefung",
        "quality_analysis": "Qualitaetsanalyse",
        "shift_planning": "Schichtplanung",
    }
    return labels.get(workflow_key, workflow_key.replace("_", " ").title())


def workflow_purpose(workflow_key):
    """Return a short admin-facing workflow purpose."""
    return f"Prompt fuer den AI-Workflow {workflow_key}."


def default_variables(response_mode):
    """Return default prompt variable descriptions for a response mode."""
    if response_mode == "json":
        return ["payload_json"]
    return ["question", "context"]


class SafeFormatDict(dict):
    """Format mapping that leaves unknown placeholders readable."""

    def __missing__(self, key):
        """Return an empty string for missing prompt variables."""
        return ""
