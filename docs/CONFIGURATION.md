# Configuration and Operations

The README covers the quick start. This page lists every setting and the operational commands.

## Docker

Use one of the Compose profiles:

```bash
cp .env.example .env   # set SECRET_KEY, JWT_SECRET_KEY, OPENAI_API_KEY for mongodb profile
docker compose --profile mongodb up --build
docker compose --profile pgvector up --build   # offline pgvector + hashing fallback
```

| Profile | Vector store | Embedding | Use case |
| --- | --- | --- | --- |
| `mongodb` | MongoDB Atlas Local | OpenAI | Production-like retrieval with `$vectorSearch` |
| `pgvector` | PostgreSQL pgvector | hashing | Offline development without OpenAI |

The `mongodb` profile starts PostgreSQL, MongoDB Atlas Local, a one-shot vector-index
init container, the app, and the worker. App runs at `http://127.0.0.1:5050`.

After the first start with MongoDB retrieval enabled, reindex knowledge:

```bash
curl -X POST http://127.0.0.1:5050/api/v1/admin/ai/knowledge/reindex \
  -H "Authorization: Bearer <token>"
```

Local Atlas index maintenance:

```bash
flask --app run:app atlas ensure-index
python scripts/rag_atlas_smoke.py
```

Minimal and production env templates:

- [`.env.minimal.example`](.env.minimal.example) for SQLite + mock AI
- [`.env.production.example`](.env.production.example) for PostgreSQL + MongoDB Atlas + OpenAI

Legacy single-profile command:

```bash
cp .env.example .env   # set SECRET_KEY and JWT_SECRET_KEY
docker compose up --build
```

This requires an explicit profile because app and worker services are profile-scoped.

Health checks:

```bash
curl http://127.0.0.1:5050/health
curl http://127.0.0.1:5050/health/ready
```

`/health/ready` returns a redacted JSON payload with `ready`,
`degraded_components`, and `components` for `database`, `ai`, and `rag`. The
AI component checks both chat provider readiness and embedding provider
readiness without external API calls. Provider or embedding misconfiguration is
reported through safe reasons such as `base_url_missing`,
`unsupported_provider`, or `embedding_base_url_missing`.

Production containers should set `AUTO_CREATE_DATABASE=false` and run
`flask --app run:app db upgrade` during release before starting Gunicorn.
Persistent volumes are configured for PostgreSQL, data, documents, manuals,
knowledge, logs, and backups. Secrets must come from `.env`, never from the
image.

Before releasing to production, use
[`docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md`](docs/PRODUCTION_DEPLOYMENT_CHECKLIST.md)
to verify configuration, secrets, migrations, health checks, observability,
governance, reindexing, backups and rollback readiness.
Release history is tracked in [`CHANGELOG.md`](CHANGELOG.md).

## Configuration

Copy `.env.example` to `.env` and set these values:

