# Engineering conventions

Guidance for AI-assisted and human development on this repo. Read alongside `docs/`.

## Architecture decisions in force

- **Catalog drives the conversation.** Never reintroduce static intake forms or hard-coded question lists. Questions exist only because current candidate policies disagree on an attribute (`agent/discriminators.py`). New differentiating policy fields get a registry entry, not a form field.
- **Abstractions are introduced on trigger, not speculatively.** Current seams (module functions, monkeypatchable in tests) are deliberate. Introduce `Protocol`-based abstractions ONLY when a concrete trigger appears:
  - a second catalog source (anything beyond the MCP policy-catalog server) → introduce a `CatalogClient` protocol in `agent/`,
  - a model-provider abstraction beyond `init_chat_model` strings (e.g. self-hosted models, per-tenant routing) → introduce an `LLMProvider` protocol in `agent/llm.py`,
  - a second ingestion source type with different parsing (insurer API feeds, scraping) → protocol in `ingestion/`.
  Until then, keep functions flat. Do not add interfaces "for testability" — tests already patch the module seams.
- **Verification is layered and mandatory:** SQL truth → programmatic checks (`agent/verify.py`) → cross-provider unanimous LLM panel (`agent/verifier.py`). New user-visible claims about policies must be grounded in catalog fields and pass through these layers.
- **Guided mode must always work with zero LLM keys.** Any new question type needs a deterministic parser, and choice options must round-trip through their own parser (tested in `test_discriminators.py`).
- **Anti-loop guardrails are load-bearing** (`MAX_QUESTIONS`, `MAX_BOOTSTRAP_TURNS`, `MAX_TURNS`, `recursion_limit`). Don't remove; extend tests if you change them.

## Code style

