# Maintenance Agent

Der Maintenance Agent ist die Weiterentwicklung des read-only Chat-Assistenten
zu einem **Tool-nutzenden Agenten**: Ein LLM waehlt Werkzeuge, die bestehenden
permission-aware Services fuehren sie aus, deterministische Guards bleiben im
Code. Schreibende Aktionen laufen nur nach expliziter Bestaetigung des Nutzers.

## Architektur

```text
POST /api/v1/ai/agent (oder /ai/chat mit AI_CHAT_MODE=agent)
  -> guard      Safety-Check, Tool-Katalog nach Berechtigung, System-Prompt
  -> agent      Provider.chat_with_tools(messages, tools)
  -> tools      execute_tool(...) pro Tool-Call, Ergebnis als tool-Message zurueck
  -> agent      ... bis Antwort ohne Tool-Calls oder AI_AGENT_MAX_ITERATIONS
  -> validate   Confidence, Post-Generation-Safety, Ergebnis-Payload
  -> respond    prompt-sichere Workflow-Diagnostik (rag.agent)
```

Module:

| Modul | Aufgabe |
| --- | --- |
| `app/agent/tools.py` | Tool-Registry, JSON-Schemas, Permission-Gates, Ergebnis-Kompaktierung |
| `app/agent/graph.py` | LangGraph-State-Machine mit deterministischem Fallback-Runner |
| `app/agent/service.py` | `run_agent(...)`, strukturierter Fast-Path, Checkpoint-Thread pro Session, Audit-Finalisierung |
| `app/agent/checkpoints.py` | LangGraph-Checkpointer (postgres, sqlite, memory) fuer Session-Gedaechtnis |
| `app/agent/actions.py` | signierte Pending Actions (itsdangerous) und Bestaetigung |
| `app/agent/mock_policy.py` | deterministische Tool-Auswahl fuer `AI_PROVIDER=mock` und Tests |
| `app/agent/prompts.py` | System-Prompt (per Prompt-Admin unter `workflow_key=agent` ueberschreibbar) |
| `app/agent/evals.py` | Golden Cases fuer Tool-Auswahl, `flask agent eval-tools` |

Provider: `BaseAIProvider.chat_with_tools(messages, tools, workflow)` liefert
`ToolCallResponse(content, tool_calls, metadata)`. OpenAI und
OpenAI-kompatible Endpunkte nutzen Function Calling; der Mock-Provider nutzt
die Keyword-Policy. Nachrichten folgen dem OpenAI-Format
(`system`/`user`/`assistant` mit `tool_calls`/`tool`).

## Strukturierter Fast-Path

`run_agent(...)` prueft vor dem Modell-Loop die deterministischen Regel-Handler
(`try_domain_structured_answers`, `try_local_structured_routes`). Treffen sie,
kommt die Antwort ohne Token-Verbrauch und reproduzierbar zurueck:

- Zaehl-, Listen- und Statusfragen zu Tasks, Stoerungen, Lager, Dokumenten,
  Schichten, Urlaub, Mitarbeitern, Daily Briefing, Auftragsplanung
- Berechtigungsverweigerungen fuer explizit angefragte Bereiche

Die Antwort traegt `diagnostics.agent_fast_path = "structured_rules"` und
`rag.agent.engine = "fast_path"`. Mit `AI_AGENT_STRUCTURED_FAST_PATH=false`
laeuft jede Frage durch den Loop. Die Regeln sind damit kein eigener Router
mehr, sondern ein Vorab-Schritt des Agenten; sie koennen Fragetyp fuer Fragetyp
in Tools ueberfuehrt werden.

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
| `none` | kein Checkpointer; Historie aus `ChatMessage`-Zeilen |

Zu Beginn jedes Turns kompaktiert `guard` die gespeicherten Nachrichten auf
reine User/Assistant-Turns (Tool-Payloads werden verworfen) und begrenzt sie auf
`AI_SESSION_CONTEXT_MESSAGES` Runden und `AI_SESSION_CONTEXT_MAX_CHARS` Zeichen.
`diagnostics.memory_backend` zeigt das aktive Backend.

## Werkzeuge

| Tool | Berechtigung | Schreibend | Beschreibung |
| --- | --- | --- | --- |
| `search_tasks` | tasks:view | nein | Strukturierte Suche in sichtbaren Tasks |
| `search_errors` | errors:view | nein | Fehlerkatalog und Stoerungen |
| `search_machines` | machines:view | nein | Maschinen und Wartungsplaene |
| `search_inventory` | inventory:view | nein | Lager und Mindestbestaende |
| `search_documents` | documents:view | nein | Berichte und Handbuecher |
| `search_shift_handovers` | shiftplans:view | nein | Schichtplaene und Uebergaben |
| `search_employees` | employees:view + Personalfreigabe | nein | Mitarbeiterdaten |
| `search_knowledge` | (intern gefiltert) | nein | RAG-Wissenssuche mit Quellen |
| `get_machine_overview` | machines:view | nein | Maschinenprofil (KPIs, Tasks, Stoerungen) |
| `error_assistant` | errors:view | nein | Ursachen, Massnahmen, Root-Cause |
| `draft_task` | tasks:write | nein | Task-Entwurf ohne Speichern |
| `prioritize_tasks` | tasks:view | nein | Risiko-Rangfolge |
| `plan_order` | machines:view (+ intern) | nein | Auftragsplanung |
| `daily_briefing` | (intern gefiltert) | nein | Tagesbriefing |
| `create_task` | tasks:write | **ja, Bestaetigung** | Task anlegen |
| `request_knowledge_reindex` | admin_ai:write | **ja, Bestaetigung** | Reindex-Job einplanen |

Jedes Tool liefert nur skalare, laengenbegrenzte Felder, entfernt interne
Notizen und Pfade und haengt oeffentliche Source-Cards an. Ergebnisse gehen
als JSON in die `tool`-Nachricht an das Modell.

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
  alle Runden aggregiert und im Audit-Event gespeichert.

## Konfiguration

```env
AI_CHAT_MODE=agent             # Default; legacy = nur der alte Regel-Router
AI_AGENT_STRUCTURED_FAST_PATH=true
AI_AGENT_CHECKPOINTER=auto
AI_AGENT_CHECKPOINT_PATH=data/agent_checkpoints.sqlite
AI_AGENT_MAX_ITERATIONS=4
AI_AGENT_ACTION_TTL_SECONDS=600
AI_CHAT_RATE_LIMIT_PER_MINUTE=30
AI_DAILY_TOKEN_BUDGET_PER_USER=0
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
`tests/test_agent.py`).

## Ausbaustufen

- Weitere Tools nur ueber `register_tool(...)` mit Permission-Gate ergaenzen.
- Regel-Handler des Fast-Path schrittweise durch Tools ersetzen und danach
  `AI_AGENT_STRUCTURED_FAST_PATH=false` als Default setzen.
- Multi-Agent (Supervisor + Worker) erst fuer langlaufende Workflows wie
  "Bericht recherchieren, entwerfen, pruefen"; die Tool-Registry bleibt die
  gemeinsame Basis.
