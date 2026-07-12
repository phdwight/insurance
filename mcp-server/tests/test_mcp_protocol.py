"""Functional test of the MCP server over the real MCP protocol (in-memory
transport): tool discovery, tool calls, JSON envelopes, and error paths.
Only the SQL layer (queries) is faked."""

import asyncio
import json

import mcp_server.main as server_main
from mcp.shared.memory import create_connected_server_and_client_session as connect
from mcp_server import queries

EXPECTED_TOOLS = {
    "list_product_lines",
    "list_insurers",
    "search_policies",
    "get_policy",
    "compare_policies",
}

FAKE_POLICY = {
    "slug": "demo-asia-traveler",
    "name": "Demo Asia Traveler",
    "insurer_name": "Byahero",
    "premium_min": 550,
    "currency": "PHP",
    "coverage": {"line": "travel"},
    "verified_at": "2026-07-10",
}


def install_fake_queries(monkeypatch) -> None:
    monkeypatch.setattr(
        queries,
        "list_product_lines",
        lambda: [{"code": "travel", "name": "Travel Insurance", "policy_count": 6}],
    )
    monkeypatch.setattr(
        queries,
        "search_policies",
        lambda **kwargs: {
            "ranking": "premium_asc",
            "count": 1,
            "results": [dict(FAKE_POLICY)],
            "echo": kwargs,
        },
    )
    monkeypatch.setattr(
        queries,
        "get_policy",
        lambda slug: dict(FAKE_POLICY) if slug == FAKE_POLICY["slug"] else None,
    )


def call(session_coro):
    return asyncio.run(session_coro)


def test_tools_and_calls_over_protocol(monkeypatch) -> None:
    install_fake_queries(monkeypatch)

    async def scenario():
        async with connect(server_main.mcp) as session:
            listed = await session.list_tools()
            assert {tool.name for tool in listed.tools} == EXPECTED_TOOLS
            # tool descriptions are the LLM's API docs — they must exist
            assert all(tool.description for tool in listed.tools)

            found = await session.call_tool(
                "search_policies",
                {"product_line": "travel", "max_premium": 2000.0, "limit": 3},
            )
            payload = json.loads(found.content[0].text)
            assert payload["results"][0]["slug"] == "demo-asia-traveler"
            assert payload["echo"]["max_premium"] == 2000.0  # args pass through

            detail = await session.call_tool("get_policy", {"slug": "demo-asia-traveler"})
            assert json.loads(detail.content[0].text)["premium_min"] == 550

    call(scenario())


def test_error_envelopes_over_protocol(monkeypatch) -> None:
    install_fake_queries(monkeypatch)

    async def scenario():
        async with connect(server_main.mcp) as session:
            missing = await session.call_tool("get_policy", {"slug": "ghost"})
            assert "error" in json.loads(missing.content[0].text)

            too_few = await session.call_tool("compare_policies", {"slugs": ["only-one"]})
            assert "between 2 and 4" in json.loads(too_few.content[0].text)["error"]

            too_many = await session.call_tool(
                "compare_policies", {"slugs": ["a", "b", "c", "d", "e"]}
            )
            assert "error" in json.loads(too_many.content[0].text)

    call(scenario())
