"""Admin-token auth on the ingestion data surface."""

import ingestion.main as ingestion_main
from fastapi.testclient import TestClient

from ingestion import repository

client = TestClient(ingestion_main.app)


def test_open_when_no_token_configured(monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(repository, "list_insurers", lambda: [])
    assert client.get("/insurers").status_code == 200


def test_data_endpoints_locked_when_token_set(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    monkeypatch.setattr(repository, "list_insurers", lambda: [])
    monkeypatch.setattr(repository, "list_reviews", lambda status="x": [])

    # no token -> 401 on every data endpoint (uploads, reviews, files, lists)
    assert client.get("/insurers").status_code == 401
    assert client.get("/reviews").status_code == 401
    assert client.post("/documents", files={"file": ("a.txt", b"x")}).status_code == 401
    assert client.get("/documents/x/file").status_code == 401
    assert client.post("/reviews/x/reject", json={}).status_code == 401

    # wrong token -> still 401
    bad = {"authorization": "Bearer nope"}
    assert client.get("/insurers", headers=bad).status_code == 401

    # bearer header works; query param works (for opening documents in a tab)
    good = {"authorization": "Bearer s3cret"}
    assert client.get("/insurers", headers=good).status_code == 200
    assert client.get("/insurers?token=s3cret").status_code == 200

    # the page shell and health stay open (page carries no data itself)
    assert client.get("/admin").status_code == 200
    assert client.get("/health").status_code == 200
