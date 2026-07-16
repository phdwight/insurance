"""Catalog TTL cache (scaling slab): read-only MCP calls are memoized so every
turn's re-narrowing doesn't pay search + get_policy×N round-trips for a catalog
that doesn't change mid-conversation. Bounded staleness via CATALOG_CACHE_SECONDS;
0 disables; errors never cache; hits are mutation-safe deep copies."""

import asyncio

from agent import mcp_client


def _patch_upstream(monkeypatch, calls: list) -> None:
    async def fake_call_tool(name, arguments):
        calls.append((name, dict(arguments)))
        return {"name": name, "arguments": arguments, "nested": {"n": len(calls)}}

    monkeypatch.setattr(mcp_client, "call_tool", fake_call_tool)
    mcp_client.clear_cache()


def test_repeat_call_hits_cache(monkeypatch) -> None:
    calls: list = []
    _patch_upstream(monkeypatch, calls)
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "60")

    first = asyncio.run(mcp_client.get_policy("demo-term"))
    second = asyncio.run(mcp_client.get_policy("demo-term"))
    assert len(calls) == 1  # one upstream round-trip, second served from cache
    assert first == second


def test_different_arguments_are_different_entries(monkeypatch) -> None:
    calls: list = []
    _patch_upstream(monkeypatch, calls)
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "60")

    asyncio.run(mcp_client.get_policy("a"))
    asyncio.run(mcp_client.get_policy("b"))
    asyncio.run(mcp_client.search_policies(product_line="life"))
    asyncio.run(mcp_client.search_policies(product_line="pet"))
    assert len(calls) == 4


def test_zero_ttl_disables_caching(monkeypatch) -> None:
    calls: list = []
    _patch_upstream(monkeypatch, calls)
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "0")

    asyncio.run(mcp_client.list_product_lines())
    asyncio.run(mcp_client.list_product_lines())
    assert len(calls) == 2


def test_expired_entry_refetches(monkeypatch) -> None:
    calls: list = []
    _patch_upstream(monkeypatch, calls)
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "60")

    asyncio.run(mcp_client.get_policy("demo-term"))
    # Age the entry past the TTL, as if a minute passed.
    key, (stamp, value) = next(iter(mcp_client._cache.items()))
    mcp_client._cache[key] = (stamp - 61, value)
    asyncio.run(mcp_client.get_policy("demo-term"))
    assert len(calls) == 2


def test_hits_are_mutation_safe_copies(monkeypatch) -> None:
    calls: list = []
    _patch_upstream(monkeypatch, calls)
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "60")

    first = asyncio.run(mcp_client.get_policy("demo-term"))
    first["nested"]["n"] = "poisoned"  # downstream mutation...
    second = asyncio.run(mcp_client.get_policy("demo-term"))
    assert second["nested"]["n"] != "poisoned"  # ...never reaches the cache


def test_upstream_error_is_not_cached(monkeypatch) -> None:
    attempts: list = []

    async def flaky(name, arguments):
        attempts.append(name)
        if len(attempts) == 1:
            raise RuntimeError("catalog down")
        return {"ok": True}

    monkeypatch.setattr(mcp_client, "call_tool", flaky)
    mcp_client.clear_cache()
    monkeypatch.setenv("CATALOG_CACHE_SECONDS", "60")

    try:
        asyncio.run(mcp_client.get_policy("demo"))
    except RuntimeError:
        pass
    assert asyncio.run(mcp_client.get_policy("demo")) == {"ok": True}
    assert len(attempts) == 2
