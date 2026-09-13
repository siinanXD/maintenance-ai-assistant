"""Server-rendered web page routes."""

from flask import Blueprint, abort, redirect, render_template, request

from app.shiftplans.templates import list_shift_templates

web_bp = Blueprint("web", __name__)

AI_ADMIN_VIEWS = {
    "overview": "/admin/ai",
    "rag_board": "/admin/ai/rag-board",
    "source_check": "/admin/ai/source-check",
    "prompt_faq": "/admin/ai/prompt-faq",
    "effectiveness": "/admin/ai/effectiveness",
    "technical": "/admin/ai/technical",
}

# Deprecated legacy Admin-AI page paths kept for old bookmarks and clients.
# Remove these redirects after a documented deprecation phase.
AI_ADMIN_LEGACY_REDIRECTS = {
    "/admin/ai/prompts": "/admin/ai/prompt-faq",
    "/admin/ai/faq": "/admin/ai/prompt-faq",
    "/admin/ai/lab": "/admin/ai/source-check",
    "/admin/ai/costs": "/admin/ai/effectiveness",
    "/admin/ai/feedback": "/admin/ai/effectiveness",
    "/admin/ai/models": "/admin/ai#ai-models",
    "/admin/ai/knowledge": "/admin/ai/rag-board",
    "/admin/ai/training": "/admin/ai/rag-board",
    "/admin/ai/retrieval": "/admin/ai/technical",
    "/admin/ai/diagnostics": "/admin/ai/technical",
    "/admin/ai/indexing": "/admin/ai/technical",
}

SHIFT_MODEL_LABELS = {
    "one_shift": "Tagschicht",
    "two_shift": "2-Schicht Früh/Spät",
    "three_shift": "3-Schicht Früh/Spät/Nacht",
    "teilkonti": "Teilkonti",
    "vollkonti_4": "Vollkonti 4-Schicht",
    "vollkonti_5": "Vollkonti 5-Schicht",
}


def shift_model_options():
    """Return pre-rendered shift model metadata for the shiftplan page."""
    options = []
    for template in list_shift_templates():
        shifts_summary = ", ".join(
            f"{shift.display_name} {shift.start_time}-{shift.end_time}" for shift in template.shifts
        )
        rotation_label = (
            "Vorwärtsrotation Früh → Spät → Nacht"
            if template.rotation_direction == "forward"
            else "Feste Tagschicht"
        )
        options.append(
            {
                "key": template.key,
                "label": SHIFT_MODEL_LABELS.get(template.key, template.display_name),
                "display_name": template.display_name,
                "description": template.description,
                "shifts_summary": shifts_summary,
                "team_count": template.team_count,
                "weekend_operation": template.weekend_operation,
                "weekend_label": (
                    "Wochenendbetrieb aktiv" if template.weekend_operation else "Montag bis Freitag"
                ),
                "rotation_direction": template.rotation_direction,
                "rotation_label": rotation_label,
                "recommended_rest_hours": template.recommended_rest_hours,
            }
        )
    return options


def render_ai_admin_page(view_name):
    """Render a specific AI admin subpage inside the shared shell."""
    return render_template(
        "admin_ai.html",
        admin_ai_view=view_name,
        ai_admin_views=AI_ADMIN_VIEWS,
    )


@web_bp.get("/admin/ai/prompts")
@web_bp.get("/admin/ai/faq")
@web_bp.get("/admin/ai/lab")
@web_bp.get("/admin/ai/costs")
@web_bp.get("/admin/ai/feedback")
@web_bp.get("/admin/ai/models")
@web_bp.get("/admin/ai/knowledge")
@web_bp.get("/admin/ai/training")
@web_bp.get("/admin/ai/retrieval")
@web_bp.get("/admin/ai/diagnostics")
@web_bp.get("/admin/ai/indexing")
def admin_ai_legacy_redirect_page():
    """Redirect deprecated Admin-AI legacy pages to canonical sections."""
    target_path = AI_ADMIN_LEGACY_REDIRECTS.get(request.path)
    if target_path is None:
        abort(404)
    return redirect(target_path, code=302)


@web_bp.get("/")
def dashboard():
    """Render the dashboard page."""
    return render_template("dashboard.html")


@web_bp.get("/login")
def login_page():
    """Render the login page."""
    return render_template("login.html")


@web_bp.get("/api-docs")
def api_docs_page():
    """Render the API documentation page."""
    return render_template("api_docs.html")


@web_bp.get("/tasks")
def tasks_page():
    """Render the task management page."""
    return render_template("tasks.html")


@web_bp.get("/errors")
def errors_page():
    """Render the error catalog page."""
    return render_template("errors.html")


@web_bp.get("/admin/users")
def admin_users_page():
    """Render the admin user management page."""
    return render_template("admin_users.html")


@web_bp.get("/admin/ai")
def admin_ai_page():
    """Render the AI administration overview page."""
    return render_ai_admin_page("overview")


@web_bp.get("/admin/ai/rag-board")
def admin_ai_rag_board_page():
    """Render the RAG board administration page."""
    return render_ai_admin_page("rag_board")


@web_bp.get("/admin/ai/source-check")
def admin_ai_source_check_page():
    """Render the AI source check administration page."""
    return render_ai_admin_page("source_check")


@web_bp.get("/admin/ai/prompt-faq")
def admin_ai_prompt_faq_page():
    """Render the combined AI prompt and FAQ administration page."""
    return render_ai_admin_page("prompt_faq")


@web_bp.get("/admin/ai/effectiveness")
def admin_ai_effectiveness_page():
    """Render the AI cost and effectiveness administration page."""
    return render_ai_admin_page("effectiveness")


@web_bp.get("/admin/ai/technical")
def admin_ai_technical_page():
    """Render the AI technical diagnostics page."""
    return render_ai_admin_page("technical")


@web_bp.get("/employees")
def employees_page():
    """Render the employee page."""
    return render_template("employees.html")


@web_bp.get("/shiftplans")
def shiftplans_page():
    """Render the shift planning page."""
    return render_template(
        "shiftplans.html",
        shift_model_options=shift_model_options(),
    )


@web_bp.get("/machines")
def machines_page():
    """Render the machine page."""
    return render_template("machines.html")


@web_bp.get("/machines/<int:machine_id>")
def machine_detail_page(machine_id):
    """Render the machine-centered detail page."""
    return render_template("machine_detail.html", machine_id=machine_id)


@web_bp.get("/maintenance")
def maintenance_page():
    """Render the inspections and maintenance plans page."""
    return render_template("maintenance.html")


@web_bp.get("/m/<int:machine_id>")
def machine_short_link(machine_id):
    """Resolve the short link printed on machine QR labels."""
    return redirect(f"/machines/{machine_id}")


@web_bp.get("/inventory")
def inventory_page():
    """Render the inventory page."""
    return render_template("inventory.html")


@web_bp.get("/documents")
def documents_page():
    """Render the generated documents overview."""
    return render_template("documents.html")


@web_bp.get("/handover")
def handover_page():
    """Render the shift handover page."""
    return render_template("handover.html")


@web_bp.get("/vacations")
def vacations_page():
    """Render the vacation planning page."""
    return render_template("vacations.html")
