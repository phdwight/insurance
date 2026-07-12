from mcp_server import queries
from mcp_server.main import app
from starlette.testclient import TestClient

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mcp-server"}


class _FakeResult:
    def __init__(self):
        self._rows = []

    def __iter__(self):
        return iter(self._rows)


class _FakeConn:
    def execute(self, sql, params=None):
        return _FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_embedding_failure_degrades_to_sql_ranking(monkeypatch) -> None:
    """Rate limits/outages on the embedding API must never fail the search."""
    monkeypatch.setattr(queries, "embeddings_enabled", lambda: True)

    def exploding_embed(text):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(queries, "embed_query", exploding_embed)
    monkeypatch.setattr(queries, "get_engine", lambda: type(
        "E", (), {"connect": lambda self: _FakeConn()}
    )())

    result = queries.search_policies("travel", needs_description="trip to Japan")
    assert result["ranking"] == "premium_asc"  # graceful fallback
    assert "semantic ranking unavailable" in result["ranking_note"]  # never silent


def test_compare_rest_route(monkeypatch) -> None:
    monkeypatch.setattr(
        queries,
        "compare_policies",
        lambda slugs: {"policies": slugs, "not_found": [], "comparison": {}},
    )
    response = client.get("/compare?slugs=a,b")
    assert response.status_code == 200
    assert response.json()["policies"] == ["a", "b"]

    assert client.get("/compare?slugs=only-one").status_code == 400
    assert client.get("/compare?slugs=a,b,c,d,e").status_code == 400
