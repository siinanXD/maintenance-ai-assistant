# Feature Inventory

This document records the current product features and their isolation boundary.
The frontend source of truth is `app/static/core/feature-registry.js`; backend
permissions remain in `app/permissions.py`.

## Features

| Feature | Route | Permission | Current boundary |
| --- | --- | --- | --- |
| Dashboard | `/` | `dashboard` | Cockpit, KPIs, briefing, calendar preview |
| Tasks | `/tasks` | `tasks` | Work orders, link to incident, spare-part withdrawals, photos, reports |
| Error catalog | `/errors` | `errors` | Incidents with photos, similar-error search, work order from incident |
| Inspections & maintenance | `/maintenance` | `machines` | Maintenance and inspection plans, execution records, follow-up orders |
| Employees | `/employees` | `employees` | Employee records, access tiers, employee documents |
| Machines | `/machines` | `machines` | Machine CRUD, profile with availability/MTBF, QR label, assistant |
| Inventory | `/inventory` | `inventory` | Materials, goods receipts, movements, reorder list, forecast |
| Shift plans | `/shiftplans` | `shiftplans` | Generation, calendar, drag-and-drop, publish, changelog |
| Shift handover | `/handover` | `shiftplans` | Handover create, edit, complete, filtering |
| Vacations | `/vacations` | `employees` | Requests, approval, rejection, balance |
| Documents | `/documents` | `documents` | Generated reports, filters, download, quality review |
| Admin users | `/admin/users` | `admin_users` | User list and dashboard permission management |
| Admin AI | `/admin/ai` | `admin_users` | AI audit, chats, manual training CRUD, RAG status, source filters, stale/reindex jobs |

## Cross-Cutting Features

- Global chat widget: tool-using agent with sources, confirmed write actions,
  diagnostics and feedback.
- RAG knowledge base: uploaded knowledge, generated reports, structured app
  records, manual training entries, source/status filters, department scoping,
  priorities and stale/reindex workflows.
- Operations readiness: health checks, database schema checks, worker queue,
  AI/RAG diagnostics and runtime operations metrics.

## Isolation Rules

- New navigation entries must be added to `app/static/core/feature-registry.js`
  first, then wired to templates with `data-feature-key`.
- The registry owns permission metadata. Shared workflow pages use
  `module: "workflows"` and `initializers`; larger standalone pages use
  `module: "page"` plus `moduleUrl` for dedicated modules in
  `app/static/pages/`.
- If a feature reuses another permission, set `permissionKey` explicitly instead
  of duplicating permission checks in templates or scripts.
- New frontend code should live behind one feature initializer, one small shell
  helper, or one React route island in `frontend/src`; avoid adding feature
  logic to the core `app/static/app.js` bootstrap.
- Login, handover, shift plans, Admin AI and the other larger screens are
  loaded as route-specific React islands or page modules. Do not reintroduce
  large inline scripts in templates.
- Dynamic API data should be rendered with DOM APIs and `textContent` unless the
  string is a static, trusted empty-state fragment.
