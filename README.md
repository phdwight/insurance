# Insurance Recommender

A PWA where users describe their insurance needs in plain language (life, health, travel, pet) and an agentic AI suggests and compares matching policies. Policy data is ingested from insurer documents into a Postgres catalog and exposed to the agent via an MCP server.

**Market:** Philippines. **Positioning:** suggest + compare only — no quoting, binding, or selling.

**Status:** Phases 0–4 complete and deployable — policy catalog + MCP server, LangGraph agent, PWA, and the full ingestion pipeline (async queue worker). Phase 5 (hardening) is mostly done; the main remaining item is replacing the demo seed with real PH policies. See [`docs/05-roadmap.md`](docs/05-roadmap.md).

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

Postgres (with pgvector) runs on 5432. Python services form a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (Python >= 3.14). The `ingestion/` package runs as **two** services: the web/reviewer API above and a durable queue **worker** (`python -m ingestion.worker`) that parses + LLM-extracts uploads off the request path.

## API keys

| Env var | Needed for | Required? | Where to get it |
|---|---|---|---|
| `VOYAGE_API_KEY` | Semantic policy search + seed-time embeddings (voyage-3.5) | Optional — without it, search falls back to SQL premium-sorted ranking | [voyageai.com](https://www.voyageai.com/) (free tier) |
| `ANTHROPIC_API_KEY` | Agent chat + ingestion extraction (default provider) | Required for free-form chat + auto-extraction; guided mode and manual drafting work without it | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | Alternative LLM provider, and the default verifier panel (`openai:gpt-4o-mini`) | Optional | [platform.openai.com](https://platform.openai.com/) |
| `LANGSMITH_API_KEY` | LLM tracing/observability — agent chat + verifier and ingestion extraction (set `LANGSMITH_TRACING=true`) | Optional | [smith.langchain.com](https://smith.langchain.com/) (free tier) |
| `ADMIN_TOKEN` | Locks the ingestion/reviewer surface (`:8003`) | Required before exposing beyond localhost | any secret string you choose |

**Nothing is required to run the stack today** — guided mode and the pipeline work with zero keys (free-form chat and auto-extraction are what need a provider key). Postgres credentials default to `insurance`/`insurance` via compose; override in `.env` for anything non-local.

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
brochure PDF (insurer is detected from the document). The upload returns immediately
and a background **worker** parses (docling) + LLM-extracts while the page polls;
then review the extracted draft and approve to publish. Re-uploading the same file
re-runs extraction as a fresh review.

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

## Production deployment

`docker-compose.prod.yml` is the single production compose. It pulls pre-built images from GHCR (or `--build`s locally), publishes host ports **from 41500** (pwa 41500, api 41501, ingestion 41502; postgres, agent, and mcp-server stay internal), and adds restart policies, log rotation, memory limits, `/health` healthchecks, and required-secret guards.

**Images are published automatically:** merging image-affecting code to `main`
triggers the [`Publish images`](.github/workflows/publish-images.yml) workflow,
which builds all services multi-arch (amd64 + arm64, native runners) and pushes
them to GHCR tagged `:latest` and `:sha-<short>`. `deploy/push-images.sh` is the
manual fallback for building/publishing locally.

```bash
# (Manual/local alternative to CI — multi-arch amd64+arm64:)
IMAGE_PREFIX=ghcr.io/phdwight IMAGE_TAG=latest ./deploy/push-images.sh

# On the TARGET host — only this file + .env are needed:
cp .env.example .env    # set POSTGRES_PASSWORD, ADMIN_TOKEN, CORS_ORIGINS, VITE_API_URL, VITE_INGESTION_URL
docker compose -f docker-compose.prod.yml --env-file .env pull   # get the latest images
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

`CORS_ORIGINS` and `VITE_API_URL` must be the API's **public** address as seen from the browser (e.g. `http://<host>:41501`, or an HTTPS domain). `VITE_INGESTION_URL` is optional — set it to the public ingestion address to show brochure cover thumbnails + document links in results (empty = feature off; must be `https` when the PWA is `https`, or covers are blocked as mixed content). Front the published ports with a TLS-terminating reverse proxy for anything internet-facing. Ingestion parsing runs in its own `ingestion-worker` service — scale it with `docker compose ... up -d --scale ingestion-worker=N` (the queue is concurrency-safe).

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
- **Upload parsed with pypdf instead of docling** — the run's `parse_status` (shown in the `/admin` review detail) records the parser + fallback reason. Common causes: stale ingestion image (rebuild), or docling's OpenCV needing `libgl1`/`libglib2.0-0` (baked into the image via `APT_PACKAGES`; docling's models are baked in too). Parsing runs in the worker: `docker compose logs ingestion-worker | grep -i docling` has the full traceback.
- **Upload stuck in "queued" / "processing"** — the `ingestion-worker` service does the parsing/extraction; make sure it's running (`docker compose ps ingestion-worker`) and check its logs. A run a crashed worker abandoned is requeued after `WORKER_STALE_SECONDS` (default 30 min).
- **Reviewer UI auth** — set `ADMIN_TOKEN` in `.env` and the whole `:8003` data surface requires it (the page prompts for it once per browser session). Leaving it empty keeps the service open: local development only.

## Docs

Plan documents live in [`docs/`](docs/): overview, architecture, ingestion/MCP design, agent design, PWA/UX, and roadmap — plus drawio diagrams of the high-level architecture (`architecture.drawio`), the agent graph, and the ingestion pipeline, kept in sync with the implementation.
