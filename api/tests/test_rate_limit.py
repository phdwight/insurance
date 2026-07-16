"""/chat rate limiting: the only token-spending endpoint gets a per-client
sliding window. Over the limit -> 429 with a human message; other clients and
other endpoints are unaffected; 'off' disables."""

import api.main as api_main
from fastapi.testclient import TestClient

BODY = {"session_id": "rate-test", "message": "hello", "mode": "guided"}


def make_client(monkeypatch, limit: str) -> TestClient:
    monkeypatch.setenv("RATE_LIMIT_CHAT", limit)
    api_main._windows.clear()
    # /chat proxies upstream after the limit check; a dead upstream turns into
    # a 502/500 — anything but 429 counts as "allowed" for these tests.
    return TestClient(api_main.app, raise_server_exceptions=False)


def post_chat(client: TestClient, ip: str = "203.0.113.9") -> int:
    response = client.post("/chat", json=BODY, headers={"x-forwarded-for": ip})
    return response.status_code


def test_over_limit_returns_429_with_message(monkeypatch) -> None:
    client = make_client(monkeypatch, "3/60")
    codes = [post_chat(client) for _ in range(4)]
    assert all(code != 429 for code in codes[:3])
    assert codes[3] == 429
    response = client.post("/chat", json=BODY, headers={"x-forwarded-for": "203.0.113.9"})
    assert response.json()["detail"] == api_main.RATE_LIMIT_MESSAGE


def test_clients_are_isolated_per_ip(monkeypatch) -> None:
    client = make_client(monkeypatch, "2/60")
    assert post_chat(client, ip="198.51.100.1") != 429
    assert post_chat(client, ip="198.51.100.1") != 429
    assert post_chat(client, ip="198.51.100.1") == 429  # this client is done...
    assert post_chat(client, ip="198.51.100.2") != 429  # ...others are not


def test_off_switch_disables_limiting(monkeypatch) -> None:
    client = make_client(monkeypatch, "off")
    codes = [post_chat(client) for _ in range(10)]
    assert all(code != 429 for code in codes)


def test_window_slides(monkeypatch) -> None:
    client = make_client(monkeypatch, "2/60")
    assert post_chat(client) != 429
    assert post_chat(client) != 429
    assert post_chat(client) == 429
    # Age the recorded hits past the window: the client is welcome again.
    window = api_main._windows["203.0.113.9"]
    for i in range(len(window)):
        window[i] -= 61
    assert post_chat(client) != 429


def test_malformed_config_falls_back_to_default_not_open(monkeypatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_CHAT", "lots")
    assert api_main._rate_config() == (30, 60.0)


def test_other_endpoints_unlimited(monkeypatch) -> None:
    client = make_client(monkeypatch, "1/60")
    post_chat(client)
    post_chat(client)  # chat now limited for this ip
    for _ in range(5):
        assert client.get("/health").status_code == 200