```env
SECRET_KEY=                  # set in .env; keep empty in examples
JWT_SECRET_KEY=              # set in .env; keep empty in examples
ENABLE_API_DOCS=true         # default is false when FLASK_ENV=production
API_DOCS_REQUIRE_MASTER_ADMIN=false  # default is true when FLASK_ENV=production
DATABASE_URL=sqlite:///data/maintenance.db
# Docker/Postgres:
# DATABASE_URL=postgresql+psycopg://maintenance:${POSTGRES_PASSWORD}@db:5432/maintenance
POSTGRES_PASSWORD=
AUTO_CREATE_DATABASE=true  # set false in production and run migrations
AI_PROVIDER=openai          # openai, openai_compatible, or mock
OPENAI_API_KEY=             # leave empty to use local fallback
AI_BASE_URL=                # set for OpenAI-compatible local APIs, e.g. http://127.0.0.1:11434/v1
OPENAI_MODEL=gpt-4o-mini
AI_TASK_PRIORITIZATION_TIMEOUT_SECONDS=6
AI_TASK_PRIORITIZATION_MAX_RETRIES=0
AI_CHAT_RATE_LIMIT_PER_MINUTE=30    # per-user limit for AI chat/assistant calls, 0 disables
AI_DAILY_TOKEN_BUDGET_PER_USER=0    # optional per-user daily token cap, 0 disables
AI_AGENT_MAX_ITERATIONS=4
AI_AGENT_ACTION_TTL_SECONDS=600
AI_AGENT_CHECKPOINTER=auto          # session memory: auto, none, memory, sqlite, postgres
AI_AGENT_CHECKPOINT_PATH=data/agent_checkpoints.sqlite
LANGFUSE_ENABLED=false      # set true to trace OpenAI calls in Langfuse
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_RELEASE=
GITHUB_REPOSITORY=siinanXD/maintenance-ai-assistant
GITHUB_SHA=
GITHUB_REF_NAME=
RAG_ENABLED=true
RAG_VECTOR_STORE=pgvector   # pgvector primary; local, chroma or mongodb_atlas optional
MONGODB_ATLAS_URI=          # required only when RAG_VECTOR_STORE=mongodb_atlas
MONGODB_ATLAS_DATABASE=maintenance_ai
MONGODB_ATLAS_VECTOR_COLLECTION=knowledge_vectors
MONGODB_ATLAS_VECTOR_INDEX=knowledge_vector_index
MONGODB_ATLAS_TIMEOUT_MS=3000
RAG_CHUNKING_MODE=hybrid_semantic
RAG_CHUNK_SIZE=1400
RAG_CHUNK_OVERLAP=160
RAG_SEMANTIC_BREAKPOINT_THRESHOLD=0.35
RAG_SEMANTIC_MIN_CHUNK_CHARS=600
RAG_SEMANTIC_TARGET_CHUNK_CHARS=1200
RAG_SEMANTIC_MAX_CHUNK_CHARS=1800
RAG_TOP_K=4
RAG_RERANK_CANDIDATE_LIMIT=20
RAG_SCAN_LIMIT=300
RAG_MIN_SCORE=1
RAG_SCORE_DEBUG=false       # true exposes score components to admins/tests only
RAG_SCORE_SEMANTIC_WEIGHT=70
RAG_SCORE_LEXICAL_WEIGHT=60
RAG_SCORE_QUALITY_WEIGHT=30
RAG_SCORE_RECENCY_WEIGHT=15
RAG_SCORE_MACHINE_WEIGHT=50
RAG_SCORE_FEEDBACK_WEIGHT=20
RAG_SCORE_USAGE_WEIGHT=15
RAG_SCORE_SOURCE_PRIORITY_WEIGHT=15
RAG_RECENCY_WINDOW_DAYS=90
RAG_AGING_OUTDATED_MULTIPLIER=0.55
RAG_AGING_STALE_MULTIPLIER=0.65
RAG_AGING_OLD_MULTIPLIER=0.78
RAG_FEEDBACK_SCAN_LIMIT=300
RAG_SEMANTIC_ONLY_MIN_SIMILARITY=0.78
KNOWLEDGE_GAP_DEDUP_HOURS=24
KNOWLEDGE_GAP_LOW_CONFIDENCE_SCORE=35
KNOWLEDGE_AGING_STALE_DAYS=180
KNOWLEDGE_AGING_UNCONFIRMED_DAYS=60
KNOWLEDGE_AGING_STABLE_CONFIRMATIONS=3
KNOWLEDGE_AGING_STABLE_HELPFUL_FEEDBACK=3
AI_SESSION_CONTEXT_MESSAGES=4
AI_SESSION_CONTEXT_TTL_MINUTES=120
AI_SESSION_CONTEXT_MAX_CHARS=1400
RETRIEVAL_TELEMETRY_WINDOW_DAYS=30
RETRIEVAL_TELEMETRY_LIMIT=10
RETRIEVAL_TELEMETRY_LOW_CONFIDENCE_SCORE=35
RETRIEVAL_TELEMETRY_LOW_SOURCE_SCORE=20
AI_GOVERNANCE_ALERTS_ENABLED=true
AI_GOVERNANCE_HIGH_NO_SOURCE_RATE_WARNING=0.2
AI_GOVERNANCE_HIGH_NO_SOURCE_RATE_CRITICAL=0.4
AI_GOVERNANCE_RETRIEVAL_DEGRADATION_WARNING=0.8
AI_GOVERNANCE_RETRIEVAL_DEGRADATION_CRITICAL=0.6
AI_GOVERNANCE_RETRIEVAL_LATENCY_WARNING=1200
AI_GOVERNANCE_RETRIEVAL_LATENCY_CRITICAL=3000
AI_GOVERNANCE_EXCESSIVE_TOKEN_USAGE_WARNING=100000
AI_GOVERNANCE_EXCESSIVE_TOKEN_USAGE_CRITICAL=250000
AI_GOVERNANCE_HALLUCINATION_RISK_WARNING=1
AI_GOVERNANCE_HALLUCINATION_RISK_CRITICAL=5
AI_GOVERNANCE_SYNC_FAILURES_WARNING=1
AI_GOVERNANCE_SYNC_FAILURES_CRITICAL=3
AI_GOVERNANCE_ATLAS_ERRORS_WARNING=1
AI_GOVERNANCE_ATLAS_ERRORS_CRITICAL=3
AI_GOVERNANCE_ATLAS_UNAVAILABLE_WARNING=1
AI_GOVERNANCE_ATLAS_UNAVAILABLE_CRITICAL=1
AI_GOVERNANCE_ATLAS_FALLBACKS_WARNING=1
AI_GOVERNANCE_ATLAS_FALLBACKS_CRITICAL=1
AI_GOVERNANCE_ATLAS_SYNC_FAILURES_WARNING=1
AI_GOVERNANCE_ATLAS_SYNC_FAILURES_CRITICAL=3
AI_GOVERNANCE_ATLAS_SYNC_DRIFT_WARNING=1
AI_GOVERNANCE_ATLAS_SYNC_DRIFT_CRITICAL=1
AI_GOVERNANCE_ATLAS_LATENCY_DEGRADATION_WARNING=500
AI_GOVERNANCE_ATLAS_LATENCY_DEGRADATION_CRITICAL=1500
AI_GOVERNANCE_ATLAS_RETRIEVAL_DEGRADATION_WARNING=0.8
AI_GOVERNANCE_ATLAS_RETRIEVAL_DEGRADATION_CRITICAL=0.6
AI_GOVERNANCE_COST_SPIKE_MIN_USD=0.01
AI_GOVERNANCE_COST_SPIKE_MULTIPLIER_WARNING=2.0
AI_GOVERNANCE_COST_SPIKE_MULTIPLIER_CRITICAL=3.0
EMBEDDING_PROVIDER=openai  # production default; requires OPENAI_API_KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
RAG_HASH_EMBEDDING_DIMENSIONS=384  # hashing fallback/test dimensions
KNOWLEDGE_FOLDER=knowledge
BACKUP_FOLDER=backups
OPERATIONS_HASH_SECRET=     # optional; defaults to SECRET_KEY
OPERATIONS_EVENT_RETENTION_MONTHS=24
DOCUMENTS_FOLDER=documents
MANUALS_FOLDER=manuals
ATTACHMENT_MAX_BYTES=10485760   # photos and PDFs on incidents and tasks
PUBLIC_BASE_URL=                # address printed into machine QR labels
PLANT_TIMEZONE=Europe/Berlin     # "today", "tomorrow" and "this week" in assistant answers
MAIL_ENABLED=false
MAIL_HOST=
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM=
MAIL_USE_TLS=true
MAIL_DRY_RUN=true
WORKER_RAG_REINDEX_ENABLED=false
WORKER_POLL_SECONDS=60
WORKER_JOB_LEASE_SECONDS=900
```

