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
- Dark design: follows the system setting, switchable in the user menu, set
  before the first paint. About 460 fixed color values and 400 Tailwind palette
  utilities in the page styles now read the design tokens

### Removed
- Dead code found by AST, import-graph and CSS scans: 44 unused Python
  definitions, 14 unreachable React files, 100+ unused exports, 546 unused CSS
  rules; the unused LangGraph answer-generation path; the `/ai/agent`,
  `/ai/chat/templates`, `/ai/incident-timeline` and `/ai/order-plan` endpoints;
  legacy Admin-AI redirects
- Help boxes and placeholder KPI cards without real data on list pages
- The second JavaScript layer next to React: `app/static/pages/*` (14 mount
  watchers), `app/static/shared/*`, `core/api-client.js`, the page loader in
  `app.js`, DOM list filtering and permission toggling in `auth.js`, 432 `data-*`
  hook attributes that nothing read, hidden dashboard forms and counters, the
  unused React demo app and five pass-through provider and markup components
- About 1,800 lines of source-snapshot tests that pinned those hooks; replaced by
  `tests/test_frontend_structure.py`

### Fixed
- Logging out from the topbar now revokes the token on the server; the React
  handler cleared the session but stopped the click before `auth.js` saw it
- Shift plan and user administration pages showed "Maintenance Assistant" as
  topbar title
- Relative dates in assistant answers ("today", "yesterday", "tomorrow", "this
  week", overdue) follow the plant calendar (`PLANT_TIMEZONE`, default
  Europe/Berlin) instead of comparing the server's local date with UTC timestamps
- The shift plan publish button received its label text as CSS class
- `success_payload` no longer lets a body key named `success` flip the
  response envelope; a dict result is the response body (documented)
- The "In Bearbeitung" kanban column carried the orange action colour; it is a
  state and now uses the info blue

### Changed
- `task_service.py` (1,300 lines) split into task CRUD, `task_ai_service.py`
  (prioritization, suggestions) and `task_priority_context_service.py`
  (history and evidence); `ai_observability_service.py` (2,460 lines) split
  into dashboard, chats, sources, actions, debug and common modules
- Frontend: every page folder has `entry.tsx`, `<Page>App.tsx`, API/type/util
  modules and `components/`; entries share `mountPage`. Pages use one
  `PageHeader` and one `StatStrip` instead of eleven header and eight stats components,
  and one confirmation dialog instead of `window.confirm`. Admin-AI: eight API
  modules and three barrels merged, one access check, the view switch lives in
  `AdminAiApp`
- Page styles live in `app/static/css/src/15-pages/` (one file per page and for
  the shell); `10-legacy` keeps only shared building blocks (9,400 → 3,700 lines).
  Stylesheets read design tokens directly: 411 uses of the 49 `--ui-*`/`--ops-*`
  variables replaced and their definitions removed. Computed styles of all pages
  (desktop, tablet, phone) compared before and after: identical
- CSS sources are grouped by cascade layer (`00-foundation`, `10-legacy`,
  `20-components`, `90-overrides`) instead of 70 fragments split mid-block;
  389 overridden declarations and 312 unused selectors removed, built
  declarations verified identical apart from those
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
