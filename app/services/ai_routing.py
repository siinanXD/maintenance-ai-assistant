"""Central model routing, token budgets and AI usage metadata helpers."""

import os
import re
import time
from dataclasses import asdict, dataclass

from flask import current_app

DEFAULT_MODELS = {
    "fast": "gpt-4o-mini",
    "balanced": "gpt-4o-mini",
    "quality": "gpt-5-mini",
}

WORKFLOW_PROFILES = {
    "task_suggestion": {"tier": "fast", "temperature": 0.1, "max_tokens": 520},
    "task_prioritization": {"tier": "fast", "temperature": 0.0, "max_tokens": 900},
    "error_analysis": {"tier": "balanced", "temperature": 0.1, "max_tokens": 700},
    "error_assistant": {"tier": "balanced", "temperature": 0.1, "max_tokens": 650},
    "document_text": {"tier": "balanced", "temperature": 0.2, "max_tokens": 600},
    "document_review": {"tier": "balanced", "temperature": 0.1, "max_tokens": 900},
    "chat": {"tier": "balanced", "temperature": 0.2, "max_tokens": 750},
    "agent": {"tier": "balanced", "temperature": 0.1, "max_tokens": 900},
    "general_chat": {"tier": "balanced", "temperature": 0.2, "max_tokens": 260},
    "machine_assistant": {"tier": "balanced", "temperature": 0.2, "max_tokens": 750},
    "machine_summary": {"tier": "balanced", "temperature": 0.1, "max_tokens": 600},
    "shift_planning": {"tier": "balanced", "temperature": 0.1, "max_tokens": 1800},
    "quality_analysis": {"tier": "quality", "temperature": 0.1, "max_tokens": 1400},
}


@dataclass(frozen=True)
class AIModelProfile:
    """Runtime profile for one AI workflow call."""

    workflow: str
    tier: str
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    max_retries: int

    def to_dict(self):
        """Return the profile as a JSON-safe dictionary."""
        return asdict(self)


def workflow_profile(workflow, legacy_model=None):
    """Return the configured model profile for a workflow."""
    workflow_key = str(workflow or "chat")
    settings = WORKFLOW_PROFILES.get(workflow_key, WORKFLOW_PROFILES["chat"])
    tier = str(settings["tier"])
    model = _workflow_model(workflow_key) or _tier_model(tier, legacy_model)
    default_timeout = _workflow_default_timeout(workflow_key)
    default_retries = _workflow_default_retries(workflow_key)
    return AIModelProfile(
        workflow=workflow_key,
        tier=tier,
        model=model,
        temperature=_workflow_float(
            workflow_key,
            "TEMPERATURE",
            float(settings["temperature"]),
        ),
        max_tokens=_workflow_int(
            workflow_key,
            "MAX_TOKENS",
            int(settings["max_tokens"]),
        ),
        timeout_seconds=_workflow_float(
            workflow_key,
            "TIMEOUT_SECONDS",
            default_timeout,
        ),
        max_retries=_workflow_int(
            workflow_key,
            "MAX_RETRIES",
            default_retries,
        ),
    )


def openai_client_options(profile=None, allow_base_url=True):
    """Return OpenAI client options for timeout, retry, and optional base URL control."""
    if profile is not None:
        options = {
            "timeout": profile.timeout_seconds,
            "max_retries": profile.max_retries,
        }
    else:
        options = {
            "timeout": float(current_app.config.get("AI_TIMEOUT_SECONDS", 10)),
            "max_retries": int(current_app.config.get("AI_MAX_RETRIES", 1)),
        }
    base_url = str(current_app.config.get("AI_BASE_URL") or "").strip()
    if allow_base_url and base_url:
        options["base_url"] = base_url
    return options


def call_timer():
    """Return a monotonic timestamp for AI latency measurement."""
    return time.perf_counter()


def elapsed_ms(started_at):
    """Return elapsed milliseconds for a started monotonic timer."""
    return int(round((time.perf_counter() - started_at) * 1000))


def completion_metadata(provider_name, profile, completion, latency_ms):
    """Return safe metadata for one provider completion."""
    usage = _completion_usage(completion)
    estimated_cost = estimate_cost_usd(
        profile.model,
        usage["input_tokens"],
        usage["output_tokens"],
        usage["cached_tokens"],
    )
    return {
        "provider": provider_name,
        "workflow": profile.workflow,
        "model": profile.model,
        "model_tier": profile.tier,
        "temperature": profile.temperature,
        "max_tokens": profile.max_tokens,
        "latency_ms": latency_ms,
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "cached_tokens": usage["cached_tokens"],
        "total_tokens": usage["total_tokens"],
        "estimated_cost_usd": estimated_cost,
    }


