"""Thin MCP client for the policy-catalog server (streamable HTTP).

One connection per call — the server is stateless. Read-only catalog calls are
memoized for a short TTL (scaling slab): every conversation turn re-narrows
from the full candidate set, so without a cache each turn pays search +
get_policy×N MCP round-trips (HTTP connection + handshake + SQL each) for a
catalog that effectively never changes mid-conversation.

``CATALOG_CACHE_SECONDS`` (default 60, ``0`` disables) bounds staleness: a
newly published policy appears in fresh conversations within a minute. The
catalog is small (hundreds of entries at most), so the cache is size-bounded
by nature; expired entries are dropped on access.
"""

import copy
import json
import os
import time
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agent.config import MCP_SERVER_URL

_cache: dict[str, tuple[float, Any]] = {}


def _cache_ttl() -> float:
    try:
        return float(os.environ.get("CATALOG_CACHE_SECONDS", "60"))
    except ValueError:
        return 60.0


def clear_cache() -> None:
    _cache.clear()


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool {name} failed: {result.content}")
            return json.loads(result.content[0].text)


async def _cached_call(name: str, arguments: dict[str, Any]) -> Any:
    """call_tool memoized for read-only catalog tools. Errors never cache.
    Returns a deep copy so downstream mutation can't poison the cache."""
    ttl = _cache_ttl()
    if ttl <= 0:
        return await call_tool(name, arguments)
    key = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < ttl:
        return copy.deepcopy(hit[1])
    _cache.pop(key, None)
    value = await call_tool(name, arguments)
    _cache[key] = (now, value)
    return copy.deepcopy(value)


async def list_product_lines() -> list[dict[str, Any]]:
    return await _cached_call("list_product_lines", {})


async def search_policies(**kwargs: Any) -> dict[str, Any]:
    return await _cached_call(
        "search_policies", {k: v for k, v in kwargs.items() if v is not None}
    )


async def get_policy(slug: str) -> dict[str, Any]:
    return await _cached_call("get_policy", {"slug": slug})
