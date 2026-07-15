"""Functional tests of the ingestion pipeline over HTTP: upload -> parse ->
extract -> review -> publish, with persistence and LLM faked at module seams.
The parser runs for real (plain text and a minimal in-memory PDF)."""

import asyncio

import ingestion.main as ingestion_main
from fastapi.testclient import TestClient

from ingestion import parsing, repository, worker

client = TestClient(ingestion_main.app)


def drain_worker() -> None:
    """Run the queue worker until the queue is empty — the test stand-in for the
    separate worker process (upload only enqueues now)."""

    async def _drain() -> None:
        while await worker.process_one():
            pass

    asyncio.run(_drain())

BROCHURE = (
    "Demo Worldwide Voyager. Single-trip travel insurance. "
    "Emergency medical PHP 3,000,000 including COVID-19. Premium from PHP 900. "
    "Trips up to 45 days. Ages 0-70."
)

VALID_DRAFT = {
    "name": "Demo Worldwide Voyager",
    "insurer_name": "Byahero Travel Insurance Co.",
    "product_line": "travel",
    "summary": "Single-trip travel insurance with PHP 3M medical.",
    "premium_min": "900",
    "premium_frequency": "single",
    "eligibility": {"age_min": 0, "age_max": 70},
    "coverage": {
        "line": "travel",
        "medical_limit": "3000000",
        "covid_covered": True,
        "max_trip_days": 45,
    },
    "exclusions": ["Extreme sports"],
}