- SOLID/DRY/clean code; but cohesion over ceremony — no speculative layers (see trigger rule above).
- All LLM prompts, structured-output contracts, and user-facing copy live in `agent/prompts.py`. No prompt or user-facing string literals inside node/logic modules.
- Model tiers: a roster of **6 models in 3 tiers, 2 per tier** (`LLM_MODEL_{LARGE,MID,SMALL}_{1,2}`; the code uses each tier's `_1`, `_2` is a documented swap-in). Role→tier: **writer = large**, **vision triage / intake gate / auto-correction = mid**, **extractors = small**, **judges = `VERIFIER_MODELS`** (≥2, cross-provider). Legacy `LLM_MODEL`/`LLM_MODEL_SMALL` stay honored as the large/small fallback. Resolution lives in `agent/config.py` (agent) and `ingestion/models.py` (ingestion); keep new LLM call sites asking for a *tier*, not a hard-coded model. Documented in `.env.example`.
- **LLM structured-output contracts** (lessons already paid for): strip server-managed fields (`id`, `version`, `verified_at`…) from extraction schemas so models can't fill them with document noise; keep schemas provider-compatible — OpenAI rejects `oneOf`/`discriminator` (rewrite to `anyOf`) and strict json_schema can't express open-ended maps (use `method="function_calling"`); partial extractions go to human review, never discarded; normalize printed formats (money like `₱2.5M`, dates like `06-Apr-2025`) deterministically and let genuinely unparseable values fail validation loudly.
- Python >= 3.14, `uv` workspace. After changing any `pyproject.toml`, run `uv lock` and commit `uv.lock` (CI uses `--locked`).
- Every recommendation surface must carry `verified_at`, `source_url`, and the informational-only disclaimer (PH Insurance Commission positioning: suggest + compare, never solicit or bind).

## Verification before commit

`uv run ruff check .` and `uv run pytest` must pass; PWA changes also need `npm run build` in `pwa/`.

## Decision log (owner-confirmed)

Product and process decisions made by the project owner across sessions. Don't relitigate these without asking.

### Product
- **Market:** Philippines first. Positioning is suggest + compare only — never quote, bind, sell, or solicit (Insurance Commission licensing line). Every result carries `verified_at`, `source_url`, and an informational-only disclaimer.
- **Product lines (MVP):** life, health, travel, pet.
- **Policy data intake:** the reviewer just uploads a file (no insurer/type declared). manual/document upload → parse (PDFs: the **mid-tier** vision model triages each upload — transcribe image-heavy/scanned docs to markdown itself, else docling; `VISION_TRIAGE`) → intake gate (the **mid-tier** model **rejects non-insurance uploads** as `rejected_invalid` and **redacts PII** from the derived text; `INTAKE_GATE`, fails open) → LLM extraction → **mandatory human review** → publish. The original file stays for the token-gated reviewer; only derived text is redacted. No insurer APIs or scraping for MVP. Tables are extracted into structured JSONB fields and queried with SQL — they never reach the embedder.
- **The insurer is detected from the document, not pre-declared.** Extraction reads `insurer_name` off the brochure, the reviewer confirms it, and publish get-or-creates the insurer — that's how new insurers enter the catalog. Never make the uploader pre-select from a dropdown of existing insurers.
- **Re-uploading the same document is a feature, not an error.** Hash-dedupe reuses the stored file, but each upload creates a fresh extraction run (the redo workflow after a poor parse/extraction). **Re-approving an existing policy (same slug) re-versions it** — the current `policy_version` is superseded and a new one becomes current — rather than being blocked; history is preserved and readers only surface the current version.
- **Approval failures auto-repair before falling back to the human.** Extraction is non-deterministic, so a draft that fails validation on approve often succeeds on a re-upload. Instead of dead-ending, the **mid-tier** model re-reads the document **visually** with the exact validation error and returns a corrected draft for another human approval — at most **3 passes** (`correction_attempts`), then the error is surfaced for a manual fix. Runs synchronously in the approve call; fails safe (any error just surfaces the original validation error). The ingestion **web** service therefore needs the mid-tier model configured, not just the worker.
- **Parser fallbacks must be visible.** A docling→pypdf fallback carries its reason into the upload response (`parser_note`) and the reviewer UI. Silent quality downgrades are bugs.
- **Admin/reviewer UX:** progressive disclosure (queue hidden until runs exist), new uploads auto-open for review, long operations show a busy state with honest text — no fake progress percentages for server-side work.
- **Seed data is fictional and labeled "(Demo)"** until real policies are hand-entered from brochures. Never fabricate real insurer policy details.
- **UX:** dual intake — free-text (LLM extraction) and catalog-sourced category chips with live policy counts. Choice questions render as tap chips, numeric questions as numeric inputs; free typing always remains available. The UI never advertises a category the catalog can't serve.
- **No-match is a valid outcome** — presented honestly, never a forced fit.

### Architecture & stack
- **Monorepo** (single repo, uv workspace + npm PWA); split only on a concrete trigger.
- **Scaling posture lives in `docs/06-scaling.md`** — poured slabs (stateless-over-Postgres, shared agent DB pool `agent/db.py`, catalog TTL cache in `agent/mcp_client.py`, queue-scaled ingestion) and the trigger table for each next step (replicas, distributed limiter, pgbouncer, object storage). Don't build past a trigger before it fires; when adding agent DB access, go through `db.connection()` (pooled, dict rows).
- **Stack:** Postgres + pgvector, LangGraph, FastAPI, React/Vite PWA, MCP boundary between agent and catalog.
- **Python floor: >= 3.14** (owner decision; Docker/CI run 3.14).
- **Embeddings: voyage-3.5 @ 1024 dims** (`vector(1024)`); optional — search falls back to SQL ranking without a key.
- **PDF parsing: docling primary, pypdf fallback** (owner decision). Docling's table-structure markdown is worth its heavy model dependencies for brochure tables; `DOCLING_ENABLED=false` forces the light path; parser used is recorded in `parse_status`.
- **LLM access is provider-agnostic** via `init_chat_model` env strings; LangSmith for tracing.
- **Multi-LLM verifier panel:** explanations only; 2+ judges, unanimous vote, cross-provider; failed reasons dropped silently (never drops a policy). **Batched:** one call per judge per policy (facts sent once, all claims numbered, one verdict each; misaligned/failed responses reject all claims — fail closed).
- **Token economy: explanation cache** (`app.explanation_cache`, `EXPLANATION_CACHE=auto`). Writer + judge panel run once per **outcome bucket** (same profile answers × same policy versions, content-hashed with models + prompts); later users in the bucket get the verified result with zero LLM calls. Self-invalidating (re-version/model/prompt changes the hash); errors read as a miss (never blocks a chat); rows unused past `EXPLANATION_CACHE_TTL_DAYS` purged by the retention task. **Deterministic-parse-first extraction:** a freeform message that is only the direct answer to the pending question (exact chip option, bare number, short line pick) skips the extractor LLM — richer messages still extract. **Judge panel batching:** one call per judge per policy (see verifier bullet) — with system-first prompt structure, OpenAI's automatic prompt caching applies to any ≥1024-token static prefix for free. **Degradation ladder** (`LLM_ECONOMY`, `agent/economy.py`): `full` → `lean` (drop panel) → `deterministic` (zero LLM — template explanations from verified fields via `deterministic_reasons`, deterministic parsing only); every rung stays honest and usable, and the mode is part of the explanation-cache key. **Spend ledger** (`app.llm_usage`, `agent/usage.py`): every LLM call metered by (day, model, role); cache hits recorded as zero-token rows; `GET /ops/usage` on the agent; `DAILY_TOKEN_BUDGET` warns once per day when crossed (alarm only, blocks nothing). New agent LLM call sites must attach `usage.tracker()` callbacks and `usage.record(role, ...)`.
- **Dynamic elicitation over static forms** — the catalog is fetched first and questions derive from candidate disagreement (see Architecture decisions above).

### Security & retention
- **Ingestion data surface is token-gated** (`ADMIN_TOKEN`, constant-time compare, bearer or `?token=`); `/health` and the data-free `/admin` shell stay open. Empty token = open = local dev only. New ingestion endpoints must take the `Protected` dependency. **Exception: the public brochure endpoints** (`GET /policies/{slug}/brochure` cover image, `GET /policies/{slug}/document`) are intentionally un-gated so end users can see brochures in results — but they serve a file **only** when the policy is published AND its source doc_type is `brochure`/`product_summary` (`PUBLIC_DOC_TYPES`); a `policy_contract` (possible PII) or unpublished/unknown slug 404s. Any new public file endpoint must apply the same eligibility gate.
- **/chat is rate-limited at the API gateway** (`RATE_LIMIT_CHAT`, default 30 requests/60s per client IP via first `X-Forwarded-For` hop; `off` disables) — it's the only endpoint that can spend LLM tokens. In-memory per-process by design; a distributed limiter is a scale trigger. Over-limit returns 429 with a human message the PWA surfaces.
- **Conversation retention:** `app.sessions` tracks last-seen per thread; an hourly agent task purges checkpoint rows idle past `SESSION_TTL_DAYS` (default 30) — DPA minimization, not a conversation timeout. The same task purges explanation-cache rows unused past `EXPLANATION_CACHE_TTL_DAYS`. Retention failures log and retry; they never take the service down.

### Process
- **Documentation, diagram, implementation, and tests move together.** Any change to the agent graph or a flow must be reflected in the same commit in `docs/03-agent-design.md`, `docs/agent-graph.drawio`, and the tests. No inconsistencies between what's documented, drawn, implemented, and tested.
- **Tests must be functional and cross-layer**, not trivial (SSE conversation tests, MCP-protocol tests, proxy tests, real-seed integration). Trivial import/health-only tests are unwelcome except as smoke tests for empty skeleton services.
- **Prompts and user-facing copy live in `agent/prompts.py`** — never inline in logic modules.
- **Architecture diagrams** live in `docs/*.drawio` (`agent-graph.drawio` for the LangGraph agent, `ingestion-pipeline.drawio` for the ingestion flow) and must be kept in sync with implementation changes; layout uses clear lanes with no line crossings or label overlaps. New flows get a diagram — everything is documented.
- **Git:** work is committed locally by the assistant; the owner pushes from their machine (`git push`). After dependency changes, the owner runs `uv lock` before pushing (CI uses `--locked`).
- **Dependency currency is automated:** a weekly GitHub Actions job (`dependency-currency.yml`) runs `uv lock --upgrade` and `npm outdated`, opening/updating a "dependencies"-labeled issue when anything falls behind latest stable and closing it when current.
- **Docker:** in-cluster MCP calls require the hostname allowlisted via `MCP_ALLOWED_HOSTS` (421 otherwise). Rebuild images before re-seeding — `docker compose run` uses the built image, not the working tree.
