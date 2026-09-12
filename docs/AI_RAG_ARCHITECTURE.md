# AI And RAG Architecture

This document describes the current AI/RAG structure after cleanup. It is meant
to prevent duplicate retrieval paths from reappearing.

## Public Entry Points

- `app/ai/routes.py` owns HTTP routes and response redaction; every chat
  request runs `app/agent/service.py::run_agent`.
- The agent reaches retrieval only through tools: `search_knowledge` calls
  `build_rag_context(...)`, the `search_<scope>` tools call
  `retrieve_ai_context(...)`, and the `list_*`/`count_records` tools query
  the permission-aware SQL services directly (`app/agent/queries/`).
- `app/services/rag_service.py` is the stable RAG facade with:
  - `build_rag_context(...)`
  - `answer_with_rag(...)`

## Orchestration

- `app/services/langgraph_rag_workflow.py` owns the RAG workflow nodes.
- LangGraph is optional at runtime. If graph compilation is unavailable, the
  same node functions run in deterministic fallback order.
- The facade does not expose a second pipeline-step constant. The authoritative
  node list is `LANGGRAPH_RAG_PIPELINE_STEPS` in the workflow module.

## Retrieval

- `app/services/retrieval_service.py` is the single orchestration layer for
  structured retrieval, vector retrieval, context assembly and final ranking.
- `app/services/ai_retrieval.py` remains the structured SQL retrieval component
  used by the agent's `search_<scope>` tools and the consolidated retrieval
  pipeline.
- `app/services/sql_keyword_retrieval_service.py` remains a fallback only. It is
  not a primary retrieval path.
- `app/services/vector_store_service.py` owns vector-store adapters and fallback
  behavior. Local, pgvector, Chroma and Atlas-compatible paths must stay
  available while configured deployments rely on them.
- Vector-store candidates are never authoritative by themselves. SQL remains the
  system of record for permissions, visibility, document status, quality gates
  and source-card metadata.
- Source-card route hints use `source_url(...)` from the knowledge-service
  facade so indexing, linking, network views and vector metadata share one URL
  mapping.

## Indexing And Vector Stores

- `app/services/semantic_chunking_service.py` creates semantic chunk structure
  while `app/services/chunking_service.py` stays available as the migration
  fallback.
- `app/services/knowledge_indexing_service.py` persists `KnowledgeChunk`
  records and embeddings before syncing configured external vector stores.
- `VectorRecord.embedding` carries existing chunk embeddings into external
  stores. Vector-store sync must not regenerate embeddings when chunks already
  have embeddings.
- `mongodb_atlas` is an optional external candidate store. Atlas stores synced
  chunk text, embeddings and flattened safe metadata only; business data stays
  in SQL.
- Atlas fallback diagnostics must remain visible through retrieval debug,
  vector-store diagnostics, observability metrics and governance alerts.

## Prompts

- `app/services/ai_prompting.py` owns code-level fallback prompts.
- `app/services/ai_prompt_admin_service.py` owns DB-backed prompt templates and
  resolves them over code-level fallbacks.
- Obsolete standalone prompt constants should not be added. New prompt behavior
  should go through the prompt builder functions or managed prompt templates.

## Traceability And Observability

- `app/services/ai_traceability_service.py` stores internal `AIAnswerTrace`
  records and is the system of record for answer traceability.
- `app/services/langfuse_service.py` is an optional external sink. It may receive
  sanitized correlation metadata, but not raw prompts, raw answers, chunk text,
  private paths, secrets or internal notes.
- `app/services/ai_observability_service.py` aggregates request, retrieval,
  answer-quality, vector-store and Atlas metrics without double-counting AI
  requests.
- `app/services/vector_sync_status_service.py` owns in-process vector and Atlas
  sync diagnostics used by observability and governance.

## Governance

- `app/services/ai_governance_service.py` evaluates alert rules from existing
  observability and vector-drift snapshots.
- Atlas-specific alerts reuse the same governance framework. They must not
  duplicate generic vector-store alerts when Atlas context is present.
- Alert configuration belongs in environment-backed Flask config, not hardcoded
  route or dashboard logic.

## Cleanup Guardrails

- Do not remove fallback mechanisms used by tests, local development or
  production recovery.
- Do not move modules that are imported through `app.ai.services` without a
  migration step for existing imports.
- Do not add keyword-only retrieval as a primary path. Keep it as fallback.
- Keep SQL permission checks, visibility checks, document status and quality
  gates in the retrieval path.
- Do not make Langfuse authoritative for answer traces.
- Do not expose MongoDB URIs, OpenAI keys, raw prompts, raw answers, raw chunk
  text, private file paths or internal notes in diagnostics.
- After changing the embedding provider, embedding model or vector store,
  fully reindex knowledge documents.
