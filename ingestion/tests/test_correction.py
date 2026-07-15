"""Auto-correction on approve.

When an approved draft fails validation, the large model re-reads the document
and returns a corrected draft for another human review — capped at 3 passes.
A valid draft still publishes straight through; a cap or a disabled corrector
falls back to a plain validation error for a manual fix."""

import ingestion.main as ingestion_main
from fastapi.testclient import TestClient

from ingestion import correction, repository

client = TestClient(ingestion_main.app)

VALID = {
    "name": "Demo Voyager",
    "insurer_name": "Byahero Travel Insurance Co.",
    "product_line": "travel",
    "summary": "Single-trip travel cover.",
    "premium_min": "900",
    "coverage": {"line": "travel", "medical_limit": "3000000"},
}
# product_line disagrees with coverage.line → PolicyDraft validation fails.
INVALID = {**VALID, "product_line": "life"}


def _review(monkeypatch, tmp_path, attempts=0, with_file=True):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        repository,
        "get_review",
        lambda run_id: {
            "id": run_id,
            "status": "pending_review",
            "file_ref": str(pdf) if with_file else None,
            "correction_attempts": attempts,
        },
    )


def test_valid_draft_publishes(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    _review(monkeypatch, tmp_path)
    monkeypatch.setattr(repository, "publish", lambda *a, **k: {"slug": "demo-voyager"})
    r = client.post("/reviews/r1/approve", json={"draft": VALID})
    assert r.status_code == 200
    assert r.json()["published"]["slug"] == "demo-voyager"


def test_invalid_draft_triggers_correction(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    _review(monkeypatch, tmp_path, attempts=0)
    monkeypatch.setattr(correction, "correction_enabled", lambda: True)

    async def fake_correct(data, draft, errors):
        # the model "fixes" the mismatch by trusting the coverage line
        return {**draft, "product_line": "travel"}

    monkeypatch.setattr(correction, "correct_draft", fake_correct)
    stored = {}
    monkeypatch.setattr(
        repository, "store_corrected_draft", lambda run_id, draft: stored.update(draft)
    )

    r = client.post("/reviews/r1/approve", json={"draft": INVALID})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "corrected"
    assert body["attempt"] == 1 and body["max_attempts"] == 3
    assert body["draft"]["product_line"] == "travel"  # the corrected draft
    assert stored["product_line"] == "travel"  # persisted for re-review


def test_correction_cap_falls_back_to_manual(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    _review(monkeypatch, tmp_path, attempts=3)  # already at the cap
    monkeypatch.setattr(correction, "correction_enabled", lambda: True)
    r = client.post("/reviews/r1/approve", json={"draft": INVALID})
    assert r.status_code == 422  # surfaced for a manual fix
    detail = r.json()["detail"]
    assert detail and any("coverage" in e["msg"] for e in detail)


def test_correction_disabled_falls_back_to_manual(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    _review(monkeypatch, tmp_path, attempts=0)
    monkeypatch.setattr(correction, "correction_enabled", lambda: False)
    r = client.post("/reviews/r1/approve", json={"draft": INVALID})
    assert r.status_code == 422
