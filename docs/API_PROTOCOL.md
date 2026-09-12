# Maintenance Assistant API - HTTPS-Protokoll

Dieses Dokument beschreibt die bestehenden API-Routen fuer den Maintenance Assistant. In Produktion sollte die API ausschliesslich ueber HTTPS betrieben werden.

## Basis

```http
Base URL: https://deine-domain.de
API Prefix: /api/v1
Content-Type: application/json
Authorization: Bearer <access_token>
```

Lokale Entwicklung:

```http
Base URL: http://127.0.0.1:5050
```

Die interaktive Swagger UI ist lokal unter `/swagger/` verfuegbar. Die
OpenAPI-Spezifikation kann direkt unter `/api/swagger.json` gelesen werden.
In Produktion ist API-Dokumentation standardmaessig deaktiviert
(`ENABLE_API_DOCS=false`). Das schuetzt `/swagger/`, `/api/swagger.json`,
`/api/v1/swagger.json` und `/apispec_1.json`. Wenn Dokumentation in Produktion
bewusst aktiviert wird, sollte `API_DOCS_REQUIRE_MASTER_ADMIN=true` gesetzt
bleiben, damit nur Master Admins mit JWT darauf zugreifen koennen.
`/api/v1` ist die stabile Version; Breaking Changes werden erst unter einem
neuen Prefix wie `/api/v2` eingefuehrt.

## Sicherheit

Alle geschuetzten Endpunkte erwarten einen JWT im `Authorization`-Header:

```http
Authorization: Bearer <access_token>
```

Passwoerter werden nicht im Klartext gespeichert, sondern als Hash. Der Token wird ueber `/api/v1/auth/login` ausgestellt.

## Rollen- und Rechtemodell

| Rolle | Wert | Zugriff |
| --- | --- | --- |
| Master/Admin | `master_admin` | Alle Bereiche und alle Daten |
| IT | `it` | Eigener Bereich |
| Verwaltung | `verwaltung` | Eigener Bereich |
| Instandhaltung | `instandhaltung` | Eigener Bereich |
| Produktion | `produktion` | Eigener Bereich |
| Personalabteilung | `personalabteilung` | Eigener Bereich |

Zusaetzlich zur Rolle gibt es Dashboard-Rechte pro User. Der Admin kann fuer jedes Dashboard `can_view` und `can_write` setzen. Die API prueft diese Rechte serverseitig.

Dashboard-Keys:

```text
dashboard, tasks, errors, employees, shiftplans, machines, inventory, documents, admin_users
```

`admin_users` bleibt effektiv `master_admin` vorbehalten. Normale Rollen sehen und bearbeiten Tasks und Fehlerkatalogeintraege weiterhin nur im eigenen Bereich.

Mitarbeiterdaten werden gestuft ausgeliefert:

| Stufe | Felder |
| --- | --- |
| `none` | Keine Mitarbeiterdaten |
| `basic` | Personalnummer, Name, Abteilung, Team |
| `shift` | Basic plus Schicht, Qualifikationen, Favoritenmaschine |
| `confidential` | Shift plus Geburtsdatum, Adresse, Gehaltsklasse, Dokumente |

## Standardantworten

Erfolg:

```json
{
  "id": 1,
  "title": "Motor M12 pruefen"
}
```

Fehler:

```json
{
  "success": false,
  "message": "Forbidden",
  "error": "Forbidden"
}
```

Typische Statuscodes:

| Code | Bedeutung |
| --- | --- |
| `200` | Erfolgreiche Anfrage |
| `201` | Ressource erstellt |
| `204` | Ressource geloescht, kein Body |
| `400` | Ungueltige Anfrage |
| `401` | Nicht authentifiziert |
| `403` | Keine Berechtigung |
| `404` | Ressource nicht gefunden |
| `409` | Konflikt, z. B. Name existiert bereits |

## Auth

### Benutzer registrieren

```http
POST /api/v1/auth/register
Content-Type: application/json
```

Request:

```json
{
  "username": "admin",
  "email": "admin@example.com",
  "password": "secret",
  "role": "master_admin"
}
```

Normaler Benutzer:

```json
{
  "username": "max",
  "email": "max@example.com",
  "password": "secret",
  "role": "instandhaltung",
  "department": "Instandhaltung"
}
```

Response `201`:

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "master_admin",
  "department": null,
  "permissions": {
    "tasks": {
      "can_view": true,
      "can_write": true,
      "employee_access_level": "none"
    }
  },
  "created_at": "2026-04-28T18:30:00"
}
```

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json
```

