"""Public brochure/document endpoints.

These are served WITHOUT the admin token (end users see them in results), so the
eligibility gate is load-bearing: only a published brochure/product summary is
exposed — a policy_contract (which may carry PII) must never leak, and an
unknown/unpublished slug reveals nothing."""

import ingestion.main as ingestion_main
from fastapi.testclient import TestClient

from ingestion import preview, repository

client = TestClient(ingestion_main.app)


def _stub(monkeypatch, doc_type, path=""):
    monkeypatch.setattr(
        repository,
        "get_published_source_document",
        lambda slug: None
        if doc_type is None
        else {"id": "d", "file_ref": str(path), "doc_type": doc_type},
    )


def test_brochure_document_is_public_without_a_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")  # gate is ON for the rest of the surface
    pdf = tmp_path / "brochure.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake brochure")
    _stub(monkeypatch, "brochure", pdf)
    # no token presented, yet served — these endpoints are deliberately public
    assert client.get("/policies/demo/document").status_code == 200


def test_cover_image_is_rendered_and_public(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DOCS_DIR", str(tmp_path))
    pdf = tmp_path / "brochure.pdf"
    pdf.write_bytes(b"%PDF fake")
    png = tmp_path / "cover.png"
    png.write_bytes(b"\x89PNG\r\n fake")
    _stub(monkeypatch, "product_summary", pdf)
    monkeypatch.setattr(preview, "render_cover", lambda src, cache: png)
    response = client.get("/policies/demo/brochure")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_policy_contract_is_never_exposed(monkeypatch, tmp_path) -> None:
    pdf = tmp_path / "contract.pdf"
    pdf.write_bytes(b"%PDF secret PII")
    _stub(monkeypatch, "policy_contract", pdf)
    assert client.get("/policies/demo/document").status_code == 404
    assert client.get("/policies/demo/brochure").status_code == 404


def test_unpublished_or_unknown_slug_is_404(monkeypatch) -> None:
    _stub(monkeypatch, None)
    assert client.get("/policies/ghost/document").status_code == 404
    assert client.get("/policies/ghost/brochure").status_code == 404
