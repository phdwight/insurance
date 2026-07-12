# ingestion

Policy document ingestion: upload → parse (docling for layout/tables, pypdf
fallback) → LLM extraction (small model, never guesses) → **mandatory human
review** → publish to the catalog (+ embedding when `VOYAGE_API_KEY` is set).

Docling loads local models on first use (heavy image, seconds per document —
fine for this low-volume admin path). Set `DOCLING_ENABLED=false` to force
the lightweight pypdf path.

Endpoints: `POST /documents`, `GET /reviews`, `GET /reviews/{id}`,
`POST /reviews/{id}/approve`, `POST /reviews/{id}/reject`.
See [`docs/02-ingestion-mcp.md`](../docs/02-ingestion-mcp.md).

**Reviewer UI: http://localhost:8003/admin** — upload a brochure (insurer is
detected from the document; new insurers are created on publish), the draft
opens automatically for review, edit, approve to publish (or reject). The
queue only appears once runs exist. Re-uploading the same file creates a
fresh extraction run (the redo workflow); a docling→pypdf fallback always
shows its reason. The same flow is available over the API:

```bash
curl -F "file=@brochure.pdf" -F "insurer_slug=byahero-demo" localhost:8003/documents
curl localhost:8003/reviews
```

Auth: set `ADMIN_TOKEN` and every data endpoint requires it (the UI prompts
once per browser session; document links carry `?token=`). Empty token =
open, for local development only.
