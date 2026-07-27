# Insurance Recommender

[![CI](https://github.com/phdwight/insurance/actions/workflows/ci.yml/badge.svg)](https://github.com/phdwight/insurance/actions/workflows/ci.yml)
[![Publish images](https://github.com/phdwight/insurance/actions/workflows/publish-images.yml/badge.svg)](https://github.com/phdwight/insurance/actions/workflows/publish-images.yml)
[![version](https://img.shields.io/github/v/tag/phdwight/insurance?label=version)](https://github.com/phdwight/insurance/tags)
[![license](https://img.shields.io/github/license/phdwight/insurance)](LICENSE)
[![python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/)

A PWA where users describe their insurance needs in plain language (life, health, travel, pet) and an agentic AI suggests and compares matching policies. Policy data is ingested from insurer documents into a Postgres catalog and exposed to the agent via an MCP server.

**Market:** Philippines. **Positioning:** suggest + compare only — no quoting, binding, or selling. This is not insurance advice; see the [disclaimer](docs/disclaimer.md).

## How it works

1. **Ingest** — a reviewer drops an insurer brochure into `/admin`. A vision model triages the PDF (transcribing image-heavy scans itself, else routing to docling), an intake gate rejects non-insurance uploads and redacts PII, an LLM extracts a structured draft, and **a human approves before anything is published**.
2. **Elicit** — the agent fetches candidate policies from the catalog *first*, then asks only questions whose answers actually split the remaining candidates. There are no hard-coded questionnaires; guided mode runs with zero LLM keys.
3. **Verify** — every recommendation passes a programmatic guardrail against real catalog fields, then a cross-provider LLM judge panel fact-checks each written claim. Unsupported claims are dropped, never shown.
4. **Answer honestly** — a no-match is a valid outcome, and it explains *which answer excluded which policy* rather than forcing a fit.

## Quick start

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/), [uv](https://docs.astral.sh/uv/getting-started/installation/), git. (Node 22 only if developing the PWA outside Docker.)

```bash
git clone https://github.com/phdwight/insurance.git
cd insurance
cp .env.example .env        # fill in any API keys you have (all optional)

docker compose up --build   # Postgres, migrations, all services, PWA

# in a second terminal — seed demo policies into the catalog
docker compose run --rm migrate python db/seed.py
```

Then open **http://localhost:5173**. Check everything is alive:

```bash
curl localhost:8000/health   # api        {"status":"ok","service":"api","version":"..."}
curl localhost:8001/health   # agent
curl localhost:8002/health   # mcp-server
curl localhost:8003/health   # ingestion
```

> The seed data is **fictional demo data** for pipeline validation. Replace `db/seed_data.yaml` with real policies (hand-entered from public insurer brochures) before anything user-facing.

## Usage

**Add a policy** via the reviewer UI at **http://localhost:8003/admin**: upload a brochure PDF — the insurer is detected from the document, so nothing is pre-selected. The upload returns immediately while a background worker triages the PDF (vision transcription or docling) and LLM-extracts a draft; review it and approve to publish. Re-uploading the same file re-runs extraction as a fresh review, and approving a slug that already exists publishes a **new version** (history is kept).

**Query the catalog over MCP** — the interesting part:

```bash
npx @modelcontextprotocol/inspector
# connect to http://localhost:8002/mcp (streamable HTTP), then call:
#   search_policies { "product_line": "travel", "max_premium": 2000 }
```

With `VOYAGE_API_KEY` set (and after re-seeding), `search_policies` ranks semantically by `needs_description`; without it, results sort by premium.

## Configuration

### API keys

| Env var | Needed for | Required? | Where to get it |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Agent chat + ingestion extraction (default provider) | Required for free-form chat + auto-extraction; guided mode and manual drafting work without it | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | Alternative provider, and half the default verifier panel (`openai:gpt-4o-mini`) | Optional | [platform.openai.com](https://platform.openai.com/) |
| `VOYAGE_API_KEY` | Semantic policy search + seed-time embeddings (voyage-3.5) | Optional — without it, search falls back to SQL premium-sorted ranking | [voyageai.com](https://www.voyageai.com/) (free tier) |
| `LANGSMITH_API_KEY` | Per-call LLM tracing (set `LANGSMITH_TRACING=true`) | Optional — `/ops/usage` gives token accounting without it | [smith.langchain.com](https://smith.langchain.com/) (free tier) |
| `ADMIN_TOKEN` | Locks the ingestion/reviewer surface (`:8003`) | Required before exposing beyond localhost | any secret string you choose |

**Nothing is required to run the stack** — guided mode and the pipeline work with zero keys (free-form chat and auto-extraction are what need a provider key). Postgres credentials default to `insurance`/`insurance` via compose; override in `.env` for anything non-local.

### Model roster

Six models in three tiers, two per tier. The code uses each tier's `_1` slot; `_2` is a vetted alternate you promote by copying it into `_1`. Legacy `LLM_MODEL` / `LLM_MODEL_SMALL` are still honored as the large/small fallback.

| Tier | Env vars | Used by |
|---|---|---|
| large | `LLM_MODEL_LARGE_1` / `_2` | the writer (user-facing match explanations) |
| mid | `LLM_MODEL_MID_1` / `_2` | ingestion vision triage, intake gate, approve auto-correction |
| small | `LLM_MODEL_SMALL_1` / `_2` | profile extraction, policy-draft extraction |
| judges | `VERIFIER_MODELS` | the groundedness panel (≥2, ideally cross-provider) |

Model strings are provider-agnostic ([`init_chat_model`](https://python.langchain.com/docs/how_to/chat_models_universal_init/) format, `provider:model`). Any OpenAI model is routed through the Responses API automatically.

### Cost controls

LLM spend scales with the **catalog**, not with users — see [`docs/06-scaling.md`](docs/06-scaling.md).

| Env var | Effect |
|---|---|
| `EXPLANATION_CACHE` (`auto`) | Writer + judge panel run once per *outcome bucket* (same answers × same policy versions, content-hashed); later users get the verified result with zero LLM calls. Self-invalidating. |
| `LLM_ECONOMY` (`full`) | Spend kill switch: `full` → `lean` (drop the judge panel) → `deterministic` (zero LLM — explanations render from verified catalog fields). Every rung stays honest and usable. |
| `DAILY_TOKEN_BUDGET` (`0`) | Logs a once-per-day warning when the day's tokens cross it. Alarm only — blocks nothing. |
| `RATE_LIMIT_CHAT` (`30/60`) | Per-client sliding window on `/chat`, the only token-spending endpoint. `off` disables. |

Chip taps and bare-number answers skip the extractor LLM entirely (the deterministic parser already consumed them), so a returning user's whole conversation can cost zero tokens. `GET /ops/usage` reports tokens by day/model/role, with cache hits recorded as zero-token rows.

## Architecture

| Path | Purpose | Port |
|---|---|---|
| `pwa/` | React PWA frontend (Vite + vite-plugin-pwa) | 5173 |
| `api/` | FastAPI gateway: SSE streaming, rate limiting, public file proxy | 8000 |
| `agent/` | LangGraph recommendation agent | 8001 |
| `mcp-server/` | Read-only MCP server over the policy catalog (`/mcp`) | 8002 |
| `ingestion/` | Policy document ingestion pipeline + reviewer portal | 8003 |
| `db/` | Alembic migrations + catalog seed script | — |
| `shared/` | Shared Pydantic models (policy schema, coverage types) | — |
| `docs/` | Design documents + drawio diagrams | — |
| `deploy/` | Manual multi-arch image publish script | — |
| `harness/` | Engineering conventions this repo is maintained by | — |
| `VERSION` | Release floor/seed — git tags are the source of truth | — |

Postgres (with pgvector) runs on 5432. Python services form a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (Python >= 3.14). The `ingestion/` package runs as **two** services: the web/reviewer API above and a durable queue **worker** (`python -m ingestion.worker`) that parses + LLM-extracts uploads off the request path.

### HTTP surface

| Service | Endpoints |
|---|---|
| `api` :8000 | `POST /chat` (SSE, rate-limited) · `GET /product-lines` · `GET /compare?slugs=a,b` · `GET /policies/{slug}/brochure` · `GET /policies/{slug}/document` · `GET /health` |
| `agent` :8001 | `POST /chat` (SSE) · `GET /ops/usage` (LLM spend ledger) · `GET /health` |
| `mcp-server` :8002 | `/mcp` (streamable HTTP; tools: `list_product_lines`, `list_insurers`, `search_policies`, `get_policy`, `compare_policies`) · `GET /product-lines` · `GET /compare` · `GET /health` |
| `ingestion` :8003 | `GET /admin` (reviewer UI) · `POST /documents` · `GET /reviews[/{id}]` · `POST /reviews/{id}/{approve,reject}` · `GET /stats` · `GET /insurers` · public `GET /policies/{slug}/{brochure,document}` · `GET /health` |

Everything except `/health`, `/admin`, and the public brochure endpoints requires `ADMIN_TOKEN` on the ingestion service.

## Development

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
uv run alembic -c db/alembic.ini upgrade head       # apply
uv run alembic -c db/alembic.ini revision -m "..."  # create new
```

`uv run pytest`, `uv run ruff check .`, and (for PWA changes) `npm run build` must all pass before a commit. [`CLAUDE.md`](CLAUDE.md) records the conventions and the architecture decisions in force; [`harness/`](harness/) holds the reusable engineering practices.

## Deployment

`docker-compose.prod.yml` is the single production compose. It pulls pre-built images from GHCR (or `--build`s locally), publishes host ports **from 41500** (pwa 41500, api 41501, ingestion 41502; postgres, agent, and mcp-server stay internal), and adds restart policies, log rotation, memory limits, `/health` healthchecks, and required-secret guards.

```bash
# On the TARGET host — only this file + .env are needed:
cp .env.example .env    # set POSTGRES_PASSWORD, ADMIN_TOKEN, CORS_ORIGINS, VITE_API_URL
docker compose -f docker-compose.prod.yml --env-file .env pull
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

`CORS_ORIGINS` and `VITE_API_URL` must be the API's **public** address as seen from the browser. Leave **`VITE_INGESTION_URL` empty** — brochure covers and documents are proxied by the API gateway, so the ingestion host can sit entirely behind an access layer (e.g. Cloudflare Access). Only set it to serve those files from a different *public* host; pointing it at an access-gated host silently breaks covers, because a browser `<img>` can't authenticate. Front the published ports with a TLS-terminating reverse proxy for anything internet-facing.

Ingestion parsing runs in its own `ingestion-worker` service — scale it with `docker compose ... up -d --scale ingestion-worker=N` (the queue is concurrency-safe). Migrations run automatically: the `migrate` service applies Alembic to head before the app services start, so `pull` + `up -d` is the whole upgrade.

### Versioning & releases

**Every merge to `main` cuts a release.** There is nothing to bump by hand:

1. CI runs the full suite (the same one that gates a PR — `ci.yml` is reused, not duplicated).
2. On green, it computes the next version and pushes an annotated **`vX.Y.Z` git tag**. Only the tag is pushed — never a commit, because `main` is protected and a CI commit would be rejected.
3. Images whose inputs changed are rebuilt **with that version baked in**, then *every* image — including unchanged ones, re-tagged from its existing digest — gets the `:X.Y.Z` tag. So `IMAGE_TAG=X.Y.Z` always pulls a complete, coherent stack and is a real rollback point.
4. The workflow verifies each tag resolves and that rebuilt images carry the version *inside* them.

The version source of truth is **git tags**; the committed [`VERSION`](VERSION) file is the seed for the first release and the **floor**:

```bash
# patch release: nothing to do — merging is enough (0.1.4 -> 0.1.5)
# minor/major:   raise the floor in the same PR, and that becomes the release
echo 0.2.0 > VERSION     # next merge releases v0.2.0, then v0.2.1, v0.2.2 ...
```

Cutting a GitHub release reuses the tag CI already made — never let it create one:

```bash
gh release create v0.2.0 --verify-tag --notes "…"
```

**Everything reports the same number.** Each service returns it from `/health`, and the PWA shows it in the footer and serves it at `/VERSION`. At runtime the version resolves as `APP_VERSION` env → the baked `VERSION` file → `0.0.0+dev`, and anything that is **not** a published artifact gets a `+dev` suffix (detected by the absence of the `BUILD_ID` CI writes for every image it publishes). So a source checkout reports `0.1.1+dev` — the floor, plainly marked — rather than claiming to be release 0.1.1. `docker-compose.prod.yml` passes `APP_VERSION=$IMAGE_TAG`, so a version-pinned deploy reports that release across every service.

Images are published automatically by the [`Publish images`](.github/workflows/publish-images.yml) workflow (multi-arch amd64 + arm64 on native runners); `deploy/push-images.sh` is the manual fallback.

### Image hygiene

Published images carry no secrets and no dev baggage: `.dockerignore` keeps `.env`, the local `.venv`, `pwa/`, `samples/`, `docs/`, and tests out of the build context, and `uv sync --no-cache` keeps uv's download cache out of the final layer. `deploy/push-images.sh` refuses to publish if `.env` is ever reachable in the build context, and `tests/test_image_hygiene.py` fails CI if those guards are weakened.

## Troubleshooting

- **`uv sync --locked` / CI fails with a stale lockfile** — dependencies changed without re-locking. Run `uv lock` and commit `uv.lock`.
- **`.python-version` conflicts** — this file should contain `3.14` for uv. If pyenv overwrites it with a venv name, run uv commands with `UV_PYTHON=3.14`.
- **`vector` extension errors** — the Postgres container must be the `pgvector/pgvector` image (compose handles this); a plain `postgres` volume from earlier runs won't have it. `docker compose down -v` resets.
- **Changing the embedding model** — dimension is baked into `catalog.policy_embeddings` (1024 for voyage-3.5). A different model needs a migration recreating that table plus re-seeding, and matching `EMBEDDING_MODEL`/`EMBEDDING_DIM` env vars.
- **Upload parsed with pypdf instead of docling** — the run's `parse_status` (shown in the `/admin` review detail) records the parser + fallback reason. Common causes: stale ingestion image (rebuild), or docling's OpenCV needing `libgl1`/`libglib2.0-0` (baked into the image via `APT_PACKAGES`; docling's models are baked in too). Parsing runs in the worker: `docker compose logs ingestion-worker | grep -i docling` has the full traceback.
- **Image build fails downloading docling models** — Hugging Face Hub was flaky; the build retries 5× with backoff before failing. Re-run once [status.huggingface.co](https://status.huggingface.co/) is green.
- **Upload stuck in "queued" / "processing"** — the `ingestion-worker` service does the parsing/extraction; make sure it's running (`docker compose ps ingestion-worker`) and check its logs. A run a crashed worker abandoned is requeued after `WORKER_STALE_SECONDS` (default 30 min).
- **Reviewer UI auth** — set `ADMIN_TOKEN` in `.env` and the whole `:8003` data surface requires it (the page prompts for it once per browser session). Leaving it empty keeps the service open: local development only.
- **Brochure covers missing in results** — the PWA loads them from the API gateway by default. If `VITE_INGESTION_URL` points at a host behind an access layer, covers fall back to the placeholder; clear it. Files are served only for published policies whose source doc type is a brochure/product summary — contracts never are.
- **A policy you just published doesn't appear** — read-only catalog calls are cached for `CATALOG_CACHE_SECONDS` (60s default), so new policies reach fresh conversations within a minute.
- **"No policy matches" for a policy you know exists** — the message names which answer excluded which policy (matching is fully deterministic, never an LLM guess). Check the stated eligibility band or attribute against the answer given.

## Documentation

Design documents live in [`docs/`](docs/):

| Doc | Contents |
|---|---|
| [`00-overview.md`](docs/00-overview.md) | Vision, differentiation, scope, PH compliance |
| [`01-architecture.md`](docs/01-architecture.md) | Components, data flows, stack decisions |
| [`02-ingestion-mcp.md`](docs/02-ingestion-mcp.md) | Pipeline, catalog schema, MCP tools |
| [`03-agent-design.md`](docs/03-agent-design.md) | LangGraph state, graph, guardrails, evals |
| [`04-pwa-ux.md`](docs/04-pwa-ux.md) | Screens, PWA capabilities, streaming protocol |
| [`05-roadmap.md`](docs/05-roadmap.md) | Delivery plan, risks, open questions |
| [`06-scaling.md`](docs/06-scaling.md) | Scaling posture: what's ready, and the trigger for each next step |
| [`disclaimer.md`](docs/disclaimer.md) | Canonical legal notice, mirrored into both UIs |

Drawio diagrams of the high-level architecture (`architecture.drawio`), the agent graph, and the ingestion pipeline live alongside them and are kept in sync with the implementation.

## Contributing

Read [`CLAUDE.md`](CLAUDE.md) first — it records the architecture decisions in force and the conventions (documentation, diagrams, implementation, and tests move together in the same commit). Work happens on `develop` and reaches `main` via pull request; `uv run pytest`, `uv run ruff check .`, and `npm run build` (for PWA changes) must pass.

## License

Licensed under the [Apache License 2.0](LICENSE).

> **Not insurance advice.** This project suggests and compares publicly published policy information; it does not quote, bind, or sell insurance, and it is not a licensed insurance intermediary. Every result carries its source and an "as of" date — confirm final terms with the insurer. See the full [disclaimer](docs/disclaimer.md).