Request:

```json
{
  "login": "admin",
  "password": "secret"
}
```

`login` kann Benutzername oder E-Mail sein.

Response `200`:

```json
{
  "access_token": "<jwt>",
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "role": "master_admin",
    "department": null,
    "created_at": "2026-04-28T18:30:00"
  }
}
```

### Aktuellen Benutzer lesen

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "role": "master_admin",
  "department": null,
  "permissions": {
    "employees": {
      "can_view": true,
      "can_write": true,
      "employee_access_level": "confidential"
    }
  },
  "created_at": "2026-04-28T18:30:00"
}
```

## Admin-Rechteverwaltung

### Rechte-Schema fuer den Editor lesen

Nur `master_admin`.

```http
GET /api/v1/admin/permissions/schema
Authorization: Bearer <access_token>
```

Response `200` enthaelt Dashboard-Gruppen, Labels, Mitarbeiterdaten-Labels und
Rollen-Defaults fuer den UI-Editor.

### Rechte eines Users lesen

Nur `master_admin`.

```http
GET /api/v1/admin/users/2/permissions
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "tasks": {
    "can_view": true,
    "can_write": true,
    "employee_access_level": "none"
  },
  "employees": {
    "can_view": true,
    "can_write": false,
    "employee_access_level": "basic"
  }
}
```

### Rechte eines Users ersetzen

Nur `master_admin`.

```http
PUT /api/v1/admin/users/2/permissions
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "permissions": {
    "tasks": {
      "can_view": true,
      "can_write": true,
      "employee_access_level": "none"
    },
    "employees": {
      "can_view": true,
      "can_write": false,
      "employee_access_level": "basic"
    }
  }
}
```

Ungueltige Dashboard-Keys oder Mitarbeiterdatenstufen liefern `400`.

## Admin-Audit und Backups

Alle Endpunkte in diesem Abschnitt sind `master_admin`-only.

```http
GET /api/v1/admin/audit-log?q=permissions.update&limit=50&offset=0
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "actor": {"id": 1, "username": "admin"},
      "action": "permissions.update",
      "resource_type": "user",
      "resource_id": "2",
      "before": {},
      "after": {},
      "created_at": "2026-05-12T12:00:00+00:00"
    }
  ],
  "pagination": {"limit": 50, "offset": 0, "total": 1}
}
```

Backups:

```http
POST /api/v1/admin/backups
GET /api/v1/admin/backups
GET /api/v1/admin/backups/<backup_id>/download
POST /api/v1/admin/backups/<backup_id>/restore
```

Restore verlangt immer eine explizite Bestaetigung:

```json
{"confirm": true}
```

Das Backup-ZIP enthaelt ein Manifest, die SQLite-Datenbank, Uploads,
Dokumente und Logs, soweit die konfigurierten Ordner existieren.

## Admin-Benachrichtigungen

E-Mail-Versand wird ueber SMTP aus `.env` gesteuert. `MAIL_DRY_RUN=true`
erstellt Delivery-Records ohne SMTP-Verbindung.

```http
GET /api/v1/admin/notifications/deliveries?type=task_urgent&status=dry_run
Authorization: Bearer <access_token>
```

```http
POST /api/v1/admin/notifications/test-email
Authorization: Bearer <access_token>
Content-Type: application/json

