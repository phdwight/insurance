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
- Rate limiting, input validation

**LangGraph Agent Service**
- Hosts the recommendation graph (see `03-agent-design.md`)
- Connects to the MCP server as an MCP *client*
- Persists conversation/graph state via LangGraph Postgres checkpointer

**App database (Postgres, `app` schema)**
- Sessions, conversation checkpoints, extracted user-needs profiles, recommendation snapshots (for shareable results)

### Policy Platform side

**Upload portal / reviewer UI** *(implemented at `:8003/admin`)*
- Single static page served by the ingestion service: upload policy documents (PDF/txt/md — the insurer and product line are detected from the document, not pre-declared), review the extracted draft side-by-side with the source, approve/reject
- Auth is a Phase 5 item — localhost-only until then

**Ingestion pipeline**
- Async workers: document parsing → LLM extraction into policy schema → validation → human review queue → publish to catalog
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

## Cross-cutting decisions

| Concern | Decision (MVP) |
|---|---|
| Language runtime | Python end-to-end backend (LangGraph, FastAPI, MCP SDK) |
| Frontend | React + Vite PWA (or Next.js if SSR wanted; PWA plugin either way) |
| Search | Hybrid: SQL filters (line, premium range, age eligibility) + pgvector semantic rerank |
| LLM access | Provider-agnostic via LangChain model bindings; pick one primary provider for MVP |
| State | LangGraph Postgres checkpointer; no Redis needed at MVP scale |
| Deployment | Single VPS or small managed platform (Fly.io/Railway/Render); Docker Compose: pwa, api, agent, mcp, worker, postgres |
| Observability | LangSmith (or Langfuse) for agent traces; structured logs elsewhere |

## Why MCP here (and its cost)

- **Benefit:** hard boundary between "what policies exist" and "how we recommend." The catalog becomes reusable by other agents/products, and tools are self-describing to the LLM.
- **Cost:** an extra network hop and service to operate. Acceptable; keep the MCP server stateless so it scales trivially.