`.env` is excluded from version control. Never commit real secrets.
For production deployments set `AUTO_CREATE_DATABASE=false` and run
`flask --app run:app db upgrade` during release.
`python seed.py production` never creates demo passwords. It only creates an
initial admin when `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` are set.
For mail, keep `MAIL_DRY_RUN=true` until SMTP credentials are verified. Dry-run
creates delivery records but does not open an SMTP connection.
Documents and manuals are stored below `DOCUMENTS_FOLDER` and `MANUALS_FOLDER`.
Keep both folders on persistent storage in production.

AI costs are calculated from OpenAI token usage and optional `AI_PRICE_*`
settings in `.env`. Values are USD per 1M tokens. If no price keys are set,
admin dashboards keep costs at `$0.0000` and show `Kosten nicht konfiguriert`
instead of inventing prices. Langfuse is optional and remains an external
observability sink; the internal `AIAnswerTrace` table is the system of record
for answer evidence. Langfuse receives only sanitized metadata such as
pseudonymous app user IDs (`user:3`), role, session ID, chat/answer trace IDs,
source/chunk counts, workflow/model labels, and GitHub repository/commit
metadata. Raw prompts, raw answers, raw chunk text, private paths and secrets
are not sent. For the default models, configure keys such as
`AI_PRICE_GPT_4O_MINI_INPUT_PER_1M`, `AI_PRICE_GPT_4O_MINI_OUTPUT_PER_1M`,
`AI_PRICE_GPT_5_MINI_INPUT_PER_1M`, and `AI_PRICE_GPT_5_MINI_OUTPUT_PER_1M`.

### Scheduled Notifications

No background scheduler runs inside Flask. Configure Windows Task Scheduler,
Cron, or your platform scheduler to call the idempotent CLI jobs:

```bash
flask --app run:app notifications send-task-alerts
flask --app run:app notifications send-overdue-reminders
flask --app run:app notifications send-ai-alerts
flask --app run:app notifications send-daily-briefings
```

Suggested cadence: task alerts every 15 minutes, overdue reminders hourly, AI
alerts every 15 minutes, daily briefings once per day around
`DAILY_BRIEFING_TIME`.

### Background Worker

Docker Compose includes a separate `worker` process:

```bash
python -m app.worker
```

The worker currently processes stale/pending RAG knowledge documents at a
configurable interval when jobs are queued. Enable it with
`WORKER_RAG_REINDEX_ENABLED=true` and tune `WORKER_POLL_SECONDS`.

RAG reindex jobs can be queued and inspected through the admin API:

```http
POST /api/v1/admin/ai/knowledge/reindex/jobs
GET /api/v1/admin/jobs?job_type=rag_reindex
```

The first supported job type is `rag_reindex` with payload modes `stale`,
`all`, or `document`. This keeps the web process ready for future queue engines
such as RQ or Celery without moving long-running indexing work into request
handlers.
