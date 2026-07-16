"""Functional test of the gateway as a proxy: SSE passthrough from the agent
and catalog proxying, using a stub upstream behind an in-process transport."""

import api.main as api_main
import httpx
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route


def make_upstream(healthy: bool = True) -> Starlette:
    async def chat(request):
        body = await request.json()

        async def stream():
            yield f'event: question\ndata: {{"text": "echo {body["message"]}"}}\n\n'.encode()
            yield b"event: done\ndata: {}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def product_lines(request):
        if not healthy:
            return JSONResponse({"boom": True}, status_code=500)
        return JSONResponse([{"code": "travel", "name": "Travel Insurance", "policy_count": 6}])

    async def compare(request):
        slugs = request.query_params["slugs"].split(",")
        return JSONResponse({"policies": slugs, "not_found": [], "comparison": {}})

    async def brochure(request):
        # The ingestion service's eligibility gate: only the published slug
        # with a public doc_type serves a file; everything else 404s.
        if request.path_params["slug"] != "published-brochure":
            return JSONResponse({"detail": "not found"}, status_code=404)
        from starlette.responses import Response

        return Response(b"\x89PNG fake-cover", media_type="image/png")

    return Starlette(
        routes=[
            Route("/chat", chat, methods=["POST"]),
            Route("/product-lines", product_lines),
            Route("/compare", compare),
            Route("/policies/{slug}/brochure", brochure),
        ]
    )


def route_httpx_to(monkeypatch, upstream: Starlette) -> None:
    """Make every httpx.AsyncClient in the gateway hit the stub app in-process."""
    real_async_client = httpx.AsyncClient

    def patched(**kwargs):
        kwargs.pop("transport", None)
        return real_async_client(transport=httpx.ASGITransport(app=upstream), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


def test_chat_sse_passes_through_verbatim(monkeypatch) -> None:
    route_httpx_to(monkeypatch, make_upstream())
    client = TestClient(api_main.app)

    response = client.post(
        "/chat", json={"session_id": "s1", "message": "hi there", "mode": "guided"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: question" in response.text
    assert "echo hi there" in response.text  # request body reached the agent
    assert response.text.rstrip().endswith("data: {}")


def test_product_lines_proxied(monkeypatch) -> None:
    route_httpx_to(monkeypatch, make_upstream())
    client = TestClient(api_main.app)
    assert client.get("/product-lines").json()[0]["policy_count"] == 6


def test_compare_proxied(monkeypatch) -> None:
    route_httpx_to(monkeypatch, make_upstream())
    client = TestClient(api_main.app)
    body = client.get("/compare", params={"slugs": "a,b"}).json()
    assert body["policies"] == ["a", "b"]


def test_catalog_failure_maps_to_502(monkeypatch) -> None:
    route_httpx_to(monkeypatch, make_upstream(healthy=False))
    client = TestClient(api_main.app)
    response = client.get("/product-lines")
    assert response.status_code == 502
    assert "catalog unavailable" in response.json()["detail"]


def test_public_brochure_proxied_with_content_type(monkeypatch) -> None:
    # End users get brochure files via the gateway, so the ingestion hostname
    # can sit fully behind an access layer without breaking covers in results.
    route_httpx_to(monkeypatch, make_upstream())
    client = TestClient(api_main.app)
    response = client.get("/policies/published-brochure/brochure")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
    assert "max-age" in response.headers["cache-control"]


def test_ineligible_brochure_stays_404(monkeypatch) -> None:
    # The ingestion service's eligibility gate (unpublished / contract doc
    # types) must pass through untouched — the proxy never widens access.
    route_httpx_to(monkeypatch, make_upstream())
    client = TestClient(api_main.app)
    assert client.get("/policies/policy-contract-slug/brochure").status_code == 404