{"recipient_email": "ops@example.test"}
```

Scheduler-Jobs laufen bewusst ueber CLI, nicht als Hintergrundtimer im
Flask-Prozess:

```bash
flask --app run:app notifications send-task-alerts
flask --app run:app notifications send-overdue-reminders
flask --app run:app notifications send-ai-alerts
flask --app run:app notifications send-daily-briefings
```

## In-App-Benachrichtigungen

Persoenliche Benachrichtigungen werden im Topbar-Badge angezeigt.

```http
GET /api/v1/notifications
PATCH /api/v1/notifications/1/read
PATCH /api/v1/notifications/read-all
```

Plan-Publish, Unpublish, Entry-Update, Move, Swap und Delete erzeugen
Benachrichtigungen fuer betroffene verknuepfte Mitarbeiter und Plan-Admins.

## Departments

### Departments auflisten

```http
GET /api/v1/departments
Authorization: Bearer <access_token>
```

Response `200`:

```json
[
  {
    "id": 1,
    "name": "Instandhaltung"
  }
]
```

### Department erstellen

Nur `master_admin`.

```http
POST /api/v1/departments
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "name": "Qualitaetssicherung"
}
```

Response `201`:

```json
{
  "id": 5,
  "name": "Qualitaetssicherung"
}
```

## Tasks

### Task-Vorschlag aus Freitext

```http
POST /api/v1/tasks/suggest
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "text": "Maschine 3 macht laute Geraeusche am Lager."
}
```

Response `200` ist ein Vorschlag und wird nicht gespeichert:

```json
{
  "title": "Pruefung: Maschine 3 macht laute Geraeusche am Lager.",
  "description": "Maschine 3 macht laute Geraeusche am Lager.",
  "department": "Instandhaltung",
  "priority": "soon",
  "status": "open",
  "possible_cause": "Lager verschlissen...",
  "recommended_action": "Maschine 3 sicher pruefen..."
}
```

### Tasks auflisten

```http
GET /api/v1/tasks
Authorization: Bearer <access_token>
```

Optionale Filter:

```http
GET /api/v1/tasks?status=open&priority=urgent
```

Response `200`:

```json
[
  {
    "id": 1,
    "title": "Motor M12 pruefen",
    "description": "Motor laeuft unruhig und zieht zu viel Strom.",
    "priority": "urgent",
    "status": "open",
    "due_date": "2026-04-30",
    "department": {
      "id": 3,
      "name": "Instandhaltung"
    },
    "created_by": 1,
    "created_at": "2026-04-28T18:30:00",
    "updated_at": "2026-04-28T18:30:00"
  }
]
```

### Task erstellen

```http
POST /api/v1/tasks
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "title": "Motor M12 pruefen",
  "description": "Motor laeuft unruhig und zieht zu viel Strom.",
  "department": "Instandhaltung",
  "due_date": "2026-04-30",
  "priority": "urgent",
  "status": "open"
}
```

Erlaubte Prioritaeten:

```text
urgent, soon, normal
```

Erlaubte Status:

```text
open, in_progress, done, cancelled
```

Response `201`: Task-Objekt.

### Einzelnen Task lesen

```http
GET /api/v1/tasks/1
Authorization: Bearer <access_token>
```

Response `200`: Task-Objekt.

### Task aktualisieren

```http
PUT /api/v1/tasks/1
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "status": "in_progress",
  "priority": "urgent"
}
```

Response `200`: Aktualisiertes Task-Objekt.

### Task loeschen

```http
DELETE /api/v1/tasks/1
Authorization: Bearer <access_token>
```

Response:

```http
204 No Content
```

### Heutige Tasks abrufen

```http
GET /api/v1/tasks/today
Authorization: Bearer <access_token>
```

Response `200`: Liste der Tasks mit `due_date` gleich dem aktuellen Datum des Servers.

### Tasks priorisieren

```http
POST /api/v1/tasks/prioritize
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request optional:

```json
{
  "status": "open",
  "limit": 20
}
```

Response `200` ist eine priorisierte, nicht gespeicherte Bewertung sichtbarer Tasks:

```json
[
  {
    "task": {
      "id": 1,
      "title": "Motor M12 pruefen"
    },
    "score": 88,
    "risk_level": "critical",
    "reason": "Prioritaet urgent; Faelligkeit ist heute; mechanische Symptome",
    "recommended_action": "Sofort pruefen, Anlage sichern und Instandhaltung informieren."
  }
]
```

Ohne OpenAI-Key nutzt die API den lokalen Fallback. Die Priorisierung speichert keine Scores in der Datenbank.

## Fehlerkatalog

### Fehlerbeschreibung analysieren

```http
POST /api/v1/errors/analyze
Authorization: Bearer <access_token>
Content-Type: application/json
```

Response `200` ist ein Vorschlag und wird nicht gespeichert:

```json
{
  "machine": "Maschine 3",
  "title": "Stoerung: Sensor meldet sporadisch kein Signal",
  "description": "Sensor meldet sporadisch kein Signal an Maschine 3.",
  "possible_causes": "Sensor verschmutzt...",
  "solution": "Anlage sichern...",
  "department": "Instandhaltung"
}
```

### Fehler auflisten

```http
GET /api/v1/errors
Authorization: Bearer <access_token>
```

Response `200`:

```json
[
  {
    "id": 1,
    "machine": "Verpackungsmaschine 3",
    "error_code": "E104",
    "title": "Sensor erkennt Produkt nicht",
    "description": "Der Lichttaster erkennt das Produkt sporadisch nicht.",
    "possible_causes": "Sensor verschmutzt, falscher Abstand, Kabelbruch",
    "solution": "Sensor reinigen, Abstand pruefen, Kabel messen",
    "department": {
      "id": 3,
      "name": "Instandhaltung"
    },
    "created_at": "2026-04-28T18:30:00"
  }
]
```

