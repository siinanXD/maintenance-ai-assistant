# Maintenance Assistant App Agent Instructions

Optional contributor notes for AI-assisted development in Cursor. Not required to
build, test, or deploy the application. Maintainer roadmap: `docs/ROADMAP.md`.

You are a senior software engineer working on the Maintenance Assistant App.

## Scope

- Preserve the existing Flask, SQLAlchemy, API, route, template, and test structure.
- Treat the app as an AI-powered Maintenance Intelligence Platform, not only as CRUD software with a chatbot.
- Existing modules such as tasks, errors, machines, documents, shift handovers, employees, and roles are data sources for AI-assisted workflows.
- Work in small, safe slices. Avoid broad rewrites.

## Hard Constraints

- Do not hardcode secrets or API keys.
- Do not change routes, database models, or production behavior unless the user explicitly asks for that change.
- Do not refactor unrelated production code.
- Do not revert user or unrelated work in a dirty worktree.
- Keep SQLite development support and PostgreSQL readiness in mind.
- Keep tests deterministic and avoid real LLM calls in CI.

## Engineering Standards

- Follow PEP8 for Python.
- Use clear functions, service boundaries, and meaningful names.
- Add docstrings to important service functions and new helper functions.
- Validate inputs and handle errors explicitly.
- Prefer existing project patterns over new abstractions.
- Use environment variables for configurable providers and secrets.

## AI/RAG Standards

- Do not index confidential employee fields or `EmployeeDocument` file content into
  `KnowledgeDocument` without an explicit data-policy change; use structured employee
  answers for personnel document metadata instead.
- Keep AI providers swappable: mock, OpenAI, OpenAI-compatible local endpoints, and future providers.
- Keep RAG source metadata prompt-safe and permission-aware.
- Preserve no-answer behavior when sources are weak or unavailable.
- Show uncertainty, confidence, sources, and evidence in AI workflows where available.
- Do not expose raw prompts, raw chunk text, private notes, or unauthorized data in diagnostics.

## Review And Test Expectations

- Before changing code, identify the affected files and the smallest safe change.
- After changes, run focused tests for the touched area.
- For AI/RAG changes, prefer focused pytest suites under `tests/test_ai_*`, `tests/test_rag_services.py`, `tests/test_retrieval_*`, and workflow tests.
- Run Ruff for touched Python files when practical.
- Explain residual risk and propose an exact commit message.

## Claude als Ersatz-Agent (SIN-205)

- Cursor zuerst. Hat Cursor kein Guthaben, setze das Label `claude` auf das Issue oder kommentiere `@claude`.
- Der Workflow `.github/workflows/claude.yml` startet Claude (`claude-code-action@v1`, nur für Nutzer mit Schreibrechten).
- Immer Draft-PR, nie selbst mergen.
- Commit-Nachrichten enthalten `Part of SIN-xxx` (die Issue-Nummer des Auftrags).
- Maximal 3 Reparaturrunden pro Pull Request, dann stoppen und den Blocker melden.
