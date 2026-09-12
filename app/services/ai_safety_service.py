"""Local safety validation for AI maintenance answers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CRITICAL_KEYWORDS = (
    "arbeiten unter spannung",
    "unter spannung",
    "not-aus ueberbruecken",
    "notaus ueberbruecken",
    "schutzschalter ueberbruecken",
    "sicherheitsschalter ueberbruecken",
    "sensor deaktivieren",
    "schutz entfernen",
)

SAFETY_KEYWORDS = {
    "electrical_hazard": (
        "strom",
        "spannung",
        "elektrisch",
        "schaltschrank",
        "kabel",
        "lichtbogen",
    ),
    "emergency_stop": ("not-aus", "notaus", "emergency stop"),
    "safety_shutdown": (
        "abschaltung",
        "sicherheitsabschaltung",
        "schutzschalter",
        "verriegelung",
    ),
    "live_work": ("unter spannung", "arbeiten unter spannung"),
    "critical_machine_state": (
        "rauch",
        "brand",
        "ueberhitzt",
        "überhitzt",
        "stillstand",
        "blockiert",
        "leckage",
    ),
    "dangerous_action": (
        "ueberbruecken",
        "überbrücken",
        "deaktivieren",
        "abschalten umgehen",
        "schutz entfernen",
    ),
}

SAFETY_NOTICE = (
    "## Sicherheitshinweis\n"
    "- **Status:** Sicherheitsrelevante Frage erkannt.\n"
    "- **Regel:** Keine Arbeiten unter Spannung, keine Schutzfunktionen umgehen "
    "und bei Gefahr Maschine sichern sowie qualifizierte Fachkraft hinzuziehen.\n\n"
)
POST_GENERATION_SAFETY_NOTICE = (
    "## Sicherheitshinweis\n"
    "- **Status:** Die generierte Antwort enthielt sicherheitskritische "
    "Handlungsanweisungen und wurde entschaerft.\n"
    "- **Nicht ausfuehren:** Keine Arbeiten unter Spannung, keine Not-Aus- "
    "oder Schutzfunktionen umgehen und keine Anlage ohne freigegebenes "
    "Verfahren wieder in Betrieb nehmen.\n"
    "- **Sicherer naechster Schritt:** Maschine stoppen, gegen "
    "Wiedereinschalten sichern (Lockout/Tagout), Spannungsfreiheit oder "
    "Freigabe durch qualifizierte Fachkraft sicherstellen und nur "
    "freigegebene Hersteller-/Betriebsanweisungen nutzen."
)
POST_GENERATION_WARNING = (
    "\n\n## Sicherheitshinweis\n"
    "- **Pruefung:** Arbeiten nur durch qualifiziertes Fachpersonal "
    "durchfuehren lassen.\n"
    "- **Absicherung:** Maschine vor Eingriffen freischalten, gegen "
    "Wiedereinschalten sichern (Lockout/Tagout) und Spannungsfreiheit "
    "nach freigegebenem Verfahren pruefen."
)
POST_GENERATION_AUDIT_ERROR = "post_generation_safety"
REDACTED_CONFIDENCE_PENALTY = 35
WARNING_CONFIDENCE_PENALTY = 15
LOW_CONFIDENCE_THRESHOLD = 45
HIGH_CONFIDENCE_THRESHOLD = 70
LIVE_WORK_TERMS = (
    "arbeiten unter spannung",
    "unter spannung arbeiten",
    "unter spannung messen",
    "unter spannung pruefen",
    "bei anliegender spannung",
    "spannung anliegt",
)
SAFETY_BYPASS_TERMS = (
    "not-aus ueberbruecken",
    "notaus ueberbruecken",
    "not aus ueberbruecken",
    "sicherheitsschalter ueberbruecken",
    "schutzschalter ueberbruecken",
    "schutzfunktion umgehen",
    "schutzfunktionen umgehen",
    "abschaltung umgehen",
    "verriegelung deaktivieren",
    "sensor deaktivieren",
    "schutz entfernen",
)
DANGEROUS_STEP_TERMS = (
    "ueberbruecken",
    "kurzschliessen",
    "unter spannung",
    "deaktivieren",
    "schutz entfernen",
    "verriegelung entfernen",
    "abschaltung umgehen",
    "not-aus",
    "notaus",
)
UNAUTHORIZED_RELEASE_TERMS = (
    "freigabe erteilt",
    "du kannst die maschine freigeben",
    "maschine sofort freigeben",
    "anlage sofort freigeben",
    "produktion sofort freigeben",
    "ohne pruefung freigeben",
    "ohne fachkraft freigeben",
    "ohne abnahme freigeben",
)
SAFETY_RELEVANT_TERMS = (
    "strom",
    "spannung",
    "schaltschrank",
    "kabel",
    "elektrisch",
    "not-aus",
    "notaus",
    "schutzfunktion",
    "schutzschalter",
    "verriegelung",
    "sicherheitsabschaltung",
)
REQUIRED_SAFETY_NOTICE_TERMS = (
    "fachkraft",
    "fachpersonal",
    "qualifiziert",
    "elektrofachkraft",
    "lockout",
    "tagout",
    "lototo",
    "freischalten",
    "spannungsfrei",
    "spannungsfreiheit",
    "gegen wiedereinschalten",
)
STEP_PREFIX_PATTERN = re.compile(
    r"^\s*(?:[-*]|\d+[.)]|schritt\s+\d+[:.)-])\s+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SafetyAssessment:
    """Safety classification result for one AI answer."""

    safety_relevant: bool
    risk_level: str = "none"
    categories: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    blocked_actions: tuple[str, ...] = ()
    prompt_rules: tuple[str, ...] = ()
    signals: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self):
        """Return a JSON-serializable safety payload."""
        return {
            "safety_relevant": self.safety_relevant,
            "risk_level": self.risk_level,
            "categories": list(self.categories),
            "warnings": list(self.warnings),
            "blocked_actions": list(self.blocked_actions),
            "prompt_rules": list(self.prompt_rules),
            "signals": list(self.signals),
        }


@dataclass(frozen=True)
class PostGenerationSafetyResult:
    """Final safety decision for a generated AI answer."""

    answer: str
    assessment: SafetyAssessment
    action: str = "none"
    modified: bool = False
    confidence_penalty: int = 0

    def to_dict(self):
        """Return prompt-free post-generation safety metadata."""
        payload = self.assessment.to_dict()
        payload.update(
            {
                "action": self.action,
                "modified": self.modified,
                "confidence_penalty": self.confidence_penalty,
            }
        )
        return payload


def assess_ai_safety(message, query_understanding=None, sources=None):
    """Return a local safety assessment for the question and retrieval metadata."""
    text = _normalized_text(message)
    categories = [
        category
        for category, keywords in SAFETY_KEYWORDS.items()
        if any(_normalized_text(keyword) in text for keyword in keywords)
    ]
    blocked_actions = [
        keyword for keyword in CRITICAL_KEYWORDS if _normalized_text(keyword) in text
    ]
    if query_understanding and getattr(query_understanding, "is_safety", False):
        if "query_understanding" not in categories:
            categories.append("query_understanding")
    source_safety = _source_safety_signal(sources)
    if source_safety and "retrieval_source" not in categories:
        categories.append("retrieval_source")
    risk_level = _risk_level(categories, blocked_actions)
    warnings = _warnings(risk_level, categories)
    prompt_rules = _prompt_rules(risk_level, categories, blocked_actions)
    return SafetyAssessment(
        safety_relevant=bool(categories or blocked_actions),
        risk_level=risk_level,
        categories=tuple(categories),
        warnings=tuple(warnings),
        blocked_actions=tuple(blocked_actions),
        prompt_rules=tuple(prompt_rules),
        signals=tuple(categories + [f"blocked:{item}" for item in blocked_actions]),
    )


def apply_safety_warning(answer, assessment):
    """Return an answer prefixed with a safety warning when needed."""
    if not assessment or not assessment.safety_relevant:
        return answer
    answer_text = str(answer or "").strip()
    if answer_text.startswith(SAFETY_NOTICE.strip()):
        return answer_text
    return f"{SAFETY_NOTICE}{answer_text}".strip()


def apply_safety_payload_warning(answer, safety_payload):
    """Return an answer prefixed when a serialized safety payload is relevant."""
    if not isinstance(safety_payload, dict) or not safety_payload.get("safety_relevant"):
        return answer
    answer_text = str(answer or "").strip()
    if answer_text.startswith(SAFETY_NOTICE.strip()):
        return answer_text
    return f"{SAFETY_NOTICE}{answer_text}".strip()


def safety_context_block(assessment):
    """Return a compact prompt context block for safety-relevant answers."""
    if not assessment or not assessment.safety_relevant:
        return ""
    lines = [
        "Sicherheitskontext:",
        f"- Risikostufe: {assessment.risk_level}",
        "- Keine gefaehrlichen Handlungsanweisungen erfinden.",
        "- Nur sichere, organisatorische und pruefende Schritte nennen.",
    ]
    if assessment.categories:
        lines.append(f"- Kategorien: {', '.join(assessment.categories)}")
    if assessment.blocked_actions:
        lines.append("- Gefaehrliche angefragte Aktionen nicht anleiten.")
    return "\n".join(lines)


def enforce_post_generation_safety(answer, safety_payload=None):
    """Return a final safety-checked answer without persisting prompt content."""
    answer_text = str(answer or "").strip()
    body_text = _strip_known_safety_notices(answer_text)
    normalized_body = _normalized_text(body_text)
    normalized_answer = _normalized_text(answer_text)
    categories, blocked_actions, warnings = _post_generation_findings(
        body_text,
        normalized_body,
        normalized_answer,
        safety_payload,
    )
    if not categories and not blocked_actions:
        return PostGenerationSafetyResult(
            answer=answer_text,
            assessment=SafetyAssessment(safety_relevant=False),
        )

    risk_level = _risk_level(categories, blocked_actions)
    assessment = SafetyAssessment(
        safety_relevant=True,
        risk_level=risk_level,
        categories=tuple(categories),
        warnings=tuple(warnings),
        blocked_actions=tuple(blocked_actions),
        prompt_rules=(
            "Finale Antwortpruefung: keine gefaehrlichen Handlungsanweisungen ausgeben.",
        ),
        signals=tuple(categories + [f"blocked:{item}" for item in blocked_actions]),
    )
    if blocked_actions or _requires_redaction(categories):
        return PostGenerationSafetyResult(
            answer=POST_GENERATION_SAFETY_NOTICE,
            assessment=assessment,
            action="redacted",
            modified=True,
            confidence_penalty=REDACTED_CONFIDENCE_PENALTY,
        )
    if "post_missing_loto_notice" in categories:
        return PostGenerationSafetyResult(
            answer=_append_post_generation_warning(answer_text),
            assessment=assessment,
            action="warning_added",
            modified=True,
            confidence_penalty=WARNING_CONFIDENCE_PENALTY,
        )
    return PostGenerationSafetyResult(
        answer=answer_text,
        assessment=assessment,
        action="flagged",
        modified=False,
        confidence_penalty=WARNING_CONFIDENCE_PENALTY,
    )


def apply_post_generation_safety_to_result(result, safety_result):
    """Attach post-generation safety metadata and confidence penalty to a result."""
    if not isinstance(result, dict) or safety_result is None:
        return result
    result["answer"] = safety_result.answer
    if not safety_result.assessment.safety_relevant:
        return result
    diagnostics = result.setdefault("diagnostics", {})
    diagnostics["post_generation_safety"] = safety_result.to_dict()
    diagnostics["safety"] = _merge_safety_payload(
        diagnostics.get("safety"),
        safety_result.assessment.to_dict(),
    )
    diagnostics["error"] = diagnostics.get("error") or POST_GENERATION_AUDIT_ERROR
    _apply_confidence_penalty(result, safety_result.confidence_penalty)
    return result


def reapply_post_generation_penalty(result):
    """Re-apply a stored post-generation confidence penalty after recomputation.

    The workflow validation node already redacts unsafe answers and lowers the
    confidence. When a later step recalculates confidence from scratch, the
    redacted answer no longer triggers findings, so the stored penalty would be
    lost. This keeps the diagnostics and the final confidence consistent.
    """
    if not isinstance(result, dict):
        return result
    diagnostics = result.get("diagnostics") or {}
    stored = diagnostics.get("post_generation_safety")
    if not isinstance(stored, dict):
        return result
    penalty = _bounded_int(stored.get("confidence_penalty"))
    if not penalty:
        return result
    confidence = result.get("confidence") or diagnostics.get("confidence")
    if not isinstance(confidence, dict):
        return result
    reasons = confidence.get("reasons") or []
    if any("Post-generation Safety" in str(reason) for reason in reasons):
        return result
    _apply_confidence_penalty(result, penalty)
    return result


def _source_safety_signal(sources):
    """Return whether source metadata suggests safety relevance."""
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        title = _normalized_text(source.get("title"))
        reason = _normalized_text(source.get("reason"))
        if any(keyword in f"{title} {reason}" for keyword in ("sicherheit", "not-aus")):
            return True
    return False


def _risk_level(categories, blocked_actions):
    """Return a coarse local safety risk level."""
    if blocked_actions or "live_work" in categories:
        return "critical"
    if {
        "electrical_hazard",
        "emergency_stop",
        "safety_shutdown",
        "dangerous_action",
    } & set(categories):
        return "high"
    if categories:
        return "caution"
    return "none"


def _warnings(risk_level, categories):
    """Return concise safety warnings for diagnostics and UI."""
    if risk_level == "critical":
        return (
            "Keine Anleitung fuer Arbeiten unter Spannung oder Umgehen von Schutzfunktionen.",
            "Maschine sichern und qualifizierte Elektro-/Sicherheitsfachkraft hinzuziehen.",
        )
    if risk_level == "high":
        return (
            "Sicherheitsrelevanten Zustand vorsichtig behandeln.",
            "Nur freigegebene Verfahren und Fachpersonal nutzen.",
        )
    if categories:
        return ("Sicherheitsbezug erkannt; Antwort fachlich pruefen.",)
    return ()


def _prompt_rules(risk_level, categories, blocked_actions):
    """Return safety prompt rules for answer generation."""
    if risk_level == "none":
        return ()
    rules = [
        "Sicherheitsrelevante Antwort: keine riskanten Schritt-fuer-Schritt-Anweisungen.",
        "Bei Unsicherheit Maschine sichern und Fachkraft hinzuziehen.",
    ]
    if blocked_actions:
        rules.append("Anfragen zum Umgehen von Schutzfunktionen ablehnen.")
    if "electrical_hazard" in categories or "live_work" in categories:
        rules.append("Keine Arbeiten unter Spannung anleiten.")
    return tuple(rules)


def _post_generation_findings(
    body_text,
    normalized_body,
    normalized_answer,
    safety_payload,
):
    """Return categories, blocked actions, and warnings from final answer text."""
    categories = []
    blocked_actions = []
    warnings = []
    _extend_findings_for_terms(
        normalized_body,
        LIVE_WORK_TERMS,
        "post_live_work",
        categories,
        blocked_actions,
    )
    _extend_findings_for_terms(
        normalized_body,
        SAFETY_BYPASS_TERMS,
        "post_safety_bypass",
        categories,
        blocked_actions,
    )
    _extend_findings_for_terms(
        normalized_body,
        UNAUTHORIZED_RELEASE_TERMS,
        "post_unauthorized_release",
        categories,
        blocked_actions,
    )
    if _has_dangerous_step_sequence(body_text):
        categories.append("post_dangerous_steps")
        blocked_actions.append("dangerous_step_by_step")
    if _requires_safety_notice(normalized_body, safety_payload) and not _has_required_notice(
        normalized_answer,
    ):
        categories.append("post_missing_loto_notice")
        warnings.append("Finale Antwort enthielt keinen ausreichenden Fachpersonal-/LOTO-Hinweis.")
    if categories and not warnings:
        warnings.append("Finale Antwort enthielt sicherheitskritische Maintenance-Inhalte.")
    return _dedupe(categories), _dedupe(blocked_actions), _dedupe(warnings)


def _extend_findings_for_terms(
    normalized_text,
    terms,
    category,
    categories,
    blocked_actions,
):
    """Add a finding when unsafe terms appear outside clear negative wording."""
    for term in terms:
        normalized_term = _normalized_text(term)
        if _contains_unsafe_term(normalized_text, normalized_term):
            categories.append(category)
            blocked_actions.append(category)


def _contains_unsafe_term(normalized_text, normalized_term):
    """Return whether a term appears without a nearby safety negation."""
    if not normalized_term or normalized_term not in normalized_text:
        return False
    for match in re.finditer(re.escape(normalized_term), normalized_text):
        prefix = normalized_text[max(0, match.start() - 35) : match.start()]
        if any(
            negation in prefix
            for negation in (
                "keine ",
                "nicht ",
                "niemals ",
                "nicht ausfuehren ",
                "darf nicht ",
                "duerfen nicht ",
            )
        ):
            continue
        return True
    return False


def _has_dangerous_step_sequence(text):
    """Return whether numbered or listed steps contain unsafe instructions."""
    dangerous_step_count = 0
    for line in str(text or "").splitlines():
        if not STEP_PREFIX_PATTERN.match(line):
            continue
        normalized_line = _normalized_text(line)
        if any(
            _contains_unsafe_term(normalized_line, _normalized_text(term))
            for term in DANGEROUS_STEP_TERMS
        ):
            dangerous_step_count += 1
    return dangerous_step_count >= 1 and _has_multiple_step_lines(text)


def _has_multiple_step_lines(text):
    """Return whether the text looks like a step-by-step instruction."""
    step_lines = [line for line in str(text or "").splitlines() if STEP_PREFIX_PATTERN.match(line)]
    return len(step_lines) >= 2


def _requires_safety_notice(normalized_body, safety_payload):
    """Return whether safety-sensitive content needs an explicit safety notice."""
    if isinstance(safety_payload, dict) and safety_payload.get("safety_relevant"):
        return True
    return any(term in normalized_body for term in SAFETY_RELEVANT_TERMS)


def _has_required_notice(normalized_answer):
    """Return whether the answer contains Fachpersonal or Lockout/Tagout safeguards."""
    return any(term in normalized_answer for term in REQUIRED_SAFETY_NOTICE_TERMS)


def _requires_redaction(categories):
    """Return whether post-generation categories require replacing the answer."""
    redaction_categories = {
        "post_live_work",
        "post_safety_bypass",
        "post_dangerous_steps",
        "post_unauthorized_release",
    }
    return bool(set(categories) & redaction_categories)


def _append_post_generation_warning(answer):
    """Append a safety warning exactly once."""
    answer_text = str(answer or "").strip()
    notice = POST_GENERATION_WARNING.strip()
    if notice in answer_text:
        return answer_text
    return f"{answer_text}{POST_GENERATION_WARNING}".strip()


def _strip_known_safety_notices(answer):
    """Remove locally generated safety prefaces before scanning instructions."""
    text = str(answer or "").strip()
    for notice in (SAFETY_NOTICE.strip(), POST_GENERATION_SAFETY_NOTICE.strip()):
        if text.startswith(notice):
            return text[len(notice) :].strip()
    return text


def _merge_safety_payload(base_payload, post_payload):
    """Merge serialized pre-generation and post-generation safety metadata."""
    base = dict(base_payload) if isinstance(base_payload, dict) else {}
    post = post_payload if isinstance(post_payload, dict) else {}
    return {
        "safety_relevant": bool(base.get("safety_relevant") or post.get("safety_relevant")),
        "risk_level": _max_risk_level(base.get("risk_level"), post.get("risk_level")),
        "categories": _dedupe(_as_list(base.get("categories")) + _as_list(post.get("categories"))),
        "warnings": _dedupe(_as_list(base.get("warnings")) + _as_list(post.get("warnings"))),
        "blocked_actions": _dedupe(
            _as_list(base.get("blocked_actions")) + _as_list(post.get("blocked_actions")),
        ),
        "prompt_rules": _dedupe(
            _as_list(base.get("prompt_rules")) + _as_list(post.get("prompt_rules")),
        ),
        "signals": _dedupe(_as_list(base.get("signals")) + _as_list(post.get("signals"))),
    }


def _apply_confidence_penalty(result, penalty):
    """Lower confidence score after a post-generation safety intervention."""
    if not penalty:
        return
    diagnostics = result.setdefault("diagnostics", {})
    confidence = result.get("confidence") or diagnostics.get("confidence")
    if not isinstance(confidence, dict):
        return
    adjusted = dict(confidence)
    score = _bounded_int(adjusted.get("score")) - int(penalty)
    adjusted["score"] = max(0, min(100, score))
    adjusted["level"] = _confidence_level(adjusted["score"])
    adjusted["warning"] = _confidence_warning(adjusted["level"], adjusted.get("warning"))
    reasons = list(adjusted.get("reasons") or [])
    reasons.append("Post-generation Safety-Pruefung hat Confidence reduziert.")
    adjusted["reasons"] = _dedupe(reasons)
    result["confidence"] = adjusted
    diagnostics["confidence"] = adjusted
    diagnostics["confidence_score"] = adjusted["score"]
    diagnostics["confidence_level"] = adjusted["level"]


def _confidence_level(score):
    """Return the public confidence level for a numeric score."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _confidence_warning(level, existing_warning=""):
    """Return the confidence warning after a post-generation safety penalty."""
    if level != "low":
        return existing_warning or ""
    return existing_warning or (
        "Antwort wurde wegen sicherheitskritischer Inhalte reduziert oder ergaenzt."
    )


def _max_risk_level(first, second):
    """Return the highest risk level from two serialized safety payloads."""
    order = {"none": 0, "caution": 1, "high": 2, "critical": 3}
    first_value = str(first or "none")
    second_value = str(second or "none")
    return first_value if order.get(first_value, 0) >= order.get(second_value, 0) else second_value


def _bounded_int(value):
    """Return an integer score within the expected confidence range."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _as_list(value):
    """Return list-like values as a list of strings."""
    if not isinstance(value, list | tuple | set):
        return []
    return [str(item) for item in value if item not in (None, "")]


def _dedupe(items):
    """Return items without duplicates while preserving order."""
    unique = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _normalized_text(value):
    """Return normalized text for local matching."""
    text = " ".join(str(value or "").strip().lower().split())
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ã¤": "ae",
        "Ã¶": "oe",
        "Ã¼": "ue",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = text.translate(
        str.maketrans(
            {
                "\u00e4": "ae",
                "\u00f6": "oe",
                "\u00fc": "ue",
                "\u00df": "ss",
            }
        )
    )
    return text
