"""Recommended actions for closing knowledge gaps, with next steps and success criteria."""

from app.services.knowledge_gap_rows import error_gap_priority, machine_gap_rows


def knowledge_gap_actions(
    gaps,
    documents,
    error_gaps=None,
    uncovered_error_gaps=None,
    uncovered_machine_gaps=None,
):
    """Return actionable next steps for admins based on gap clusters."""
    actions = []
    for row in machine_gap_rows(gaps, documents):
        if row["coverage"] == "missing":
            actions.append(
                {
                    "type": "missing_machine_documentation",
                    "priority": "high" if row["occurrence_count"] > 1 else "medium",
                    "target_type": "machine",
                    "target_id": row.get("machine_id"),
                    "target": row["machine"],
                    "machine": row["machine"],
                    "reason": (
                        f"{row['open_gap_count']} offene Gap(s), "
                        f"{row['document_count']} passende Dokumente"
                    ),
                    "recommended_action": (
                        "Maschinendokumentation oder FAQ aus bestaetigtem Wissen ergaenzen."
                    ),
                    "next_steps": _machine_gap_next_steps(row),
                    "success_criteria": _machine_gap_success_criteria(row),
                }
            )
        elif row["coverage"] == "thin":
            actions.append(
                {
                    "type": "thin_machine_documentation",
                    "priority": "medium",
                    "target_type": "machine",
                    "target_id": row.get("machine_id"),
                    "target": row["machine"],
                    "machine": row["machine"],
                    "reason": "Wiederkehrende Fragen trotz geringer Dokumentabdeckung.",
                    "recommended_action": (
                        "Bestehende Dokumente pruefen und konkrete Stoerungsfaelle ergaenzen."
                    ),
                    "next_steps": _machine_gap_next_steps(row),
                    "success_criteria": _machine_gap_success_criteria(row),
                }
            )
    for row in error_gaps or []:
        if row["coverage"] != "missing":
            continue
        actions.append(
            {
                "type": "missing_error_documentation",
                "priority": error_gap_priority(row),
                "target_type": "error_entry",
                "target_id": row.get("error_id"),
                "target": row["error_code"],
                "error_id": row.get("error_id"),
                "error_code": row["error_code"],
                "machine": row.get("machine"),
                "title": row.get("title"),
                "reason": (
                    f"{row['open_gap_count']} offene Gap(s), "
                    f"{row['document_count']} passende Fehlerdokumente"
                ),
                "recommended_action": (
                    "Fehlercode, Ursachen, Symptome und bestaetigte Loesung "
                    "als Knowledge-Quelle dokumentieren."
                ),
                "next_steps": _error_gap_next_steps(row),
                "success_criteria": _error_gap_success_criteria(row),
            }
        )
    for row in uncovered_error_gaps or []:
        actions.append(
            {
                "type": "missing_high_impact_error_documentation",
                "priority": row["priority"],
                "target_type": "error_entry",
                "target_id": row.get("error_id"),
                "target": row["error_code"],
                "error_id": row.get("error_id"),
                "error_code": row["error_code"],
                "machine": row.get("machine"),
                "title": row.get("title"),
                "reason": row["reason"],
                "recommended_action": (
                    "Fehlercode, Symptome, Ursachen und bestaetigte Abhilfe "
                    "als Error-Knowledge-Dokument ergaenzen."
                ),
                "next_steps": _uncovered_error_next_steps(row),
                "success_criteria": _error_gap_success_criteria(row),
            }
        )
    for row in uncovered_machine_gaps or []:
        actions.append(
            {
                "type": "missing_high_impact_machine_documentation",
                "priority": row["priority"],
                "target_type": "machine",
                "target_id": row.get("machine_id"),
                "target": row["machine"],
                "machine": row["machine"],
                "reason": row["reason"],
                "recommended_action": (
                    "Kritische Maschine mit Betriebszustand, Wartungshistorie, "
                    "Stoerbildern und Wiederanlaufhinweisen als Knowledge-Quelle abdecken."
                ),
                "next_steps": _uncovered_machine_next_steps(row),
                "success_criteria": _machine_gap_success_criteria(row),
            }
        )
    if not actions and gaps:
        actions.append(
            {
                "type": "review_open_gaps",
                "priority": "low",
                "target": "knowledge_gaps",
                "reason": "Offene Gaps vorhanden, aber keine klare Maschinenluecke erkannt.",
                "recommended_action": (
                    "Top-Fragen pruefen und passende FAQ- oder RAG-Quelle anlegen."
                ),
                "next_steps": [
                    "Top-Fragen nach Wiederholung und Abteilung priorisieren.",
                    "Fehlende Antwort als freigegebenes Knowledge-Dokument erfassen.",
                    "RAG-Testfrage mit erwarteter Quelle fuer die neue Antwort anlegen.",
                ],
                "success_criteria": [
                    "Wiederholte Frage liefert mindestens eine belastbare Quelle.",
                    "Knowledge-Gap-Status kann nach fachlicher Pruefung geschlossen werden.",
                ],
            }
        )
    return actions[:10]


