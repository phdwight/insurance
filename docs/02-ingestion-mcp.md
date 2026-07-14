# Policy Ingestion & MCP Server

## 1. Ingestion pipeline

Diagram: [`ingestion-pipeline.drawio`](ingestion-pipeline.drawio) (kept in sync with the implementation).

### Flow

```
Upload (PDF/DOCX + metadata)
   → Parse (text/tables extraction)
   → LLM Extraction (map to policy schema, with citations to source pages)
   → Validation (schema + rule checks)
   → Human Review Queue (approve / edit / reject)
   → Publish (versioned row in catalog + embeddings)
```

### Stages

**Upload.** Authenticated portal (auth itself is a Phase 5 item — see security notes). Only the document type is declared up front — the **insurer and product line are detected from the document** by extraction and confirmed by the reviewer (pre-selecting an insurer is optional; unknown insurers are created automatically on publish, which is how new insurers enter the catalog). Store original file with SHA-256 hash to dedupe; **re-uploading the same file is allowed** and reuses the stored document while creating a fresh extraction run — that's the redo workflow after a poor parse or extraction.

**Parse.** `docling` (layout-aware; premium tables come out as structured markdown with rows/columns/multi-level headers intact — much more reliable input for LLM extraction) with `pypdf` as a lightweight fallback when docling is unavailable, disabled (`DOCLING_ENABLED=false`), or fails on a document. **A fallback is never silent**: the parser used and any fallback reason are recorded in `source_documents.parse_status` (`parsed:docling` / `parsed:pypdf …`) and shown in the reviewer UI. Docling runs with **OCR disabled** — brochures are digital PDFs with real text, so scanned PDFs stay out of scope (rejected as a `failed` run). Its layout + table models are **baked into the ingestion image** at build so the first upload never downloads mid-request and parsing works offline; OpenCV needs `libgl1`/`libglib2.0-0`, also baked in via `APT_PACKAGES`. Because parse + extraction run in a separate worker process (see Upload), turning OCR back on later won't risk request timeouts.

**LLM extraction.** Structured-output call producing a `PolicyDraft` (the `PolicyVersion` schema plus `name`, `product_line`, and the document-detected `insurer_name`), model tier = small extractor, prompt forbids guessing (null over plausible values). The structured-output schema is derived from `PolicyDraft` but strips server-managed fields (`id`, `policy_id`, `version`, `verified_at`) so the model can never mistake a brochure reference number for a database id, and rewrites the discriminated `coverage` union's `oneOf` to `anyOf` (OpenAI structured output rejects `oneOf`). A run is enqueued as `queued`; the worker claims it (`processing`), then finalizes it to `pending_review` (draft ready), `extraction_skipped` (no LLM key — raw text stored for manual drafting), `extraction_failed` (extractor/provider error captured), or `failed` (parsing itself failed — e.g. an unreadable/scanned PDF). A **partial** draft (e.g. the insurer name wasn't stated in the document) is kept as `pending_review` for the reviewer to complete — only genuine call/provider errors become `extraction_failed`. *Future: per-field `source_page` + `confidence` provenance to flag low-confidence fields for the reviewer.*

**Validation.** Pydantic schema checks on approval, including the coverage-matches-product-line invariant; `insurer_name` is required. Because every PDF prints values differently, the draft normalizes reviewer/extractor input before validation — dates in `DD-Mon-YYYY` form (e.g. `06-Apr-2025`) and money with currency noise or thousands separators (`PHP 3,000,000`, `₱2.5M`, `P3,000,000.00`) are coerced deterministically; genuinely unparseable values are left untouched so validation still errors rather than silently guessing.

**Human review.** The reviewer UI (`:8003/admin`) opens each new upload automatically: draft editor with the source document one click away, approve/reject. Progressive disclosure — the queue appears only when runs exist. Nothing reaches the live catalog without approval (protects against hallucinated coverage).

**Publish.** Transactional: get-or-create the insurer from the confirmed `insurer_name`, insert the policy (published) + `policy_version`, generate the embedding (name + summary) into pgvector when a key is set. Duplicate policy slugs are rejected, so a redo can't double-publish. *Future: re-versioning an existing policy (new `policy_version`, supersede the old) — today each publish is version 1 of a new policy.*

### Pipeline API (ingestion service, :8003) — implemented

