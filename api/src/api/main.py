"""API gateway: the PWA's single backend origin.

- POST /chat          -> streams SSE through from the agent service
- GET  /product-lines -> proxies the catalog's plain REST route (chip data)
"""

import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8001")
MCP_HTTP_URL = os.environ.get("MCP_HTTP_URL", "http://localhost:8002")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")

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


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
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
