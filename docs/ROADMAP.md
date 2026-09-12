# Roadmap and technical debt

Living notes for maintainers. For product scope see [`FEATURES.md`](FEATURES.md).

## Open technical debt (prioritized)

| Priority | Area | Notes |
| --- | --- | --- |
| Medium | `app/responses.py` | `payload.update(data)` can make root and nested `data` inconsistent |
| Medium | `app/shiftplans/services.py` | Large module; candidate for focused sub-modules |
| Small | Datetime usage | Replace remaining `datetime.utcnow()` with timezone-aware UTC |
| Small | SQLAlchemy access | Prefer `db.session.get()` over legacy query `.get()` |
| Small | Seeds | Overlap between `seed.py` and `seed_demo.py` |
| Large | `app/models.py` | Monolithic models file; split only with migration plan |
| Large | Templates / islands | Further inline JS migration to external modules where useful |
| Large | `app/ai/intent.py`, `app/ai/context.py`, `ai_*structured*` services | Rule handlers now run as the agent's structured fast path (~8k lines of keyword heuristics); migrate question types to agent tools and retire rules, then default `AI_AGENT_STRUCTURED_FAST_PATH=false` |

## New endpoint checklist

1. Route in `app/<domain>/routes.py`
2. Service in `app/services/<domain>_service.py`
3. Blueprint registration in `app/__init__.py`
4. Tests in `tests/test_<domain>.py`
5. OpenAPI entry under `app/docs/`

## Developer workflow

```bash
python run.py --host 127.0.0.1 --port 5050
python -m pytest tests/ -q
python -m ruff check .
npm run build:react
flask --app run:app db upgrade
```

AI-assisted development rules for this repository live in [`../AGENTS.md`](../AGENTS.md).
