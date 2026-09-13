# Maintenance Agent

Der Chat ist ein **Tool-nutzender Agent**: Ein LLM (oder offline die
Mock-Policy) waehlt Werkzeuge und deren Argumente, die bestehenden
permission-aware Services fuehren sie aus, deterministische Guards bleiben im
Code. Es gibt genau einen Antwortpfad: `POST /api/v1/ai/chat`. Schreibende Aktionen laufen nur nach
expliziter Bestaetigung des Nutzers.

## Architektur

```text
POST /api/v1/ai/chat
  -> guard      Safety-Check, Tool-Katalog nach Berechtigung, System-Prompt
                (inkl. Hinweis auf den letzten strukturierten Datenbereich)
  -> agent      Provider.chat_with_tools(messages, tools)
  -> tools      execute_tool(...) pro Tool-Call, Ergebnis als tool-Message zurueck
  -> agent      ... bis Antwort ohne Tool-Calls oder AI_AGENT_MAX_ITERATIONS
  -> validate   Confidence, Post-Generation-Safety, answer_category, structured_context
  -> respond    prompt-sichere Workflow-Diagnostik (rag.agent)
```

Module:

| Modul | Aufgabe |
| --- | --- |
| `app/agent/tools.py` | Tool-Registry, JSON-Schemas, Permission-Gates, Ergebnis-Kompaktierung, Such- und Wissens-Tools |
| `app/agent/structured_tools.py` | Registrierung der parametrisierten Listen-/Zaehl-Tools |
| `app/agent/queries/` | Reine Query-Kerne pro Domaene (`(user, **filter) -> QueryOutcome`), deutsche Formatter, Source-Cards |
| `app/agent/graph.py` | LangGraph-State-Machine mit deterministischem Fallback-Runner |
| `app/agent/service.py` | `run_agent(...)`, Session-Gedaechtnis, Audit-Finalisierung |
| `app/agent/checkpoints.py` | LangGraph-Checkpointer (postgres, sqlite, memory) |
| `app/agent/actions.py` | signierte Pending Actions (itsdangerous) und Bestaetigung |
| `app/agent/mock_policy.py` | deterministische Tool-Auswahl mit Argument-Extraktion fuer `AI_PROVIDER=mock` und Tests |
| `app/agent/prompts.py` | System-Prompt (per Prompt-Admin unter `workflow_key=agent` ueberschreibbar) |
| `app/agent/evals.py` | Golden Cases fuer Tool-Auswahl, `flask agent eval-tools` |
| `app/ai/status.py` | Diagnostik, Audit-Metadaten, Qualitaetswarnungen, `/ai/status` |

Provider: `BaseAIProvider.chat_with_tools(messages, tools, workflow)` liefert
`ToolCallResponse(content, tool_calls, metadata)`. OpenAI und
OpenAI-kompatible Endpunkte nutzen Function Calling; der Mock-Provider nutzt
die Keyword-Policy mit Argument-Extraktion. Nachrichten folgen dem
OpenAI-Format (`system`/`user`/`assistant` mit `tool_calls`/`tool`).

## Werkzeuge

### Strukturierte Daten (parametrisiert)

Diese Tools ersetzen den frueheren Regel-Router. Das Modell liefert explizite
Filter; Berechtigungs-Semantik (Abteilungs-Scoping, Mitarbeiter-Zugriffsstufe,
nur veroeffentlichte Schichtplaene, eigener Urlaub, Maschinen+Fehler-Recht,
`admin_users` nur fuer Admins) sitzt in den Query-Kernen. Jedes Tool liefert
`entity_type`, `filters`, `count`, `items` (<= 10), ein fertig formatiertes
`answer_markdown` und `structured_context`.

| Tool | Parameter | Berechtigung |
| --- | --- | --- |
| `list_tasks` | `status` (open, in_progress, done), `department`, `machine`, `priority` (urgent), `time_range` (today, yesterday), `due` (today, overdue), `count_only` | tasks:view |
| `list_incidents` | `status`, `severity` (critical), `department`, `machine`, `time_range`, `group_by` (machine), `count_only` | errors:view |
| `count_records` | `scope` (tasks, errors, machines, inventory, documents, shiftplans, employees, admin_users) | pro Scope geprueft |
| `list_employees` | `department`, `availability` (available_today, absent_today, absent_tomorrow), `role` (team_lead), `count_only` | employees:view + Personalfreigabe |
| `list_employee_documents` | `mode` (employees_with_documents, stored_documents), `department`, `employee`, `count_only` | employees:view |
| `list_vacations` | `scope` (pending, own_pending, own_latest, absences), `time_range` (tomorrow, next_week), `date_from`, `date_to`, `department`, `count_only` | eigene Scopes immer, sonst sichtbare Antraege |
| `list_documents` | `filter` (recent, outdated, this_week, department, machine), `department`, `machine` | documents:view |
| `list_shift_entries` | `mode` (entries, count, understaffed), `date`, `time_range` (today, tomorrow), `shift` (early, late, night) | shiftplans:view |
| `list_inventory` | `filter` (all, low_stock, critical, machine), `machine`, `count_only` | inventory:view |
| `machine_incident_report` | `machine` (optional; ohne = Ausfallzeit-Ranking) | machines:view + errors:view |

