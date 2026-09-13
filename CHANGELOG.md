# Changelog

All notable changes to the Maintenance Assistant are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Photos and PDFs on incidents and tasks (`/api/v1/attachments`), type detected
  from content, camera capture on phones
- QR label per machine (`/api/v1/machines/{id}/qr.svg`, short link `/m/{id}`)
- Work order from incident (`task.error_entry_id`), closing the incident when the
  order is completed
- Spare-part withdrawals per work order, goods receipts, movement history and
  reorder suggestions (`/api/v1/inventory/reorder`)
- Inspections page `/maintenance`: plans with legal basis, execution records
  with result, follow-up orders, re-test after a failed inspection
- Availability, MTBF and MTTR per machine over 90 days
- Static assets are versioned by content hash instead of manual `?v=` strings

### Removed
- Dead code found by AST, import-graph and CSS scans: 44 unused Python
  definitions, 14 unreachable React files, 100+ unused exports, 546 unused CSS
  rules; the unused LangGraph answer-generation path; the `/ai/agent`,
  `/ai/chat/templates`, `/ai/incident-timeline` and `/ai/order-plan` endpoints;
  legacy Admin-AI redirects
- Help boxes and placeholder KPI cards without real data on list pages

### Changed
- The chat is agent-only: `POST /api/v1/ai/chat` and `POST /api/v1/ai/agent`
  run the same LangGraph tool loop. The rule-based router (`app/ai/intent.py`,
  `app/ai/context.py`, `app/ai/chat_answers.py`, `app/ai/handlers/`, the
  `ai_*structured*` services, about 9.7k lines of keyword heuristics) and the
  structured fast path were removed together with the `AI_CHAT_MODE`,
  `AI_AGENT_STRUCTURED_FAST_PATH` and `AI_GENERATE_WITHOUT_EVIDENCE` settings
- Structured questions are answered by ten parameterized tools with explicit
  filters (`list_tasks`, `list_incidents`, `count_records`, `list_employees`,
  `list_employee_documents`, `list_vacations`, `list_documents`,
  `list_shift_entries`, `list_inventory`, `machine_incident_report`) backed by
  pure query cores in `app/agent/queries/`; permission semantics are unchanged
- `search_knowledge` runs the hybrid LangGraph retrieval (`build_rag_context`)
  and returns the grounded no-answer text when nothing is found; chat responses
  carry `answer_category` and `structured_context`, follow-up questions reuse
  the persisted structured scope, knowledge gaps are tracked for `rag` answers
- The offline mock policy extracts tool arguments, issues one `count_records`
  call per scope and echoes prepared `answer_markdown`; golden tool cases cover
  every tool

### Added
- LangGraph checkpointers persist agent session memory
  (`AI_AGENT_CHECKPOINTER`: postgres, sqlite, memory, none)
- Tool-using maintenance agent (`POST /api/v1/ai/agent`):
  LangGraph loop with safety guard, permission-gated tool registry over the
  existing services, provider tool calling (OpenAI function calling, offline mock
  policy), signed human-in-the-loop confirmations for write tools
  (`POST /api/v1/ai/agent/confirm`), tool catalog endpoint, chat-widget confirm
  button, Langfuse trace context per tool call, golden tool-selection evals
  (`flask agent eval-tools`) and a per-user daily token budget
- Per-user rate limiting for AI chat, error assistant and order planning
  (`AI_CHAT_RATE_LIMIT_PER_MINUTE`, `429` with `Retry-After`)
- Unsourced knowledge questions stay local and grounded instead of producing an
  unsourced model answer
- Edit and delete UI for employees, errors, and machines (PUT/DELETE routes were
  already in place; this wires up the missing frontend for all three entities)
- `.ruff_cache/` added to `.gitignore`

### Fixed
- Knowledge retrieval in the chat runs the complete LangGraph retrieval node
  sequence; query-type prompt rules reach the agent as tool output
- Template hook stability test no longer requires a built React bundle
- Shift rotation test is deterministic on weekends
- Docstrings added to all public model classes and `to_dict` methods in `models.py`

---

## [0.9.0] — 2026-05-06

### Added
- Mitarbeiter- und Urlaubsanträge-UI auf Card-Standard umgestellt
- Realistische Demo-Daten mit vollständigen Verknüpfungen zwischen Modellen
- Nutzersuche mit Attribut-Filtern (Rolle, Status, Freitext)

### Fixed
- `datetime.utcnow()` Deprecation-Warnungen behoben
- `Query.get()` Legacy-Warnungen behoben
- `/api/v1/` Prefix-Fehler im Login und `auth.js` korrigiert

---

## [0.8.0] — 2026-04-15

### Added
- Schichtübergabe-Protokoll (ShiftHandover)
- Urlaubsplanung mit Genehmigungsworkflow (VacationRequest)
- Drag-and-Drop im Schichtplan
- ArbZG-konforme Schichtgenerierung mit Fairness-Algorithmus
- Schichtplan: farbige Zellen, Sticky-Spalte, Veröffentlichen-Workflow, Audit-Log

### Changed
- Flask-Migrate eingerichtet, `_run_lightweight_migrations()` entfernt

---

## [0.7.0] — 2026-03-20

### Added
- API-Versionierung `/api/v1/`, Pagination, OpenAPI v1 Spec
- JWT-Logout mit Server-seitiger Token-Blocklist
- Saubere Service-Schicht (Task, Employee, Error)
- Task-Delete-Button, Race-Condition-Fix bei Button-Disable
- Fehler-Assistent-Endpunkt mit lokalem Katalog-Lookup und AI-Anreicherung

### Changed
- Blueprints gruppiert, Shims entfernt, Tests umbenannt

---

## [0.6.0] — 2026-03-01

### Added
- Dokumente-Modul: Liste, Download, AI-Review
- Maschinen-Referenzen normalisiert in Modellen
- Frontend-API-Handling zentralisiert (`api()` Wrapper in `app.js`)
- Health-Route bereinigt, OpenAPI-Dokumentation aktualisiert

---

## [0.5.0] — 2026-02-15

### Added
- Dashboard-KPIs mit Task-Cockpit, Priority-Cards und farbcodierten Zonen
- KI-Chat-Widget mit Markdown-Rendering und Feedback-System
- Daily Briefing via `/api/v1/ai/daily-briefing`
- Error-Assistent mit Ähnlichkeitssuche
- Maschinen-Assistent mit Anlagenakte und KI-Fragen
