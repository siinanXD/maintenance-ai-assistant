# Roadmap and technical debt

Living notes for maintainers. For product scope see [`FEATURES.md`](FEATURES.md).

## Open technical debt (prioritized)

| Priority | Area | Notes |
| --- | --- | --- |
| Medium | Long service modules | `ai_service.py` (1,100 lines), `retrieval_telemetry_service.py` (1,000) and `knowledge_gap_service.py` (990) each hold several concerns. Split the way `task_service` and `ai_observability_*` were split: one module per concern, cross-module names public, no re-exports |
| Small | `app/docs/openapi_extensions.py` | 3,400 lines of API examples in one file; group by blueprint |
| Small | `app/static/css/src/10-legacy/` | 3,700 lines of shared building blocks plus 340 lines in `90-overrides/token-overrides.css` that correct their token choices. Move one page at a time onto `20-components/` and delete its override entries; see `app/static/css/README.md` |
| Small | `frontend/src/admin-ai/` | Largest page; `adminAiSourceCheckModel.ts`, `AdminAiSourceCheck.tsx` and `AdminAiEffectiveness.tsx` are still around 300 lines |
| Small | `app/agent/mock_policy.py` | Offline keyword policy grows with every tool; keep golden cases in `app/agent/evals.py` in sync and prefer new `list_*` parameters over new keyword branches |

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
