"""Thin MCP client for the policy-catalog server (streamable HTTP).

One connection per call — the server is stateless, and recommendation turns
make only a handful of calls.
"""

import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agent.config import MCP_SERVER_URL


async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool {name} failed: {result.content}")
            return json.loads(result.content[0].text)


async def list_product_lines() -> list[dict[str, Any]]:
    return await call_tool("list_product_lines", {})


async def search_policies(**kwargs: Any) -> dict[str, Any]:
    return await call_tool("search_policies", {k: v for k, v in kwargs.items() if v is not None})


async def get_policy(slug: str) -> dict[str, Any]:
    return await call_tool("get_policy", {"slug": slug})
