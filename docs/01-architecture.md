# System Architecture

## High-level diagram

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│        CUSTOMER APP         │        │         POLICY PLATFORM          │
│                             │        │                                  │
│  PWA (chat + guided UI)     │        │  Admin/Agent Upload Portal       │
│        │                    │        │        │                         │
│        ▼ HTTPS/SSE          │        │        ▼                         │
│  API Gateway (FastAPI)      │        │  Ingestion Pipeline              │
│        │                    │        │  (parse → extract → review)      │
│        ▼                    │        │        │                         │
│  LangGraph Agent Service ───┼──MCP──▶│  MCP Server (policy tools)      │
│        │                    │        │        │                         │
│        ▼                    │        │        ▼                         │
│  Postgres (app schema)      │        │  Postgres (catalog schema)       │
└─────────────────────────────┘        └──────────────────────────────────┘
```

Both parts can live in one Postgres instance (separate schemas: `app`, `catalog`) for MVP; split later if needed.

## Components

### Customer App side

**PWA frontend**
- Single-page app, installable, service worker for shell caching
- Two intake modes: free-form chat (streaming) and guided questionnaire
- Results view: ranked cards + comparison table

**API Gateway (FastAPI or similar Python service)**
- Auth (anonymous sessions for MVP; optional accounts later)
- Streams agent responses to the PWA via SSE/WebSocket
- Rate limiting, input validation — `/chat` (the only token-spending endpoint) has a per-client sliding window (`RATE_LIMIT_CHAT`, default 30/60s, keyed by first `X-Forwarded-For` hop else peer IP; 429 over limit, `off` disables)

**LangGraph Agent Service**
- Hosts the recommendation graph (see `03-agent-design.md`)
- Connects to the MCP server as an MCP *client* — read-only catalog calls are memoized for `CATALOG_CACHE_SECONDS` (60s default) so per-turn re-narrowing doesn't re-pay the MCP round-trips
- Persists conversation/graph state via LangGraph Postgres checkpointer, riding a shared connection pool (`agent/db.py`, `AGENT_DB_POOL_SIZE`) together with the explanation cache, usage ledger, and retention (scaling posture: `06-scaling.md`)

**App database (Postgres, `app` schema)**
- Sessions, conversation checkpoints, extracted user-needs profiles, recommendation snapshots (for shareable results)

### Policy Platform side

**Upload portal / reviewer UI** *(implemented at `:8003/admin`)*
- Single static page served by the ingestion service: upload policy documents (PDF/txt/md — the insurer and product line are detected from the document, not pre-declared), review the extracted draft side-by-side with the source, approve/reject
- Auth: the data surface requires `ADMIN_TOKEN` (bearer or `?token=`); empty token = open, local dev only. **Exception:** two public, tokenless endpoints serve brochure previews to end users — `GET /policies/{slug}/brochure` (cover image) and `GET /policies/{slug}/document` — but only for a *published* policy whose source `doc_type` is `brochure`/`product_summary`; a contract or unpublished slug 404s

**Ingestion pipeline**
- Durable queue + dedicated worker: the upload endpoint stores the file and enqueues a run (returns immediately); a separate `ingestion-worker` process claims runs (Postgres `FOR UPDATE SKIP LOCKED`) → parse → LLM extraction into the policy schema → human review queue → validation on approve → publish to catalog. A crashed worker's in-flight run is requeued, so a restart never strands an upload
- Details in `02-ingestion-mcp.md`

**MCP Server**
- Exposes catalog as MCP tools: `search_policies`, `get_policy`, `compare_policies`, `list_insurers`, `list_product_lines`
- Read-only for the agent; ingestion writes through its own path
- Transport: streamable HTTP (agent service and MCP server are separate processes)

**Catalog database (Postgres, `catalog` schema)**
- Normalized policy tables + pgvector embeddings for semantic search + source-document store

## Key data flows

1. **Ingestion:** Agent uploads PDF → parsed → LLM maps to schema → reviewer approves → row published to catalog + embeddings generated → immediately queryable via MCP.
2. **Recommendation:** User free-text → LangGraph extracts needs profile → agent calls MCP `search_policies` per product line → ranks/filters → composes explanation → streams to PWA.
3. **Guided mode:** Same graph, but a questionnaire node fills the needs profile field-by-field instead of the extraction node.
4. **Brochure preview:** In results, the PWA loads a policy's cover image + document **directly** from the ingestion service's public endpoints (bypassing the API/MCP path) — the one client→ingestion interaction that isn't token-gated (see the eligibility gate above).

## Cross-cutting decisions

| Concern | Decision (MVP) |
|---|---|
| Language runtime | Python end-to-end backend (LangGraph, FastAPI, MCP SDK) |
| Frontend | React + Vite PWA (or Next.js if SSR wanted; PWA plugin either way) |
| Search | Hybrid: SQL filters (line, premium range, age eligibility) + pgvector semantic rerank |
| LLM access | Provider-agnostic via LangChain model bindings; pick one primary provider for MVP |
| State | LangGraph Postgres checkpointer; no Redis needed at MVP scale |
| Deployment | Docker Compose (`docker-compose.prod.yml`, registry images): pwa, api, agent, mcp-server, ingestion, ingestion-worker, postgres; host ports from 41500; runs on a single VPS/NAS or small managed platform |
| Observability | LangSmith tracing on every LLM call (agent chat + verifier, ingestion extraction), env-var enabled; uniform timestamped logs across the uvicorn services |

## Why MCP here (and its cost)

- **Benefit:** hard boundary between "what policies exist" and "how we recommend." The catalog becomes reusable by other agents/products, and tools are self-describing to the LLM.
- **Cost:** an extra network hop and service to operate. Acceptable; keep the MCP server stateless so it scales trivially.
