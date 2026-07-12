# Insurance Recommender

A PWA where users describe their insurance needs in plain language (life, health, travel, pet) and an agentic AI suggests and compares matching policies. Policy data is ingested from insurer documents into a Postgres catalog and exposed to the agent via an MCP server.

**Market:** Philippines. **Positioning:** suggest + compare only — no quoting, binding, or selling.

**Status:** Phase 1 (catalog + MCP server) built. Agent (Phase 2) and intake UI (Phase 3) are next. See [`docs/05-roadmap.md`](docs/05-roadmap.md).

## Structure

| Path | Purpose | Port |
|---|---|---|
| `docs/` | Plan documents (start with [`00-overview.md`](docs/00-overview.md)) | — |
| `pwa/` | React PWA frontend (Vite + vite-plugin-pwa) | 5173 |
| `api/` | FastAPI gateway: sessions, SSE streaming | 8000 |
| `agent/` | LangGraph recommendation agent | 8001 |
| `mcp-server/` | Read-only MCP server over the policy catalog (`/mcp`) | 8002 |
| `ingestion/` | Policy document ingestion pipeline + upload portal | 8003 |
| `db/` | Alembic migrations + catalog seed script | — |
| `shared/` | Shared Pydantic models (policy schema, coverage types) | — |

Postgres (with pgvector) runs on 5432. Python services form a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (Python >= 3.14).

## API keys

| Env var | Needed for | Required? | Where to get it |
|---|---|---|---|
| `VOYAGE_API_KEY` | Semantic policy search + seed-time embeddings (voyage-3.5) | Optional — without it, search falls back to SQL premium-sorted ranking | [voyageai.com](https://www.voyageai.com/) (free tier) |
| `ANTHROPIC_API_KEY` | Agent LLM calls (Phase 2+; default provider) | Not yet — required once the agent is built | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | Agent LLM calls (only if you switch `LLM_MODEL` to an OpenAI model) | No | [platform.openai.com](https://platform.openai.com/) |
| `LANGSMITH_API_KEY` | Agent tracing/observability | Optional | [smith.langchain.com](https://smith.langchain.com/) (free tier) |
| `ADMIN_TOKEN` | Locks the ingestion/reviewer surface (`:8003`) | Required before exposing beyond localhost | any secret string you choose |

**Nothing is required to run the stack today.** Postgres credentials default to `insurance`/`insurance` via compose; override in `.env` for anything non-local.

## Quick start from scratch

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/), [uv](https://docs.astral.sh/uv/getting-started/installation/), git. (Node 22 only if developing the PWA outside Docker.)

```bash
# 1. Clone and configure
git clone https://github.com/phdwight/insurance.git
cd insurance
cp .env.example .env        # fill in any API keys you have (all optional for now)

# 2. Start everything: Postgres, migrations, all services, PWA
docker compose up --build

# 3. (new terminal) Seed demo policies into the catalog
docker compose run --rm migrate python db/seed.py
```

Add real policies via the **reviewer UI at http://localhost:8003/admin**: upload a
brochure PDF (insurer is detected from the document), review the extracted draft,
approve to publish. The first PDF parse downloads docling's models — expect it to
be slow once. Re-uploading the same file re-runs extraction as a fresh review.

Verify it's alive:

```bash
curl localhost:8000/health   # api
curl localhost:8001/health   # agent
curl localhost:8002/health   # mcp-server
curl localhost:8003/health   # ingestion
open http://localhost:5173   # pwa
```

Exercise the MCP server (the interesting part):

```bash
npx @modelcontextprotocol/inspector
# connect to http://localhost:8002/mcp (streamable HTTP), then call:
#   search_policies { "product_line": "travel", "max_premium": 2000 }
```

With `VOYAGE_API_KEY` set in `.env` (and re-seeding), `search_policies` ranks semantically by `needs_description`; without it, results sort by premium.

> The seed data is **fictional demo data** for pipeline validation. Replace `db/seed_data.yaml` with real policies (hand-entered from public insurer brochures) before anything user-facing.

## Local development (without Docker)

```bash
uv sync --all-packages        # installs Python 3.14 + all services (editable)
uv run pytest                 # tests
uv run ruff check .           # lint

# run one service against compose's Postgres:
docker compose up postgres migrate -d
uv run uvicorn mcp_server.main:app --port 8002

# PWA dev server:
cd pwa && npm install && npm run dev
```

Database migrations:

```bash
uv run alembic -c db/alembic.ini upgrade head      # apply
uv run alembic -c db/alembic.ini revision -m "..."  # create new
```

## Troubleshooting

- **`uv sync --locked` / CI fails with a stale lockfile** — dependencies changed without re-locking. Run `uv lock` and commit `uv.lock`.
- **`.python-version` conflicts** — this file should contain `3.14` for uv. If pyenv overwrites it with a venv name, run uv commands with `UV_PYTHON=3.14`.
- **`vector` extension errors** — the Postgres container must be the `pgvector/pgvector` image (compose handles this); a plain `postgres` volume from earlier runs won't have it. `docker compose down -v` resets.
- **Changing the embedding model** — dimension is baked into `catalog.policy_embeddings` (1024 for voyage-3.5). A different model needs a migration recreating that table plus re-seeding, and matching `EMBEDDING_MODEL`/`EMBEDDING_DIM` env vars.
- **Upload says "parsed with pypdf" instead of docling** — the upload response's `parser_note` (also shown in `/admin`) says why. Common causes: stale ingestion image (rebuild), or docling's OpenCV needing `libgl1`/`libglib2.0-0` (compose bakes these in via `APT_PACKAGES`). `docker compose logs ingestion | grep -i docling` has the full traceback.
- **Reviewer UI auth** — set `ADMIN_TOKEN` in `.env` and the whole `:8003` data surface requires it (the page prompts for it once per browser session). Leaving it empty keeps the service open: local development only.

## Docs

Plan documents live in [`docs/`](docs/): overview, architecture, ingestion/MCP design, agent design, PWA/UX, and roadmap — plus drawio diagrams of the agent graph and the ingestion pipeline, kept in sync with the implementation.
