"""Ingestion service: upload -> parse -> extract -> human review -> publish.

Nothing reaches the live catalog without an explicit approval
(POST /reviews/{id}/approve) — the human review step is mandatory.
"""

import hashlib
import hmac
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ingestion import extraction, parsing, repository
from ingestion.prompts import PolicyDraft


def require_admin_token(request: Request) -> None:
    """Shared-token auth for the whole data surface (ADMIN_TOKEN env).

    Accepted as `Authorization: Bearer <token>` or `?token=` (the latter so
    the reviewer can open source documents in a new tab). When ADMIN_TOKEN is
    unset the service stays open — local development only; never deploy that.
    """
    expected = os.environ.get("ADMIN_TOKEN", "")
    if not expected:
        return
    header = request.headers.get("authorization", "")
    presented = header.removeprefix("Bearer ").strip() or request.query_params.get(
        "token", ""
    )
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="missing or invalid admin token")


Protected = Annotated[None, Depends(require_admin_token)]

app = FastAPI(title="Policy Ingestion Service")


def docs_dir() -> Path:
    path = Path(os.environ.get("DOCS_DIR", "/data/uploads"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@app.post("/documents", status_code=201)
async def upload_document(
    _auth: Protected,
    file: UploadFile,
    insurer_slug: str = Form(default=""),  # optional — detected from the document
    doc_type: str = Form(default="brochure"),
    uploaded_by: str = Form(default="admin"),
) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        document_text, parser, parser_note = parsing.extract_text(file.filename or "", data)
    except parsing.UnsupportedDocument as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    file_hash = hashlib.sha256(data).hexdigest()
    file_ref = str(docs_dir() / f"{file_hash[:16]}-{Path(file.filename or 'doc').name}")
    Path(file_ref).write_bytes(data)

    try:
        document_id, created = repository.get_or_create_source_document(
            insurer_slug or None, file_hash, file_ref, doc_type, uploaded_by,
            parse_status=f"parsed:{parser}",
        )
    except repository.InsurerNotFound as error:
        raise HTTPException(
            status_code=404, detail=f"unknown insurer slug '{error}'"
        ) from error

    output, status, model = await extraction.extract_draft(document_text)
    run_id = repository.create_extraction_run(document_id, model, output, status)

    return {
        "document_id": document_id,
        "document_reused": not created,  # same file seen before -> fresh run anyway
        "extraction_run_id": run_id,
        "status": status,
        "parser": parser,
        "parser_note": parser_note,  # why a docling fallback happened, if it did
        "characters_parsed": len(document_text),
    }


@app.get("/reviews")
def pending_reviews(_auth: Protected, status: str = "pending_review") -> list[dict]:
    return repository.list_reviews(status)


@app.get("/reviews/{run_id}")
def review_detail(run_id: str, _auth: Protected = None) -> dict:
    review = repository.get_review(run_id)
    if review is None:
        raise HTTPException(status_code=404, detail="review not found")
    return review


class ApprovalRequest(BaseModel):
    draft: PolicyDraft  # reviewer-corrected draft (validated against the schema)
    reviewed_by: str = Field(default="reviewer", max_length=120)


@app.post("/reviews/{run_id}/approve")
def approve(run_id: str, request: ApprovalRequest, _auth: Protected = None) -> dict:
    try:
        published = repository.publish(
            run_id, request.draft.model_dump(mode="json"), request.reviewed_by
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail="review not found") from error
    except repository.SlugConflict as error:
        raise HTTPException(
            status_code=409, detail=f"policy slug already exists: {error}"
        ) from error
    return {"published": published}


class RejectionRequest(BaseModel):
    reviewed_by: str = Field(default="reviewer", max_length=120)


@app.post("/reviews/{run_id}/reject")
def reject(run_id: str, request: RejectionRequest, _auth: Protected = None) -> dict:
    if repository.get_review(run_id) is None:
        raise HTTPException(status_code=404, detail="review not found")
    repository.reject(run_id, request.reviewed_by)
    return {"status": "rejected"}


@app.get("/insurers")
def insurers(_auth: Protected = None) -> list[dict]:
    return repository.list_insurers()


@app.get("/documents/{document_id}/file")
def document_file(document_id: str, _auth: Protected = None) -> FileResponse:
    document = repository.get_document(document_id)
    if document is None or not Path(document["file_ref"]).exists():
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(document["file_ref"])
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "text/plain"
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/admin")
def admin() -> HTMLResponse:
    """Reviewer UI: upload documents, inspect drafts, approve/reject.
    Single static file, no build step — served by this service."""
    return HTMLResponse((Path(__file__).parent / "admin.html").read_text())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ingestion"}
