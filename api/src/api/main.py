"""API gateway: the PWA's single backend origin.

- POST /chat          -> streams SSE through from the agent service
- GET  /product-lines -> proxies the catalog's plain REST route (chip data)
"""

import os
import time
from collections import deque

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8001")
MCP_HTTP_URL = os.environ.get("MCP_HTTP_URL", "http://localhost:8002")
INGESTION_URL = os.environ.get("INGESTION_URL", "http://localhost:8003")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

# --- /chat rate limit --------------------------------------------------------
# /chat is the only endpoint that can spend LLM tokens, so it gets a per-client
# sliding window (a human sends a few messages a minute; a script hammering it
# is token burn). In-memory and per-process by design — one uvicorn worker per
# container here; a shared/distributed limiter is a scale trigger, not an MVP
# need. RATE_LIMIT_CHAT="30/60" = 30 requests per 60s per client; "off" disables.

RATE_LIMIT_MESSAGE = "You're sending messages very quickly — please wait a moment and try again."
_MAX_TRACKED_CLIENTS = 10_000  # bound memory if someone rotates addresses

_windows: dict[str, deque] = {}


def _rate_config() -> tuple[int, float] | None:
    raw = os.environ.get("RATE_LIMIT_CHAT", "30/60").strip().lower()
    if raw in ("", "off", "0", "false", "none"):
        return None
    try:
        count, seconds = raw.split("/")
        return max(1, int(count)), max(1.0, float(seconds))
    except ValueError:
        return 30, 60.0  # malformed config: fall back to the default, never open


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:  # first hop = the original client when behind a proxy
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _allow_chat(request: Request) -> bool:
    config = _rate_config()
    if config is None:
        return True
    limit, window_seconds = config
    now = time.monotonic()
    key = _client_key(request)
    window = _windows.get(key)
    if window is None:
        if len(_windows) >= _MAX_TRACKED_CLIENTS:
            # Opportunistic sweep of idle clients before tracking a new one.
            cutoff = now - window_seconds
            for stale_key in [k for k, w in _windows.items() if not w or w[0] < cutoff]:
                _windows.pop(stale_key, None)
        window = _windows.setdefault(key, deque())
    while window and window[0] < now - window_seconds:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True

app = FastAPI(title="Insurance API Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    mode: str = Field(default="freeform", pattern="^(freeform|guided)$")


@app.get("/product-lines")
async def product_lines() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{MCP_HTTP_URL}/product-lines")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"catalog unavailable: {error}") from error


@app.get("/compare")
async def compare(slugs: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{MCP_HTTP_URL}/compare", params={"slugs": slugs})
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code, detail=error.response.text
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"catalog unavailable: {error}") from error


async def _proxy_public_file(path: str) -> Response:
    """Pass a public policy file through from the ingestion service.

    The ingestion service enforces eligibility (published policy AND a public
    doc_type — brochure/product_summary; contracts and unknown slugs 404).
    Proxying through the gateway means the ingestion hostname can sit entirely
    behind an access layer (e.g. Cloudflare Access) without breaking the
    end-user brochure covers the PWA shows."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.get(f"{INGESTION_URL}{path}")
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"files unavailable: {error}") from error
    if upstream.status_code != 200:
        raise HTTPException(status_code=upstream.status_code, detail="not available")
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"cache-control": upstream.headers.get("cache-control", "public, max-age=3600")},
    )


@app.get("/policies/{slug}/brochure")
async def policy_brochure(slug: str) -> Response:
    return await _proxy_public_file(f"/policies/{slug}/brochure")


@app.get("/policies/{slug}/document")
async def policy_document(slug: str) -> Response:
    return await _proxy_public_file(f"/policies/{slug}/document")


@app.post("/chat")
async def chat(request: ChatRequest, raw_request: Request) -> StreamingResponse:
    if not _allow_chat(raw_request):
        raise HTTPException(status_code=429, detail=RATE_LIMIT_MESSAGE)

    async def stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{AGENT_URL}/chat", json=request.model_dump()
            ) as upstream:
                async for chunk in upstream.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "api"}
