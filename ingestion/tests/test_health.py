from fastapi.testclient import TestClient
from ingestion.main import app

from shared import app_version


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["service"] == "ingestion"
    # The running service must report the released version — it is what the
    # release flow verifies against the git tag (see README "Versioning").
    assert body["version"] == app_version()