### Suche, Wissen, Assistenten

| Tool | Berechtigung | Schreibend | Beschreibung |
| --- | --- | --- | --- |
| `search_tasks` | tasks:view | nein | Freitext-Relevanzsuche in sichtbaren Tasks |
| `search_errors` | errors:view | nein | Fehlerkatalog und Stoerungen |
| `search_machines` | machines:view | nein | Maschinen und Wartungsplaene |
| `search_inventory` | inventory:view | nein | Lager und Ersatzteile |
| `search_documents` | documents:view | nein | Berichte und Handbuecher |
| `search_shift_handovers` | shiftplans:view | nein | Schichtuebergaben |
| `search_employees` | employees:view + Personalfreigabe | nein | Mitarbeiterdaten |
| `search_knowledge` | (intern gefiltert) | nein | Hybrid-RAG (`build_rag_context`: SQL + Vektor + Keyword-Fallback, Safety, Konflikte, Explainability); ohne Quelle eine geerdete No-Answer |
| `get_machine_overview` | machines:view | nein | Maschinenprofil (KPIs, Tasks, Stoerungen) |
| `error_assistant` | errors:view | nein | Ursachen, Massnahmen, Root-Cause |
| `draft_task` | tasks:write | nein | Task-Entwurf ohne Speichern |
| `prioritize_tasks` | tasks:view | nein | Risiko-Rangfolge |
| `plan_order` | machines:view (+ intern) | nein | Auftragsplanung |
| `daily_briefing` | (intern gefiltert) | nein | Tagesbriefing mit `answer_markdown` und Quellen |
| `create_task` | tasks:write | **ja, Bestaetigung** | Task anlegen |
| `request_knowledge_reindex` | admin_ai:write | **ja, Bestaetigung** | Reindex-Job einplanen |

Jedes Tool liefert nur skalare, laengenbegrenzte Felder, entfernt interne
Notizen und Pfade und haengt oeffentliche Source-Cards an. Ergebnisse gehen
als JSON in die `tool`-Nachricht an das Modell. Verweigerungen tragen
`status: permission_denied` und den Standardtext `Keine Berechtigung fuer ...`
als `answer_markdown`, damit Modell und Mock sie unveraendert wiedergeben.

## Antwortklassifikation

`validate` setzt `answer_category` und `structured_context` auf dem Ergebnis:

| `answer_category` | Bedeutung |
| --- | --- |
| `structured_data` | nur Listen-/Zaehl-Tools (inkl. `get_machine_overview`, `daily_briefing`) |
| `rag` | mindestens ein Such-/Wissens-Tool (`search_*`, `search_knowledge`, `error_assistant`) |
| `general_ai_knowledge` | Antwort ohne Tool (`source_label: Modellwissen`) |
| `agent` | alles andere (z. B. verweigerte oder gemischte Aufrufe) |

Wenn alle Tools verweigert wurden, ist `diagnostics.status = "permission_denied"`.
Nur `rag`-Antworten ohne belastbare Quelle erzeugen Knowledge-Gap-Eintraege.
Das Chat-Widget zeigt den App-Daten-Badge bei `answer_category == "structured_data"`.

## Follow-ups (strukturiertes Gedaechtnis)

Das letzte strukturierte Tool eines Turns schreibt `structured_context`
(`entity_type`, `department`, `status`, `time_range`, `machine`, `query`,
`shift`, ...). Es wird mit der Chat-Nachricht (`diagnostics.structured_context`)
und im Checkpoint gespeichert und beim naechsten Turn als einzeiliger Hinweis
in den System-Prompt gegeben. "Welche davon sind in der Produktion?" fuehrt so
zu `list_tasks(status=open, department=Produktion)`; die Mock-Policy liest den
Hinweis aus derselben Prompt-Zeile.

## Session-Gedaechtnis (Checkpointer)

Der Graph-Zustand ist JSON-serialisierbar (Nutzer als ID, Tools werden pro
Knoten aus den Berechtigungen abgeleitet) und wird pro Thread
`user:<id>:<session_id>` von einem LangGraph-Checkpointer gespeichert:

| `AI_AGENT_CHECKPOINTER` | Backend |
| --- | --- |
| `auto` (Default) | `postgres`, wenn `DATABASE_URL` PostgreSQL ist, sonst `sqlite`, sonst `memory` |
| `postgres` | `PostgresSaver` auf der App-Datenbank (Tabellen werden per `setup()` angelegt) |
| `sqlite` | `SqliteSaver` unter `AI_AGENT_CHECKPOINT_PATH` (Default `data/agent_checkpoints.sqlite`) |
| `memory` | `MemorySaver`, nur innerhalb eines Prozesses (Tests) |
| `none` | kein Checkpointer; Historie und `structured_context` aus `ChatMessage`-Zeilen |