### Fehler anlegen

```http
POST /api/v1/errors
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "machine": "Verpackungsmaschine 3",
  "error_code": "E104",
  "title": "Sensor erkennt Produkt nicht",
  "description": "Der Lichttaster erkennt das Produkt sporadisch nicht.",
  "possible_causes": "Sensor verschmutzt, falscher Abstand, Kabelbruch",
  "solution": "Sensor reinigen, Abstand pruefen, Kabel messen",
  "department": "Instandhaltung"
}
```

Response `201`: Fehlerkatalog-Objekt.

### Fehler suchen

```http
GET /api/v1/errors/search?query=E104
Authorization: Bearer <access_token>
```

`query` sucht in Fehlercode, Maschine, Titel und Beschreibung.

Response `200`: Liste passender Fehlerkatalogeintraege.

### Aehnliche Fehler vorschlagen

```http
POST /api/v1/errors/similar
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "text": "Sensor Signal an Anlage 4 fehlt",
  "machine": "Anlage 4",
  "limit": 5
}
```

Response `200`:

```json
{
  "query": {
    "text": "Sensor Signal an Anlage 4 fehlt",
    "machine": "Anlage 4"
  },
  "results": [
    {
      "entry": {
        "id": 1,
        "error_code": "E104",
        "title": "Sensor erkennt Produkt nicht"
      },
      "score": 84,
      "reason": "3 gemeinsame Begriffe; Maschine stimmt ueberein"
    }
  ],
  "diagnostics": {
    "status": "local_answer",
    "provider": "local_similarity"
  }
}
```

### Einzelnen Fehler lesen

```http
GET /api/v1/errors/1
Authorization: Bearer <access_token>
```

Response `200`: Fehlerkatalog-Objekt.

### Fehler aktualisieren

```http
PUT /api/v1/errors/1
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "solution": "Sensor reinigen, Abstand auf 40 mm einstellen, Kabel auf Bruch pruefen."
}
```

Response `200`: Aktualisiertes Fehlerkatalog-Objekt.

### Fehler loeschen

```http
DELETE /api/v1/errors/1
Authorization: Bearer <access_token>
```

Response:

```http
204 No Content
```

## KI-Assistent

### Chat-Anfrage senden