def local_metadata(provider_name="mock", workflow="local"):
    """Return safe metadata for a local or mock AI response."""
    profile = workflow_profile(workflow)
    return {
        "provider": provider_name,
        "workflow": workflow,
        "model": "local" if provider_name == "local" else profile.model,
        "model_tier": "local" if provider_name == "local" else profile.tier,
        "temperature": 0.0,
        "max_tokens": 0,
        "latency_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }


def estimate_cost_usd(model, input_tokens, output_tokens, cached_tokens=0):
    """Estimate call cost from optional per-model environment price settings."""
    safe_model = _safe_price_key(model)
    input_price = _price_setting(safe_model, "INPUT")
    output_price = _price_setting(safe_model, "OUTPUT")
    cached_price = _price_setting(safe_model, "CACHED_INPUT")
    billable_input_tokens = max(int(input_tokens or 0) - int(cached_tokens or 0), 0)
    cached_input_tokens = int(cached_tokens or 0)
    cost = (
        (billable_input_tokens / 1_000_000) * input_price
        + (cached_input_tokens / 1_000_000) * cached_price
        + (int(output_tokens or 0) / 1_000_000) * output_price
    )
    return round(cost, 6)


def ai_price_configuration_status():
    """Return whether AI token price settings are configured."""
    keys = [
        key
        for key, value in os.environ.items()
        if key.startswith("AI_PRICE_") and key.endswith("_PER_1M") and str(value or "").strip()
    ]
    return {
        "configured": bool(keys),
        "configured_keys": sorted(keys),
        "message": "" if keys else "Kosten nicht konfiguriert",
    }


def _workflow_model(workflow):
    """Return an optional workflow-specific model override."""
    key = f"OPENAI_MODEL_{_safe_price_key(workflow)}"
    return _configured_text(current_app.config.get(key)) or _configured_text(os.getenv(key))


def _tier_model(tier, legacy_model=None):
    """Return the configured model for a routing tier."""
    key = f"OPENAI_MODEL_{tier.upper()}"
    return (
        _configured_text(current_app.config.get(key))
        or _configured_text(legacy_model)
        or _configured_text(current_app.config.get("OPENAI_MODEL"))
        or _configured_text(os.getenv(key))
        or _configured_text(os.getenv("OPENAI_MODEL"))
        or DEFAULT_MODELS[tier]
    )


def _configured_text(value):
    """Return stripped config text, or an empty string when unset."""
    return str(value or "").strip()


def _workflow_default_timeout(workflow):
    """Return the default timeout for one workflow."""
    if workflow == "task_prioritization":
        return float(current_app.config.get("AI_TASK_PRIORITIZATION_TIMEOUT_SECONDS", 6.0))
    return float(current_app.config.get("AI_TIMEOUT_SECONDS", 10))


def _workflow_default_retries(workflow):
    """Return the default retry count for one workflow."""
    if workflow == "task_prioritization":
        return int(current_app.config.get("AI_TASK_PRIORITIZATION_MAX_RETRIES", 0))
    return int(current_app.config.get("AI_MAX_RETRIES", 1))


def _workflow_float(workflow, suffix, default):
    """Return a workflow-specific float override or a default."""
    key = f"AI_{_safe_price_key(workflow)}_{suffix}"
    try:
        return float(current_app.config.get(key) or os.getenv(key) or default)
    except (TypeError, ValueError):
        return default


def _workflow_int(workflow, suffix, default):
    """Return a workflow-specific integer override or a default."""
    key = f"AI_{_safe_price_key(workflow)}_{suffix}"
    try:
        return int(current_app.config.get(key) or os.getenv(key) or default)
    except (TypeError, ValueError):
        return default


def _completion_usage(completion):
    """Extract token usage from an OpenAI completion object."""
    usage = _get_value(completion, "usage", {})
    input_tokens = _int_value(
        _get_value(usage, "prompt_tokens", _get_value(usage, "input_tokens", 0))
    )
    output_tokens = _int_value(
        _get_value(
            usage,
            "completion_tokens",
            _get_value(usage, "output_tokens", 0),
        )
    )
    total_tokens = _int_value(_get_value(usage, "total_tokens", input_tokens + output_tokens))
    details = _get_value(
        usage,
        "prompt_tokens_details",
        _get_value(usage, "input_tokens_details", {}),
    )
    cached_tokens = _int_value(_get_value(details, "cached_tokens", 0))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }


def _get_value(source, key, default=None):
    """Return an attribute or mapping value from a provider object."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _int_value(value):
    """Return a safe integer value."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _price_setting(safe_model, price_type):
    """Return an optional price-per-million-token setting for a model."""
    key = f"AI_PRICE_{safe_model}_{price_type}_PER_1M"
    try:
        return float(os.getenv(key, "0") or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_price_key(value):
    """Return an uppercase environment-safe key segment."""
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")