Zu Beginn jedes Turns kompaktiert `guard` die gespeicherten Nachrichten auf
reine User/Assistant-Turns (Tool-Payloads werden verworfen) und begrenzt sie auf
`AI_SESSION_CONTEXT_MESSAGES` Runden und `AI_SESSION_CONTEXT_MAX_CHARS` Zeichen.
`diagnostics.memory_backend` zeigt das aktive Backend.

## Mock-Policy (offline)

`app/agent/mock_policy.py` waehlt Tools deterministisch aus deutschen
Schluesselwoertern und extrahiert Argumente ueber
`app/services/ai_question_normalizer.py` (`detect_status`, `detect_time_range`,
`detect_department`, `detect_severity`) plus lokale Regexe (Maschinenphrase,
Schicht-Alias, Zaehlwoerter). Reihenfolge: Aktions-Tools (create/draft/plan/
reindex/prioritize/briefing) -> Kennungen (`#12`) -> Follow-up mit
`structured_context` -> strukturierte Intents -> `error_assistant` ->
`search_<scope>` -> `search_knowledge`. Mehrere Zaehl-Scopes ("Tasks und
Stoerungen") ergeben mehrere `count_records`-Calls. Liegt `answer_markdown`
vor, wird es wortgetreu ausgegeben. Strukturierte Intents waehlen Tools aus der
Registry, auch wenn der Nutzer das Recht nicht hat, damit die Verweigerung vom
Tool kommt.

## Human-in-the-loop

1. Das Modell ruft ein schreibendes Tool auf.
2. `execute_tool` fuehrt es **nicht** aus, sondern erzeugt eine signierte
   `pending_action` (`token`, `tool`, `label`, `arguments`, TTL).
3. Die Antwort enthaelt `pending_action`; die Chat-Bubble zeigt einen
   Bestaetigen-Button.
4. `POST /api/v1/ai/agent/confirm {"token": ...}` prueft Signatur, Ablauf und
   Nutzerbindung, fuehrt das Tool einmal aus, schreibt ein Audit-Event und
   speichert den Vorgang in der Chat-Historie.

Ein Token ist nur fuer den anfragenden Nutzer gueltig und laeuft nach
`AI_AGENT_ACTION_TTL_SECONDS` ab.

## Guards und Kosten

- Safety: Anfragen zum Umgehen von Schutzfunktionen werden im `guard`-Knoten
  ohne Modellaufruf abgelehnt. Die finale Antwort laeuft zusaetzlich durch die
  Post-Generation-Safety.
- Berechtigungen: Der Tool-Katalog ist pro Nutzer gefiltert; jeder Aufruf wird
  erneut geprueft und liefert `permission_denied` statt Daten.
- Iterationen: `AI_AGENT_MAX_ITERATIONS` (Default 4) begrenzt Modellrunden,
  maximal 4 Tool-Calls pro Runde.
- Quotas: `AI_CHAT_RATE_LIMIT_PER_MINUTE` pro Nutzer und optional
  `AI_DAILY_TOKEN_BUDGET_PER_USER` (Summe `AIAuditEvent.total_tokens` des Tages).
- Observability: jeder Provider-Aufruf und jeder Tool-Call laeuft in einem
  Langfuse-Trace-Kontext (`agent`, `agent_tool`); Tokens und Kosten werden ueber
  alle Runden aggregiert und im Audit-Event gespeichert. Provider-Fehler
  erscheinen in `/api/v1/ai/status` als `last_error`.

## Konfiguration

```env
AI_AGENT_CHECKPOINTER=auto
AI_AGENT_CHECKPOINT_PATH=data/agent_checkpoints.sqlite
AI_AGENT_MAX_ITERATIONS=4
AI_AGENT_ACTION_TTL_SECONDS=600
AI_CHAT_RATE_LIMIT_PER_MINUTE=30
AI_DAILY_TOKEN_BUDGET_PER_USER=0
AI_SESSION_CONTEXT_MESSAGES=4
AI_SESSION_CONTEXT_TTL_MINUTES=120
```

## Evaluation

```bash
flask --app run:app agent tools
flask --app run:app agent eval-tools --username admin
flask --app run:app agent eval-tools --as-json
```

`eval-tools` fuehrt die Golden Cases aus `app/agent/evals.py` gegen den
konfigurierten Provider aus und meldet Tool-Auswahl-Genauigkeit und Misses.
Mit `AI_PROVIDER=mock` muss die Genauigkeit 1.0 sein (Test in
`tests/test_agent.py`). Weitere Tests: `tests/test_agent_structured_tools.py`
(Query-Kerne und Permission-Gates), `tests/test_agent_chat_endpoint.py`
(Endpoint, Follow-ups, Verweigerung, leeres Retrieval),
`tests/test_ai_retrieval_golden_questions.py` (Retrieval-Qualitaet ueber die
Agent-Tools).

## Ausbaustufen

- Weitere Tools nur ueber `register_tool(...)` mit Permission-Gate ergaenzen;
  neue Query-Kerne unter `app/agent/queries/` halten Message-Parsing draussen.
- Multi-Agent (Supervisor + Worker) erst fuer langlaufende Workflows wie
  "Bericht recherchieren, entwerfen, pruefen"; die Tool-Registry bleibt die
  gemeinsame Basis.