| Endpoint | Purpose |
|---|---|
| `POST /documents` | Upload (PDF/txt/md); `insurer_slug` optional (insurer is detected from the document), `doc_type`. Stores the file and **enqueues a `queued` run, returning `202` immediately**; a separate **worker process** (Postgres-backed queue) parses (docling → pypdf fallback) → LLM-extracts (incl. `insurer_name`) so slow parsing never trips a proxy timeout — the reviewer UI polls `GET /reviews/{id}` until the run leaves the queue. Re-uploading the same file (hash match) reuses the stored document and creates a **fresh extraction run** — that's how a reviewer redoes a bad parse. Synchronous errors: `404` explicitly-given unknown insurer, `400` unsupported type / empty file; a scanned/unreadable PDF becomes a `failed` run (surfaced in the queue), not a `400`. Without an LLM key the run finalizes `extraction_skipped` with raw text for manual drafting. |
| `GET /reviews?status=` | Review queue by status (`queued`, `processing`, `pending_review`, `extraction_skipped`, `extraction_failed`, `failed`) |
| `GET /reviews/{id}` | One run with extracted output |
| `POST /reviews/{id}/approve` | Body = reviewer-corrected `PolicyDraft` (schema-validated, coverage must match product line) → publishes policy + version (+ embedding if key), marks run approved |
| `POST /reviews/{id}/reject` | Marks run rejected |
| `GET /insurers` | Insurer list for the upload form |
| `GET /documents/{id}/file` | Serves the original uploaded document (side-by-side review) |
| `GET /admin` | **Reviewer UI** — upload, queue tabs by status, draft editor (schema-validated on approve), approve/reject. Single static page, no build step. |

**Auth:** every data endpoint requires the `ADMIN_TOKEN` (bearer header or `?token=` for new-tab document links; constant-time compare). Only `/health` and the `/admin` page shell (which carries no data) stay open. An empty `ADMIN_TOKEN` leaves the service open — local development only.

### Freshness

Policies carry `effective_date` and `verified_at`. A scheduled job flags entries not re-verified in N months; the UI shows "as of" dates to users.

## 2. Data model (Postgres, `catalog` schema)

```sql
insurers            (id, name, slug, website, contact_info, ic_license_ref)
product_lines       (id, code, name)           -- life, health, travel, pet, motor…
policies            (id, insurer_id, product_line_id, name, slug, status)
policy_versions     (id, policy_id, version, effective_date, verified_at,
                     summary, currency, premium_min, premium_max,
                     premium_frequency, eligibility jsonb, coverage jsonb,
                     exclusions jsonb, riders jsonb, extras jsonb,
                     source_document_id, published_at, superseded_at)
policy_embeddings   (policy_version_id, embedding vector(1536), text_used)
source_documents    (id, insurer_id, file_hash, file_ref, doc_type,
                     uploaded_by, uploaded_at, parse_status)
extraction_runs     (id, source_document_id, model, output jsonb,
                     field_confidences jsonb, status, reviewed_by, reviewed_at)
```

Notes:
- `coverage`, `eligibility`, `exclusions` are JSONB with **per-line JSON Schemas** (a travel policy's coverage shape ≠ a life policy's). Common queryable fields (premium range, age band) are promoted to typed columns.
- Versioning is append-only; recommendations snapshot the `policy_version_id` they used.

### Per-line coverage schema sketches

- **Life:** face amount range, term/whole, maturity benefits, ADB riders, contestability
- **Health:** annual limit, room & board, inpatient/outpatient, pre-existing condition rules, HMO vs indemnity
- **Travel:** trip medical limit, trip cancellation, baggage, COVID coverage, destinations covered, Schengen-compliant flag
- **Pet:** species/breed/age eligibility, vet fee limit, wellness add-ons, waiting periods

## 3. MCP Server

Read-only MCP server (Python SDK, streamable HTTP transport) over the published catalog.

### Tools

| Tool | Input | Output |
|---|---|---|
| `list_product_lines` | — | lines with counts |
| `list_insurers` | optional line filter | insurers |
| `search_policies` | product_line, structured filters (budget, age, dependents, destination…), free-text `needs_description` | ranked policy summaries (hybrid SQL + vector search), with match scores |
| `get_policy` | policy_id or slug | full current version incl. coverage, exclusions, source doc link, verified_at |
| `compare_policies` | 2–4 policy_ids | aligned attribute comparison matrix |

Design rules:
- Tool descriptions written for LLM consumption: explicit parameter semantics, units (PHP, years), enum values.
- `search_policies` does the heavy lifting server-side (filter + embed + rerank) so the agent doesn't page through raw rows.
- Every response includes `verified_at` and `source_url` so the agent can cite freshness.
- Stateless; auth via bearer token from the agent service.
- Plain REST mirrors for the PWA: `GET /product-lines` (category chips) and `GET /compare?slugs=a,b` (side-by-side comparison view).

### Future (post-MVP)
- Write-path MCP tools for agent-assisted ingestion ("here's a brochure, extract it")
- Webhook/subscription for catalog changes
- Public/partner access tiers to the MCP server as a standalone product
