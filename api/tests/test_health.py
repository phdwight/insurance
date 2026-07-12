from api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_chat_validates_input() -> None:
    assert client.post("/chat", json={}).status_code == 422
    bad_mode = {"session_id": "s", "message": "hi", "mode": "psychic"}
    assert client.post("/chat", json=bad_mode).status_code == 422


def test_cors_preflight_allows_pwa_origin() -> None:
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
