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

**Upload.** Authenticated portal (`ADMIN_TOKEN` gates the whole data surface — see security notes). The reviewer just drops a file — **nothing is declared up front**: the AI classifies the document, detects the **insurer and product line from it**, and the reviewer confirms. Unknown insurers are created automatically on publish (how new insurers enter the catalog). Store original file with SHA-256 hash to dedupe; **re-uploading the same file is allowed** and reuses the stored document while creating a fresh extraction run — that's the redo workflow after a poor parse or extraction.

**Intake gate.** Before extraction, one pass with the large `LLM_MODEL` (`INTAKE_GATE`, on when an LLM key is present): it (1) **rejects non-insurance uploads outright** — a resume/invoice/random PDF finalizes as `rejected_invalid` with a reason the UI shows, nothing is extracted — and (2) **redacts PII** (policyholder/insured names, addresses, contacts, birth dates, government/policy/certificate numbers, signatures) from the document text, keeping product facts (insurer, plan, premiums, coverage). Extraction and everything stored downstream see only the redacted text, so PII never reaches the published catalog. The gate fails **open** (accept, unredacted) on a transient LLM error — the mandatory human review is the backstop. The original file stays on disk for the token-gated reviewer to verify against; only the *derived* text is redacted.

**Parse.** For PDFs the large vision model **triages** first (`VISION_TRIAGE`, on when an LLM key is present): it looks at the rendered pages (via `pypdfium2`) and either **transcribes an image-heavy/scanned document to Markdown itself** (recorded `parsed:llm-vision`) or **routes to `docling`** — pages a layout parser would mangle go to the LLM, clean digital text/tables stay on the cheaper, more precise docling path. Visual triage can't see whether a PDF actually has a text layer, so there's a safety net: if docling comes back with only image placeholders (a designed/image-heavy brochure with no text layer), the worker recovers by having vision transcribe the pages (`parsed:llm-vision`) rather than passing empty text downstream. `docling` (layout-aware; premium tables come out as structured markdown with rows/columns/multi-level headers intact) has `pypdf` as a lightweight fallback when docling is unavailable, disabled (`DOCLING_ENABLED=false`), or fails. **No step is silent**: the route/parser used and any reason are recorded in `source_documents.parse_status` (`parsed:llm-vision` / `parsed:docling` / `parsed:pypdf …`) and shown in the reviewer UI; vision failures degrade to docling so an upload is never lost. Docling itself runs with **OCR disabled** — the vision route covers scanned/image-heavy PDFs now. Its layout + table models are **baked into the ingestion image** at build (parsing works offline; OpenCV needs `libgl1`/`libglib2.0-0`, baked in via `APT_PACKAGES`). Vision uses the frontier `LLM_MODEL`; extraction uses the small `LLM_MODEL_SMALL`. Everything runs in the worker (see Upload), so slow parsing/vision never risks a request timeout.

**LLM extraction.** Structured-output call producing a `PolicyDraft` (the `PolicyVersion` schema plus `name`, `product_line`, and the document-detected `insurer_name`), model tier = small extractor, prompt forbids guessing (null over plausible values). The structured-output schema is derived from `PolicyDraft` but strips server-managed fields (`id`, `policy_id`, `version`, `verified_at`) so the model can never mistake a brochure reference number for a database id, and rewrites the discriminated `coverage` union's `oneOf` to `anyOf` (OpenAI structured output rejects `oneOf`). Small extractors sometimes misfile top-level facts (summary, premiums, riders, extras) *inside* `coverage`; because the coverage models don't define those keys Pydantic would drop them and a required field like `summary` would silently vanish, so a deterministic pre-validation step **hoists** any such field back to the top level when it isn't already set there. A run is enqueued as `queued`; the worker claims it (`processing`), then finalizes it to `pending_review` (draft ready), `extraction_skipped` (no LLM key — raw text stored for manual drafting), `extraction_failed` (extractor/provider error captured), `failed` (parsing itself failed), or `rejected_invalid` (the intake gate judged it not an insurance document). A **partial** draft (e.g. the insurer name wasn't stated in the document) is kept as `pending_review` for the reviewer to complete — only genuine call/provider errors become `extraction_failed`. *Future: per-field `source_page` + `confidence` provenance to flag low-confidence fields for the reviewer.*

**Validation.** Pydantic schema checks on approval, including the coverage-matches-product-line invariant; `insurer_name` is required and null-ish placeholders (`null`, `none`, `n/a`, `unknown`, empty) are rejected — publish get-or-creates the insurer, so a garbage name can't be allowed to seed the catalog.