def make_minimal_pdf(content: str) -> bytes:
    """Hand-assembled single-page PDF with real extractable text."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        None,  # content stream, built below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 72 720 Td ({content}) Tj ET".encode()
    objects[3] = (
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF"
    ).encode()
    return bytes(out)


class FakeRepo:
    """In-memory stand-in for the catalog write path."""

    def __init__(self):
        self.documents: dict[str, str] = {}  # hash -> id
        self.runs: dict[str, dict] = {}
        self.published: list[dict] = []

    def install(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("DOCS_DIR", str(tmp_path))
        # Force the pypdf path so pipeline tests are deterministic and fast
        # whether or not docling is installed; docling has dedicated tests.
        monkeypatch.setenv("DOCLING_ENABLED", "false")
        # LLM-gated steps are off by default so tests are deterministic and make
        # no real calls; the vision/intake tests opt in and mock the model.
        monkeypatch.setenv("VISION_TRIAGE", "false")
        monkeypatch.setenv("INTAKE_GATE", "false")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(repository, "get_or_create_source_document", self.create_document)
        monkeypatch.setattr(repository, "create_extraction_run", self.create_run)
        monkeypatch.setattr(repository, "finalize_extraction_run", self.finalize_run)
        monkeypatch.setattr(repository, "update_parse_status", self.update_parse)
        monkeypatch.setattr(repository, "update_doc_type", self.update_doc_type)
        monkeypatch.setattr(repository, "claim_next_run", self.claim_next_run)
        monkeypatch.setattr(repository, "reclaim_stale_runs", self.reclaim_stale_runs)
        monkeypatch.setattr(repository, "get_review", self.get_review)
        monkeypatch.setattr(repository, "list_reviews", self.list_reviews)
        monkeypatch.setattr(repository, "publish", self.publish)
        monkeypatch.setattr(repository, "reject", self.reject)
        monkeypatch.setattr(repository, "list_insurers", self.list_insurers)
        monkeypatch.setattr(repository, "get_document", self.get_document)

    def create_document(
        self, insurer_slug, file_hash, file_ref, doc_type, uploaded_by, parse_status="parsed"
    ):
        if insurer_slug is not None and insurer_slug != "byahero-demo":
            raise repository.InsurerNotFound(insurer_slug)
        self.parse_statuses = getattr(self, "parse_statuses", {})
        self.file_refs = getattr(self, "file_refs", {})
        if file_hash in self.documents:  # re-upload reuses the document
            doc_id = self.documents[file_hash]
            self.parse_statuses[doc_id] = parse_status
            return doc_id, False
        doc_id = f"doc-{len(self.documents) + 1}"
        self.documents[file_hash] = doc_id
        self.parse_statuses[doc_id] = parse_status
        self.file_refs[doc_id] = file_ref
        return doc_id, True

    def list_insurers(self):
        return [{"name": "Byahero (Demo)", "slug": "byahero-demo"}]

    def get_document(self, document_id):
        ref = getattr(self, "file_refs", {}).get(document_id)
        return {"id": document_id, "file_ref": ref, "doc_type": "brochure"} if ref else None

    def create_run(self, source_document_id, model, output, status):
        run_id = f"run-{len(self.runs) + 1}"
        self.runs[run_id] = {
            "id": run_id,
            "source_document_id": source_document_id,
            "model": model,
            "output": output,
            "status": status,
            "insurer_slug": "byahero-demo",
            "insurer_id": "ins-1",
        }
        return run_id

    def finalize_run(self, run_id, model, output, status):
        run = self.runs[run_id]
        run.update(model=model, output=output, status=status)

    def update_parse(self, document_id, parse_status):
        self.parse_statuses = getattr(self, "parse_statuses", {})
        self.parse_statuses[document_id] = parse_status

    def update_doc_type(self, document_id, doc_type):
        self.doc_types = getattr(self, "doc_types", {})
        self.doc_types[document_id] = doc_type

    def claim_next_run(self):
        for run in self.runs.values():
            if run["status"] == "queued":
                run["status"] = "processing"
                return {
                    "id": run["id"],
                    "source_document_id": run["source_document_id"],
                    "file_ref": getattr(self, "file_refs", {}).get(run["source_document_id"]),
                }
        return None

    def reclaim_stale_runs(self, older_than_seconds):
        return 0

    def get_review(self, run_id):
        return self.runs.get(run_id)

    def list_reviews(self, status="pending_review"):
        return [run for run in self.runs.values() if run["status"] == status]

    def publish(self, run_id, draft, reviewed_by):
        if run_id not in self.runs:
            raise LookupError(run_id)
        slug = repository.slugify(draft["name"])
        self.runs[run_id]["status"] = "approved"
        self.published.append({"slug": slug, "draft": draft, "by": reviewed_by})
        return {"policy_id": "p-1", "version_id": "v-1", "slug": slug}

    def reject(self, run_id, reviewed_by):
        self.runs[run_id]["status"] = "rejected"


def upload(filename: str, payload: bytes, insurer: str = ""):
    """Default mirrors the UI: no insurer pre-selected, detected from the doc."""
    return client.post(
        "/documents",
        files={"file": (filename, payload)},
        data={"insurer_slug": insurer, "doc_type": "brochure"},
    )


def test_full_pipeline_upload_review_approve(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    # Upload only enqueues; the worker processes the queue.
    response = upload("voyager.txt", BROCHURE.encode())
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"  # terminal status is polled, not returned
    run_id = body["extraction_run_id"]
    assert repo.runs[run_id]["status"] == "queued"  # nothing runs it yet

    drain_worker()
    # no LLM key -> extraction skipped, raw text kept for the reviewer
    assert repo.runs[run_id]["status"] == "extraction_skipped"
    assert BROCHURE[:40] in repo.runs[run_id]["output"]["raw_text"]
    assert "parsed:text" in repo.parse_statuses[body["document_id"]]

    # Review queue shows it under its status
    assert client.get("/reviews", params={"status": "extraction_skipped"}).json()[0][
        "id"
    ] == run_id

    # Approve with the reviewer-entered draft -> published; the insurer comes
    # from the confirmed draft (created on publish if new), not the upload form
    response = client.post(f"/reviews/{run_id}/approve", json={"draft": VALID_DRAFT})
    assert response.status_code == 200
    assert response.json()["published"]["slug"] == "demo-worldwide-voyager"
    assert repo.runs[run_id]["status"] == "approved"
    assert repo.published[0]["draft"]["insurer_name"] == "Byahero Travel Insurance Co."
    assert repo.published[0]["draft"]["coverage"]["covid_covered"] is True


def test_draft_without_insurer_name_rejected(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)
    run_id = repo.create_run("doc-1", "m", {}, "pending_review")
    draft = {k: v for k, v in VALID_DRAFT.items() if k != "insurer_name"}
    # insurer_name required; with no LLM key/file, auto-correction is unavailable,
    # so the error is surfaced for a manual fix.
    response = client.post(f"/reviews/{run_id}/approve", json={"draft": draft})
    assert response.status_code == 422


def test_llm_extraction_feeds_pending_review(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    async def fake_extract(text):
        assert "PHP 3,000,000" in text  # parsed text reaches the extractor
        return dict(VALID_DRAFT), "pending_review", "anthropic:claude-haiku-4-5"

    monkeypatch.setattr(worker.extraction, "extract_draft", fake_extract)

    response = upload("voyager.pdf", make_minimal_pdf(BROCHURE))
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    drain_worker()
    run = repo.runs[response.json()["extraction_run_id"]]
    assert run["status"] == "pending_review"  # finalized by the worker
    assert run["output"]["name"] == "Demo Worldwide Voyager"


def test_upload_guards(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    assert upload("x.docx", b"whatever").status_code == 400  # unsupported type
    assert upload("x.txt", b"").status_code == 400  # empty file
    # no insurer given is fine (detected from document)...
    assert upload("no-insurer.txt", b"some brochure text").status_code == 202
    # ...but an explicitly given unknown insurer is still an error (validated
    # synchronously, before the run is scheduled)
    assert upload("x.txt", b"text", insurer="ghost").status_code == 404


def test_reupload_same_document_creates_fresh_run(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    first = upload("dup.txt", BROCHURE.encode()).json()
    second = upload("dup.txt", BROCHURE.encode()).json()

    # same stored document, but a brand-new extraction run each time —
    # re-uploading is how a reviewer redoes a bad parse/extraction
    assert second["document_id"] == first["document_id"]
    assert second["document_reused"] is True
    assert first["document_reused"] is False
    assert second["extraction_run_id"] != first["extraction_run_id"]


def test_approve_validates_draft_and_missing_run(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    # discriminated union rejects a draft whose coverage doesn't match the line
    run_id = repo.create_run("doc-1", "m", {}, "pending_review")
    bad = dict(VALID_DRAFT, coverage={"line": "life", "policy_type": "term"})
    response = client.post(f"/reviews/{run_id}/approve", json={"draft": bad})
    assert response.status_code == 422

    response = client.post("/reviews/run-missing/approve", json={"draft": VALID_DRAFT})
    assert response.status_code == 404

    assert client.post("/reviews/run-missing/reject", json={}).status_code == 404


def test_admin_ui_and_supporting_endpoints(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    # admin page serves the reviewer workflow markers
    page = client.get("/admin")
    assert page.status_code == 200
    for marker in ("Review queue", "Approve", "upload-form", "/reviews"):
        assert marker in page.text

    # insurer dropdown data
    assert client.get("/insurers").json()[0]["slug"] == "byahero-demo"

    # uploaded source document is downloadable for side-by-side review
    upload("voyager.txt", BROCHURE.encode())
    response = client.get("/documents/doc-1/file")
    assert response.status_code == 200
    assert BROCHURE[:30] in response.text
    assert client.get("/documents/ghost/file").status_code == 404


def test_pypdf_path_extracts_and_rejects_scanned(monkeypatch) -> None:
    monkeypatch.setenv("DOCLING_ENABLED", "false")  # deterministic light path
    text, parser, note = parsing.extract_text("brochure.pdf", make_minimal_pdf("PHP 500 premium"))
    assert "PHP 500 premium" in text
    assert parser == "pypdf"
    assert "disabled" in note  # fallback is never silent

    import pytest

    with pytest.raises(parsing.UnsupportedDocument):
        parsing.extract_text("empty.pdf", make_minimal_pdf(""))  # no text = scanned


def test_docling_failure_falls_back_with_visible_reason(monkeypatch) -> None:
    monkeypatch.delenv("DOCLING_ENABLED", raising=False)
    monkeypatch.setattr(
        parsing, "_docling_convert", lambda filename, data: (None, "docling failed: boom")
    )
    text, parser, note = parsing.extract_text("brochure.pdf", make_minimal_pdf("PHP 500"))
    assert parser == "pypdf"
    assert "PHP 500" in text
    assert "docling failed: boom" in note


def test_docling_preferred_for_pdfs_when_available(monkeypatch) -> None:
    markdown = "| Plan | Premium |\n|---|---|\n| Voyager | PHP 900 |"
    monkeypatch.setattr(parsing, "_docling_convert", lambda filename, data: (markdown, None))

    text, parser, note = parsing.extract_text("brochure.pdf", make_minimal_pdf("ignored"))
    assert parser == "docling"
    assert note is None
    assert "| Plan | Premium |" in text  # table structure preserved for the LLM

    # explicit kill switch forces the lightweight path
    monkeypatch.setenv("DOCLING_ENABLED", "false")
    _, parser, _ = parsing.extract_text("brochure.pdf", make_minimal_pdf("PHP 500"))
    assert parser == "pypdf"


def test_worker_claims_queue_and_records_parse_failure(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)

    # a PDF with no extractable text (scanned) — parse fails, and the worker
    # records it as a 'failed' run rather than losing it
    response = upload("scanned.pdf", make_minimal_pdf(""))
    assert response.status_code == 202
    run_id = response.json()["extraction_run_id"]
    assert repo.runs[run_id]["status"] == "queued"  # sits in the queue until a worker claims it

    drain_worker()
    run = repo.runs[run_id]
    assert run["status"] == "failed"
    assert "error" in run["output"]
    # the empty queue is a no-op for the worker
    assert asyncio.run(worker.process_one()) is False


def test_vision_self_transcribes_image_heavy_pdf(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("VISION_TRIAGE", "auto")  # opt in (install defaults it off)

    async def fake_triage(filename, data):
        # large model decides it can read the image-heavy doc and transcribes it
        return "# Voyager\n| Plan | Premium |\n|---|---|\n| A | PHP 900 |", "self", "scanned"

    async def fake_extract(text):
        assert "| Plan | Premium |" in text  # vision Markdown reached the extractor
        return dict(VALID_DRAFT), "pending_review", "anthropic:claude-sonnet-4-5"

    monkeypatch.setattr(worker.vision, "triage", fake_triage)
    monkeypatch.setattr(worker.extraction, "extract_draft", fake_extract)

    upload("scanned.pdf", make_minimal_pdf("ignored"))
    drain_worker()
    run = list(repo.runs.values())[-1]
    assert run["status"] == "pending_review"
    assert run["output"]["name"] == "Demo Worldwide Voyager"
    assert "parsed:llm-vision" in list(repo.parse_statuses.values())[-1]


def test_vision_routes_clean_pdf_to_docling(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)  # DOCLING_ENABLED=false -> pypdf path
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("VISION_TRIAGE", "auto")

    async def fake_triage(filename, data):
        return None, "docling", "clean digital text"  # hands off to the parser

    async def fake_extract(text):
        assert "PHP 500" in text  # parser text, not vision
        return dict(VALID_DRAFT), "pending_review", "model"

    monkeypatch.setattr(worker.vision, "triage", fake_triage)
    monkeypatch.setattr(worker.extraction, "extract_draft", fake_extract)

    brochure = ("BYAHERO Worldwide Voyager travel insurance. Emergency medical up to "
                "PHP 3,000,000 including COVID-19. Trip cancellation PHP 100,000. "
                "Premium from PHP 500. Ages 0-70. Trips up to 45 days.")
    upload("brochure.pdf", make_minimal_pdf(brochure))
    drain_worker()
    parse_status = list(repo.parse_statuses.values())[-1]
    assert "parsed:pypdf" in parse_status  # real text layer -> no vision recovery
    assert "vision → docling" in parse_status


def test_vision_recovers_thin_docling_text(monkeypatch, tmp_path) -> None:
    # An image-heavy PDF where docling yields only placeholders: vision must
    # transcribe it rather than the doc being wrongly rejected as empty.
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("VISION_TRIAGE", "auto")

    async def triage(filename, data):
        return None, "docling", "looks like a clean brochure"  # wrong guess

    async def transcribe(filename, data):
        return ("# Sun Acceler8\n20-year endowment insurance from Sun Life. Increasing "
                "life coverage up to 228% of the face amount. Guaranteed maturity "
                "benefit of 102%. Special bonus after 8 years. Limited pay period.")

    monkeypatch.setattr(worker.vision, "triage", triage)
    monkeypatch.setattr(worker.vision, "transcribe", transcribe)
    # docling returns image placeholders only (thin)
    monkeypatch.setattr(
        worker.parsing, "extract_text",
        lambda f, d: ("<!-- image -->\n<!-- image -->\n<!-- image -->", "docling", None),
    )

    async def fake_extract(text):
        assert "Sun Acceler8" in text  # vision-transcribed text reached the extractor
        return dict(VALID_DRAFT), "pending_review", "model"

    monkeypatch.setattr(worker.extraction, "extract_draft", fake_extract)

    upload("sun.pdf", make_minimal_pdf("ignored"))
    drain_worker()
    run = list(repo.runs.values())[-1]
    assert run["status"] == "pending_review"
    assert "parsed:llm-vision" in list(repo.parse_statuses.values())[-1]


def test_intake_rejects_non_insurance_document(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("INTAKE_GATE", "auto")  # opt in (install defaults it off)

    from ingestion.prompts import DocumentIntake

    async def fake_classify(text):
        return DocumentIntake(is_insurance=False, category="other", reason="looks like a resume")

    monkeypatch.setattr(worker.intake, "classify", fake_classify)

    upload("resume.txt", b"John Doe. Software engineer. 10 years experience.")
    drain_worker()
    run = list(repo.runs.values())[-1]
    assert run["status"] == "rejected_invalid"  # rejected outright, not extracted
    assert "resume" in run["output"]["reason"]


def test_intake_redacts_pii_before_extraction(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("INTAKE_GATE", "auto")

    from ingestion.prompts import DocumentIntake

    async def fake_classify(text):
        assert "John Doe" in text  # the gate sees the raw text
        return DocumentIntake(
            is_insurance=True,
            category="policy_contract",
            reason="a personal policy",
            redacted_text="Voyager Plan. Insured: [REDACTED]. Premium PHP 900.",
        )

    async def fake_extract(text):
        assert "[REDACTED]" in text and "John Doe" not in text  # extractor only sees redacted text
        return dict(VALID_DRAFT), "pending_review", "model"

    monkeypatch.setattr(worker.intake, "classify", fake_classify)
    monkeypatch.setattr(worker.extraction, "extract_draft", fake_extract)

    upload("policy.txt", b"Voyager Plan. Insured: John Doe. Premium PHP 900.")
    drain_worker()
    run = list(repo.runs.values())[-1]
    assert run["status"] == "pending_review"
    assert "PII redacted" in list(repo.parse_statuses.values())[-1]


def test_parser_recorded_on_source_document(monkeypatch, tmp_path) -> None:
    repo = FakeRepo()
    repo.install(monkeypatch, tmp_path)  # forces DOCLING_ENABLED=false
    response = upload("voyager.pdf", make_minimal_pdf(BROCHURE))
    assert response.status_code == 202
    drain_worker()
    # the parser is recorded on the source document's parse_status (surfaced to
    # the reviewer) by the worker, not returned in the async upload response
    [parse_status] = repo.parse_statuses.values()
    assert parse_status.startswith("parsed:pypdf")