def _machine_gap_next_steps(row):
    """Return concrete remediation steps for a machine documentation gap."""
    machine = row.get("machine") or "die betroffene Maschine"
    steps = [
        f"Offene Fragen zu {machine} mit Instandhaltung und Produktion clustern.",
        "Bestaetigte Symptome, Ursachen und Abhilfen aus Tickets/Fehlern extrahieren.",
        "Maschinen-FAQ oder Handbuchauszug als freigegebene Knowledge-Quelle indexieren.",
    ]
    if row.get("related_error_count"):
        steps.insert(
            1,
            "Verknuepfte Fehlerhistorie pruefen und haeufige Fehlercodes priorisieren.",
        )
    return steps


def _machine_gap_success_criteria(row):
    """Return completion criteria for machine-gap remediation."""
    return [
        "Mindestens ein freigegebenes Dokument deckt Maschine und haeufige Frage ab.",
        "Top-Fragen liefern Quellen mit passender Maschinen-Metadatenabdeckung.",
        f"Offene Gap-Anzahl fuer {row.get('machine') or 'die Maschine'} sinkt im Review.",
    ]


def _error_gap_next_steps(row):
    """Return concrete remediation steps for a known error-code gap."""
    error_code = row.get("error_code") or "den Fehlercode"
    steps = [
        f"Fehler {error_code} mit bestaetigter Ursache und Abhilfe dokumentieren.",
        "Symptome, moegliche Ursachen, Sicherheitscheck und naechste Pruefschritte erfassen.",
        "Dokument mit Fehlercode, Maschine und Abteilung als Metadaten indexieren.",
        "Golden Test Question mit erwarteter Quelle fuer diesen Fehler ergaenzen.",
    ]
    if row.get("downtime_minutes"):
        steps.insert(1, "Stillstandsrelevante Eskalations- und Wiederanlaufhinweise aufnehmen.")
    return steps


def _uncovered_error_next_steps(row):
    """Return remediation steps for high-impact errors without knowledge coverage."""
    steps = _error_gap_next_steps(row)
    steps.insert(0, "High-Impact-Fehler wegen fehlender AI-Abdeckung priorisiert bearbeiten.")
    return steps


def _uncovered_machine_next_steps(row):
    """Return remediation steps for high-impact machines without knowledge coverage."""
    machine = row.get("machine") or "die kritische Maschine"
    return [
        f"Betriebs- und Wartungswissen zu {machine} aus Handbuch, Tasks und Fehlern sammeln.",
        "Typische Stoerbilder, Sicherheitspruefungen und Wiederanlaufhinweise dokumentieren.",
        "Maschinenquelle mit source_type=machine oder machine_manual indexieren.",
        "Golden Test Question mit erwarteter Maschinenquelle fuer diese Abdeckung ergaenzen.",
    ]


def _error_gap_success_criteria(row):
    """Return completion criteria for error-gap remediation."""
    error_code = row.get("error_code") or "der Fehler"
    return [
        f"{error_code} hat eine error-spezifische Knowledge-Quelle.",
        "RAG-Antwort nennt Ursache, naechste Schritte und Quelle statt No-Answer.",
        "Recall-Test findet die erwartete Quelle unter den Top-K Ergebnissen.",
    ]