**Auto-correction on approval failure.** Extraction is non-deterministic, so a draft that fails validation on approve often succeeds on a fresh run — historically the reviewer had to re-upload. Instead, on a validation failure the **frontier `LLM_MODEL` re-reads the document pages visually** with the exact error(s) and returns a corrected draft (e.g. a descriptive phrase like `110% of the single premium` wrongly placed in a numeric face-amount field is moved out and the number set to null), which goes back to `pending_review` for the human to approve again. Capped at **3 passes** (`correction_attempts`); after that, or when no LLM key / document is available, the error is surfaced for a manual fix. The pass runs synchronously in the approve call (~10–30s, with a busy state) using the same `policy_draft_schema` as extraction. Fails safe: any error in the pass just surfaces the original validation error. Because every PDF prints values differently, the draft normalizes reviewer/extractor input before validation — dates in `DD-Mon-YYYY` form (e.g. `06-Apr-2025`) and money with currency noise or thousands separators (`PHP 3,000,000`, `₱2.5M`, `P3,000,000.00`) are coerced deterministically; genuinely unparseable values are left untouched so validation still errors rather than silently guessing.

**Human review.** The reviewer UI (`:8003/admin`) opens each new upload automatically: draft editor with the source document one click away, approve/reject. Progressive disclosure — the queue appears only when runs exist. Nothing reaches the live catalog without approval (protects against hallucinated coverage).

**Publish.** Transactional: get-or-create the insurer from the confirmed `insurer_name`, insert the policy (published) + `policy_version` (version 1), generate the embedding (name + summary) into pgvector when a key is set. **Re-approving an existing policy (same slug) re-versions it instead of erroring** — the policy row is refreshed (insurer/line may have been corrected), the current `policy_version` is marked `superseded_at = now()`, and a new version (v2, v3…) becomes current with its own embedding. Readers select only the current version (`superseded_at IS NULL`), so search never returns duplicates, and any recommendation that snapshotted an older `policy_version_id` still resolves. This is the redo path after a re-upload with a better parse/extraction.

### Pipeline API (ingestion service, :8003) — implemented

| Endpoint | Purpose |
|---|---|
| `POST /documents` | Upload (PDF/txt/md); `insurer_slug` optional (insurer is detected from the document), `doc_type`. Stores the file and **enqueues a `queued` run, returning `202` immediately**; a separate **worker process** (Postgres-backed queue) parses (vision triage → self-transcribe or docling, with thin-text vision recovery and pypdf fallback) → LLM-extracts (incl. `insurer_name`) so slow parsing never trips a proxy timeout — the reviewer UI polls `GET /reviews/{id}` until the run leaves the queue. Re-uploading the same file (hash match) reuses the stored document and creates a **fresh extraction run** — that's how a reviewer redoes a bad parse. Synchronous errors: `404` explicitly-given unknown insurer, `400` unsupported type / empty file; a scanned/unreadable PDF becomes a `failed` run (surfaced in the queue), not a `400`. Without an LLM key the run finalizes `extraction_skipped` with raw text for manual drafting. |
| `GET /reviews?status=` | Review queue by status (`queued`, `processing`, `pending_review`, `extraction_skipped`, `extraction_failed`, `failed`, `rejected_invalid`) |
| `GET /reviews/{id}` | One run with extracted output |
| `POST /reviews/{id}/approve` | Body = reviewer-corrected `PolicyDraft` (raw JSON, validated in-handler) → publishes policy + version (+ embedding if key), marks run approved. On validation failure the frontier model re-reads the document and returns a corrected draft (`{"status":"corrected","attempt":n,"draft":…}`, HTTP 200) for another approval — up to 3× (`correction_attempts`), then a `422` for a manual fix |
| `POST /reviews/{id}/reject` | Marks run rejected |
| `GET /insurers` | Insurer list for the upload form |
| `GET /documents/{id}/file` | Serves the original uploaded document (side-by-side review) |
| `GET /policies/{slug}/brochure` | **Public** (no token) — cover-page PNG of a published policy's brochure, rendered once from the stored PDF (`pypdfium2`) and cached. Served **only** when the source `doc_type` is `brochure`/`product_summary`; a contract or unpublished slug 404s. |
| `GET /policies/{slug}/document` | **Public** (no token) — the original brochure document (inline), same eligibility gate. Powers the clickable brochure thumbnail in results. |
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
