# Frontend

Flask renders the page shell (`app/templates/base.html`). Every page is a React
app with its own Vite entry that mounts into one root element of its template.
The shell itself (sidebar, topbar, chat) is one more entry that renders into the
placeholders of `base.html`.

```
src/
  app/           mountPage, typed access to the shell scripts (runtimeBridge)
  api/           fetch client with auth header and error handling
  auth/          stored session, permission checks, session hooks
  components/    shared UI: PageHeader, StatStrip, PageActionBar, ActionDrawer, attachments
  layout/        shell: sidebar navigation, topbar, global search, chat widget
  utils/         dates, numbers, downloads, error messages
  <page>/        one folder per page, see below
```

A page folder always looks like this:

```
tasks/
  entry.tsx        mountPage("maintenance-tasks-root", <TasksApp />)
  TasksApp.tsx     page state, data loading, layout
  taskApi.ts       requests
  taskTypes.ts     types
  taskUtils.ts     pure helpers
  components/      UI pieces of this page
```

Larger pages add a `hooks/` folder (Admin-AI).

## Shell scripts

Three small scripts in `app/static/` run before React and are reached through
`src/app/runtimeBridge.ts`:

| Script | Global | Purpose |
| --- | --- | --- |
| `auth.js` | `window.maintenanceAuth` | session in localStorage, login redirect, logout |
| `core/action-dialogs.js` | `window.maintenanceDialogs` | confirmation and text dialog |
| `app.js` | `window.maintenanceFrontend` | toast, form and table accessibility |

`core/feature-registry.js` lists the protected routes and their permission area
for the login redirect.

## Commands

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run build     # writes app/static/react
```

`tests/test_frontend_structure.py` checks the page layout, the entries and the
shell scripts.