```http
POST /api/v1/ai/chat
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request Fehlerhilfe:

```json
{
  "message": "Maschine 3 zeigt Fehler E104. Was soll ich pruefen?"
}
```

Response `200`:

```json
{
  "type": "error_help",
  "answer": "Der Fehler E104 an Verpackungsmaschine 3 passt zu: Sensor erkennt Produkt nicht...",
  "diagnostics": {
    "status": "openai_used",
    "fallback_used": false
  },
  "data": [
    {
      "id": 1,
      "machine": "Verpackungsmaschine 3",
      "error_code": "E104",
      "title": "Sensor erkennt Produkt nicht"
    }
  ]
}
```

Request Task-Abfrage:

```json
{
  "message": "Welche Tasks stehen heute an?"
}
```

Response `200`:

```json
{
  "type": "tasks_today",
  "answer": "Heute stehen diese Tasks an:\n- Motor M12 pruefen (urgent, open, Bereich: Instandhaltung)",
  "diagnostics": {
    "status": "local_answer",
    "fallback_used": false
  },
  "data": [
    {
      "id": 1,
      "title": "Motor M12 pruefen"
    }
  ]
}
```

Moegliche Diagnosewerte:

| Status | Bedeutung |
| --- | --- |
| `local_answer` | Lokale Antwort ohne OpenAI, z. B. heutige Tasks |
| `api_key_missing` | Kein OpenAI-Key konfiguriert, lokaler Fallback genutzt |
| `openai_error` | OpenAI-Anfrage fehlgeschlagen, lokaler Fallback genutzt |
| `fallback_used` | Fallback wurde ohne genauere Kategorie genutzt |
| `openai_used` | OpenAI-Antwort wurde verwendet |

`diagnostics` enthaelt zusaetzlich `provider` und `model`, aber niemals den API-Key. Die Chat-Bubble zeigt diese Werte als kleine Statuszeile pro Antwort.

Rate-Limit: `POST /api/v1/ai/chat`, `POST /api/v1/ai/error-assistant` und
`POST /api/v1/ai/order-plan` sind pro Nutzer auf
`AI_CHAT_RATE_LIMIT_PER_MINUTE` Anfragen begrenzt. Bei Ueberschreitung:

```http
429 Too Many Requests
Retry-After: 42
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
```

```json
{
  "success": false,
  "error": "ai_request_rate_limit_exceeded",
  "message": "AI request rate limit exceeded"
}
```

OpenAI-Fehler werden in `diagnostics.error` getrennt ausgewiesen:

| Fehler | Bedeutung |
| --- | --- |
| `rate_limit` | Provider-Limit erreicht |
| `model_not_allowed` | Konfiguriertes Modell ist nicht freigeschaltet |
| `authentication_error` | API-Key wurde abgelehnt |
| `connection_error` | Netzwerk oder Provider-Verbindung fehlgeschlagen |
| `timeout` | Provider-Anfrage hat das Timeout erreicht |
| `openai_error` | Sonstiger Providerfehler |

Normale allgemeine Fragen werden als `type: general_chat` gespeichert und
enthalten sichtbar den Hinweis, dass Chat-Historie und AI-Nutzungsmetadaten
protokolliert werden.

### Agent

```http
POST /api/v1/ai/agent
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{ "message": "Welche offenen Tasks gibt es an Presse 3?", "session_id": "chat-widget" }
```

Response `200` (Auszug):

```json
{
  "type": "agent",
  "answer": "## Ergebnis
- Dichtung an Presse 3 pruefen (open)",
  "tool_trace": [{ "tool": "search_tasks", "status": "ok", "summary": "1 Treffer in tasks" }],
  "pending_action": null,
  "diagnostics": { "status": "openai_used", "workflow": "agent", "agent_tool_calls": ["search_tasks"] }
}
```

Schreibende Tools liefern statt einer Ausfuehrung eine `pending_action`
(`token`, `tool`, `label`, `arguments`, `expires_in_seconds`). Die Aktion wird
mit dem Token bestaetigt:

```http
POST /api/v1/ai/agent/confirm
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{ "token": "<signed-token>", "session_id": "chat-widget" }
```

Antworten: `200` mit `type: agent_action`, `400` bei ungueltigem oder
abgelaufenem Token, `403` wenn das Token einem anderen Nutzer gehoert oder die
Schreibberechtigung fehlt.

```http
GET /api/v1/ai/agent/tools
Authorization: Bearer <access_token>
```

liefert den nach Berechtigung gefilterten Tool-Katalog. Mit
`AI_CHAT_MODE=agent` laeuft auch `POST /api/v1/ai/chat` ueber den Agenten.
Details: `docs/AI_AGENT.md`.

### Chat-Historie

```http
GET /api/v1/ai/chat/history?q=Hydraulik&limit=30&offset=0
Authorization: Bearer <access_token>
```

Normale Nutzer erhalten nur ihre eigene Historie. Master Admins koennen alle
Chats ueber die Admin-API durchsuchen:

```http
GET /api/v1/admin/ai/chats?q=Hydraulik&user_id=3&limit=50&offset=0
Authorization: Bearer <master-admin-token>
```

### Admin-AI-Events und Knowledge

```http
GET /api/v1/admin/ai/events?workflow=general_chat&error=rate_limit&days=7
GET /api/v1/admin/ai/summary?days=7
POST /api/v1/admin/ai/knowledge/upload
GET /api/v1/admin/ai/knowledge?q=manual&status=indexed
POST /api/v1/admin/ai/knowledge/reindex
DELETE /api/v1/admin/ai/knowledge/1
```

Die Knowledge-API ist Master-Admin-only. Uploads erlauben `.pdf`, `.txt`,
`.html` und `.htm`. Der RAG-v1-Index speichert lokale Text-Chunks und nutzt
Token-Ueberschneidung, keine externen Embeddings. Treffer erscheinen im Chat
als `sources` mit `type: "knowledge"`.

### Taegliches Briefing

```http
GET /api/v1/ai/daily-briefing
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "date": "2026-05-01",
  "summary": "Heute gibt es 3 wichtige Hinweise.",
  "sections": [
    {
      "type": "tasks",
      "title": "Tasks",
      "count": 1,
      "items": [
        {
          "title": "Motor pruefen",
          "severity": "critical",
          "summary": "urgent, open, faellig 2026-04-30",
          "url": "/api/v1/tasks/1"
        }
      ]
    }
  ],
  "diagnostics": {
    "status": "local_answer",
    "provider": "local_briefing"
  }
}
```

### KI-Konfiguration pruefen

Nur `master_admin`.

```http
GET /api/v1/ai/status
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "api_key_configured": true,
  "provider": "OpenAI",
  "model": "gpt-4o-mini",
  "ready": true,
  "last_error": null
}
```

Der API-Key wird nie im Response-Body ausgegeben.

Wenn `api_key_configured` false ist, fehlt die lokale `.env` oder `OPENAI_API_KEY` ist leer. `.env.example` ist nur eine Vorlage und darf keine echten Secrets enthalten.

### AI-Feedback speichern

```http
POST /api/v1/ai/feedback
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "prompt": "Was bedeutet E104?",
  "response": "Der Fehler deutet auf...",
  "rating": "helpful",
  "comment": "optional"
}
```

## Dokumente

```http
GET /api/v1/documents
GET /api/v1/documents?task_id=1&department=Instandhaltung&machine=Maschine
POST /api/v1/documents/1/review
GET /api/v1/documents/1/download
GET /api/v1/documents/1/download.pdf
GET /api/v1/documents/1/versions
POST /api/v1/documents/1/summarize
POST /api/v1/documents/1/submit-review
POST /api/v1/documents/1/approve
POST /api/v1/documents/1/reject
```

Dokumente benoetigen `documents.view`. Statusaenderungen, Handbuch-Uploads
und Freigaben benoetigen `documents.write`. Berichte werden lokal als HTML
unter `documents/YYYY/MM/task_<id>/maintenance_report.html` gespeichert. Jede
neu erzeugte Berichtsversion bleibt als `DocumentVersion` nachvollziehbar.

### PDF-Export und Versionen

```http
GET /api/v1/documents/1/download.pdf
Authorization: Bearer <access_token>
```

Response `200` liefert `application/pdf`. Der PDF-Export nutzt denselben
Sichtbarkeitscheck wie der HTML-Download und gibt `404` zurueck, wenn die
Berichtsdatei nicht mehr auf dem Datentraeger liegt.

```http
GET /api/v1/documents/1/versions
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "success": true,
  "message": "Document versions loaded",
  "data": [
    {
      "id": 1,
      "document_id": 1,
      "version_number": 1,
      "original_filename": "maintenance_report.html",
      "content_type": "text/html",
      "file_size": 4096,
      "created_at": "2026-05-12T10:00:00"
    }
  ]
}
```

### Dokument pruefen

```http
POST /api/v1/documents/1/review
Authorization: Bearer <access_token>
```

Response `200`:

```json
{
  "document": {
    "id": 1,
    "title": "Wartungsbericht Task 1"
  },
  "quality_score": 80,
  "status": "needs_review",
  "findings": [
    {
      "field": "Ursache",
      "severity": "critical",
      "message": "Ursache fehlt im Wartungsbericht."
    }
  ],
  "recommendations": [
    "Ursache oder wahrscheinliche Fehlerquelle dokumentieren."
  ],
  "diagnostics": {
    "status": "local_answer",
    "provider": "mock"
  }
}
```

Die Pruefung speichert keine Ergebnisse. Ohne OpenAI-Key nutzt die API einen lokalen Fallback.

### Zusammenfassung und Freigabe

```http
POST /api/v1/documents/1/summarize
POST /api/v1/documents/1/submit-review
POST /api/v1/documents/1/approve
POST /api/v1/documents/1/reject
```

`summarize` speichert eine Kurzfassung am Dokument. Ohne erreichbaren
OpenAI-Provider wird eine lokale Extrakt-Zusammenfassung erzeugt.

Der Freigabeprozess ist einstufig:

| Status | Bedeutung |
| --- | --- |
| `draft` | Entwurf oder neue Version |
| `in_review` | Zur Pruefung eingereicht |
| `approved` | Freigegeben mit Nutzer, Kommentar und Zeitstempel |
| `rejected` | Abgelehnt mit Nutzer, Kommentar und Zeitstempel |

Kommentar-Felder sind optional:

```json
{
  "comment": "Freigegeben fuer die Ablage."
}
```

### Maschinenhandbuecher

```http
POST /api/v1/documents/manuals
GET /api/v1/documents/manuals?machine_id=1&q=Sensor
GET /api/v1/documents/manuals/1/download
POST /api/v1/documents/manuals/1/analyze
POST /api/v1/documents/manuals/1/summarize
DELETE /api/v1/documents/manuals/1
```

Upload ist `multipart/form-data` und erlaubt `.pdf`, `.txt`, `.html` und
`.htm`. PDF-Text wird mit optional installiertem `pypdf` extrahiert; gescannte
PDFs ohne Textschicht liefern eine klare Analyse-/Extraktionsmeldung statt OCR.

Beispiel-Upload:

```http
POST /api/v1/documents/manuals
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file=<manual.pdf>
machine_id=1
department=Instandhaltung
```

Analysepunkte fuer Handbuecher:

```text
Maschinenbezug, Wartungsintervalle, Sicherheitshinweise, Ersatzteile,
Fehlercodes, offene Risiken
```

## Wissenssuche

```http
GET /api/v1/search?q=Sensorfehler
Authorization: Bearer <access_token>
```

Response:

```json
{
  "query": "Sensorfehler",
  "results": [
    {
      "type": "task",
      "title": "Sensor pruefen",
      "summary": "Beschreibung",
      "url": "/api/v1/tasks/1"
    }
  ]
}
```

## Mitarbeiter

Mitarbeiter-Endpunkte benoetigen `employees.view`. Schreibzugriffe, Uploads und Downloads vertraulicher Dokumente benoetigen `employees.write` und `employee_access_level=confidential`.

```http
GET /api/v1/employees
POST /api/v1/employees
PUT /api/v1/employees/1
DELETE /api/v1/employees/1
```

Mitarbeiter enthalten fuer die Schichtplanung:

```json
{
  "qualifications": "CNC, Staplerschein",
  "favorite_machine": "Anlage 4"
}
```

## Maschinen

Maschinen-Endpunkte benoetigen `machines.view` oder `machines.write`.

```http
GET /api/v1/machines
POST /api/v1/machines
GET /api/v1/machines/1/history
PUT /api/v1/machines/1
DELETE /api/v1/machines/1
```

Request:

```json
{
  "name": "Anlage 4",
  "produced_item": "Gehaeuse",
  "required_employees": 2
}
```

### Maschinenqualifikationen

Das Freitextfeld `qualifications` bleibt fuer Notizen erhalten. Fuer die
Schichtplanung entscheidet die strukturierte Maschinenfreigabe:

```http
GET /api/v1/employees/qualifications
PUT /api/v1/employees/1/qualifications
```

Request:

```json
{
  "qualifications": [
    {
      "machine_id": 1,
      "level": "trained",
      "valid_until": "2026-12-31",
      "notes": "Freigabe durch Teamleitung"
    }
  ]
}
```

Erlaubte Level: `basic`, `trained`, `expert`, `trainer`.

### Maschinen-Historie

```http
GET /api/v1/machines/1/history
Authorization: Bearer <access_token>
```

Benoetigt `machines.view`. Tasks, Fehler und Dokumente werden nur einbezogen, wenn der Benutzer fuer das jeweilige Dashboard Leserechte hat.

Response `200`:

```json
{
  "machine": {
    "id": 1,
    "name": "Anlage 4"
  },
  "summary": {
    "text": "Anlage 4 hat 2 Tasks, 1 Fehler und 3 Dokumente in der Historie.",
    "diagnostics": {
      "status": "local_answer"
    }
  },
  "source_counts": {
    "tasks": 2,
    "errors": 1,
    "documents": 3,
    "total": 6
  },
  "timeline": [
    {
      "type": "task",
      "date": "2026-05-01T12:00:00",
      "title": "Stillstand Anlage 4",
      "status": "open",
      "summary": "Sensorfehler pruefen",
      "url": "/api/v1/tasks/1"
    }
  ]
}
```

Die Historie ist read-only und speichert keine KI-Zusammenfassungen.

### Maschinen-KI-Assistent

```http
POST /api/v1/machines/1/assistant
Authorization: Bearer <access_token>
Content-Type: application/json
```

Request:

```json
{
  "question": "Was sollte ich als naechstes pruefen?"
}
```

Response `200`:

```json
{
  "answer": "Anlage 4: 2 Tasks, 1 Fehler, 1 Dokument sichtbar.",
  "diagnostics": {
    "status": "local_answer",
    "provider": "mock"
  },
  "context": {
    "source_counts": {
      "tasks": 2,
      "errors": 1,
      "documents": 1,
      "total": 4
    },
    "forecast_items": 1
  }
}
```

## Lager

Lager-Endpunkte benoetigen `inventory.view` oder `inventory.write`.

```http
GET /api/v1/inventory
GET /api/v1/inventory/summary
POST /api/v1/inventory
PUT /api/v1/inventory/1
DELETE /api/v1/inventory/1
```

Request:

```json
{
  "name": "Schraube M6",
  "unit_cost": 0.12,
  "quantity": 500,
  "machine_id": 1,
  "manufacturer": "ACME"
}
```

Summary:

```json
{
  "material_count": 1,
  "total_quantity": 500,
  "total_value": 60.0
}
```

### Ersatzteil-Prognose

```http
POST /api/v1/inventory/forecast
Authorization: Bearer <access_token>
Content-Type: application/json
```

Benoetigt `inventory.view` und `tasks.view`.

Request optional:

```json
{
  "status": "open",
  "limit": 20,
  "low_stock_threshold": 5
}
```

Response `200`:

```json
{
  "items": [
    {
      "machine": {"id": 1, "name": "Anlage 4"},
      "material": {"id": 2, "name": "Sensor S1"},
      "quantity": 1,
      "task": {"id": 7, "title": "Stillstand Anlage 4"},
      "score": 92,
      "risk_level": "high",
      "reason": "Sensor S1 liegt bei 1 Stueck und damit unter oder auf dem Mindestbestand 5; Task-Risiko critical.",
      "recommended_action": "Nachbestellung vorbereiten und Task vor Arbeitsbeginn pruefen."
    }
  ],
  "unmatched_tasks": [],
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 0,
    "total": 1
  }
}
```

Die Prognose speichert keine Ergebnisse. Maschinen werden ueber normalisierte
Maschinen- und Produktnamen, Teilnamen und Nummern-/Alias-Treffer in Task-Titel
oder Beschreibung erkannt.

## Schichtplanung

Schichtplan-Endpunkte benoetigen `shiftplans.view` oder `shiftplans.write`. Die Generierung benoetigt zusaetzlich mindestens Mitarbeiterdatenstufe `shift`, weil dabei Produktionsmitarbeiter geplant werden.

```http
GET /api/v1/shiftplans
POST /api/v1/shiftplans/generate
GET /api/v1/shiftplans/1/conflicts
POST /api/v1/shiftplans/validate
GET /api/v1/shiftplans/1/export.xlsx
DELETE /api/v1/shiftplans/1
```

Request:

```json
{
  "title": "KW 18 Produktion",
  "start_date": "2026-05-01",
  "days": 7,
  "rhythm": "2-Schicht",
  "preferences": "Max bevorzugt Fruehschicht, Lisa bevorzugt Anlage 4"
}
```

Die Generierung beruecksichtigt Produktionsmitarbeiter, Rhythmus,
Praeferenzen, genehmigte Urlaube, strukturierte Maschinenfreigaben und
Maschinenbedarf. Ohne OpenAI-Key oder bei OpenAI-Fehlern wird ein lokaler
Fallback genutzt.

Die Antwort enthaelt zusaetzlich `warnings`, `conflicts` und
`coverage_summary`, damit Doppelbelegung, Urlaubskonflikte, fehlende
Qualifikation, Ruhezeit, Wochenstunden, aufeinanderfolgende Arbeitstage und
Maschinenabdeckung sichtbar werden.

Konflikttypen:

```text
duplicate_assignment, vacation_conflict, missing_qualification, coverage,
rest_time, weekly_hours, consecutive_days
```

Der XLSX-Export enthaelt Plan-Metadaten, Eintraege, Konflikte und Auswertung.
Die PDF-Ausgabe erfolgt ueber die optimierte Druckansicht des Browsers.

## cURL-Beispiele

Login:

```bash
curl -X POST https://deine-domain.de/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"login\":\"admin\",\"password\":\"secret\"}"
```

Fehler suchen:

```bash
curl "https://deine-domain.de/api/v1/errors/search?query=E104" \
  -H "Authorization: Bearer <access_token>"
```

Chat:

```bash
curl -X POST https://deine-domain.de/api/v1/ai/chat \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"Maschine 3 zeigt Fehler E104. Was soll ich pruefen?\"}"
```

## Produktionshinweise

- HTTPS ueber Reverse Proxy wie Nginx, Caddy oder Traefik terminieren.
- `JWT_SECRET_KEY` in Produktion stark und geheim halten.
- `.env` niemals committen.
- CORS nur fuer bekannte Frontend-Domains erlauben.
- Rate-Limits fuer Login und KI-Chat einplanen.
- Datenbank-Backups fuer den Fehlerkatalog automatisieren.
