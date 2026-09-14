# Feature Inventory

This document records the current product features and their boundaries.
Backend permissions live in `app/permissions.py`; the frontend structure is
described in [`frontend/README.md`](../frontend/README.md).

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
| Admin AI | `/admin/ai` | `admin_ai` (API: master admin) | AI audit, chats, manual training CRUD, RAG status, source filters, stale/reindex jobs |

## Cross-Cutting Features

- Global chat widget: tool-using agent with sources, confirmed write actions,
  diagnostics and feedback.
- RAG knowledge base: uploaded knowledge, generated reports, structured app
  records, manual training entries, source/status filters, department scoping,
  priorities and stale/reindex workflows.
- Operations readiness: health checks, database schema checks, worker queue,
  AI/RAG diagnostics and runtime operations metrics.

## Adding a page

1. Web route in `app/web/routes.py` and a template that extends `base.html`
   with one root element and `react_entrypoint("src/<page>/entry.tsx")`.
2. `frontend/src/<page>/entry.tsx`, `<Page>App.tsx`, API and type modules, UI
   pieces in `components/`; the entry goes into `frontend/vite.config.ts`.
3. The route and its permission area in `app/static/core/feature-registry.js`
   (login redirect) and the link in `frontend/src/layout/ShellNavigationModel.ts`.
4. Use `PageHeader` and `StatStrip` from `frontend/src/components/ui/` and
   `confirmAction` for confirmations; styles for new building blocks go into
   `app/static/css/src/20-components/`.

`tests/test_frontend_structure.py` checks these rules.
