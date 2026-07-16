"""Explanation cache: the writer + judge panel run once per outcome bucket.

Covers key content-addressing (what must and must not change the key), the
explain-node hit path (no writer call), the miss path (writer runs, the
verified result is stored), the off switch, and failure safety (an unreachable
cache reads as a miss — the conversation never depends on it)."""

import asyncio

import pytest

from agent import expl_cache, nodes

PROFILE = {"product_lines": ["life"], "age": 35, "budget_amount": 3000}

RECS = {
    "life": [
        {
            "slug": "demo-term",
            "name": "Demo Term",
            "premium_min": 800,
            "verified_at": "2026-07-10",
            "eligibility": {"age_min": 18, "age_max": 55},
        }
    ]
}


def explained(recs: dict) -> dict:
    out = {
        line: [dict(p, match_reasons=[{"text": "ok", "kind": "match"}]) for p in policies]
        for line, policies in recs.items()
    }
    return out


# ---------- key content-addressing ----------


def test_key_is_deterministic_and_content_addressed(monkeypatch) -> None:
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)
    assert expl_cache.cache_key(PROFILE, RECS) == expl_cache.cache_key(PROFILE, RECS)

    # A different user answer -> different bucket.
    other_profile = dict(PROFILE, age=60)
    assert expl_cache.cache_key(other_profile, RECS) != expl_cache.cache_key(PROFILE, RECS)

    # A re-versioned policy changes its content -> key self-invalidates.
    reversioned = {"life": [dict(RECS["life"][0], verified_at="2026-08-01")]}
    assert expl_cache.cache_key(PROFILE, reversioned) != expl_cache.cache_key(PROFILE, RECS)


def test_key_depends_on_judge_panel(monkeypatch) -> None:
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)
    without_panel = expl_cache.cache_key(PROFILE, RECS)
    monkeypatch.setenv("VERIFIER_MODELS", "prov:judge-a,prov:judge-b")
    assert expl_cache.cache_key(PROFILE, RECS) != without_panel


def test_enabled_needs_dsn_and_respects_off(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EXPLANATION_CACHE", raising=False)
    assert not expl_cache.enabled()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@db:5432/x")
    assert expl_cache.enabled()
    monkeypatch.setenv("EXPLANATION_CACHE", "off")
    assert not expl_cache.enabled()


# ---------- explain node: hit and miss ----------


def _setup_llm(monkeypatch, writer_calls: list) -> None:
    monkeypatch.setattr(nodes, "llm_available", lambda: True)

    async def fake_writer(profile, recommendations):
        writer_calls.append(profile)
        return {"demo-term": [{"text": "written", "kind": "match"}]}

    monkeypatch.setattr(nodes, "_explain_with_llm", fake_writer)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@db:5432/x")
    monkeypatch.delenv("EXPLANATION_CACHE", raising=False)


def test_cache_hit_skips_writer_and_panel(monkeypatch) -> None:
    writer_calls: list = []
    _setup_llm(monkeypatch, writer_calls)
    cached_payload = explained(RECS)

    async def fake_get(key):
        return cached_payload

    monkeypatch.setattr(expl_cache, "get", fake_get)

    update = asyncio.run(nodes.explain({"profile": PROFILE, "recommendations": RECS}))
    assert update["recommendations"] == cached_payload
    assert update["explanations_cached"] is True
    assert writer_calls == []  # the whole point: no writer tokens spent

    # And the panel/store are skipped downstream.
    puts: list = []

    async def fake_put(key, recs):
        puts.append(key)

    monkeypatch.setattr(expl_cache, "put", fake_put)
    verdict = asyncio.run(nodes.verify_explanations(update))
    assert verdict == {} and puts == []


def test_cache_miss_runs_writer_then_stores_verified_result(monkeypatch) -> None:
    writer_calls: list = []
    _setup_llm(monkeypatch, writer_calls)

    async def fake_get(key):
        return None

    puts: list = []

    async def fake_put(key, recs):
        puts.append((key, recs))

    monkeypatch.setattr(expl_cache, "get", fake_get)
    monkeypatch.setattr(expl_cache, "put", fake_put)
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)

    state = {"profile": PROFILE, "recommendations": RECS}
    update = asyncio.run(nodes.explain(state))
    assert len(writer_calls) == 1
    assert update["explanations_cached"] is False
    assert update["expl_cache_key"]

    asyncio.run(nodes.verify_explanations({**state, **update}))
    assert len(puts) == 1
    key, stored = puts[0]
    assert key == update["expl_cache_key"]
    reasons = stored["life"][0]["match_reasons"]
    assert reasons == [{"text": "written", "kind": "match"}]


def test_cache_off_never_touches_cache(monkeypatch) -> None:
    writer_calls: list = []
    _setup_llm(monkeypatch, writer_calls)
    monkeypatch.setenv("EXPLANATION_CACHE", "off")

    async def boom(*args):  # any cache access is a bug when disabled
        raise AssertionError("cache accessed while off")

    monkeypatch.setattr(expl_cache, "get", boom)
    monkeypatch.setattr(expl_cache, "put", boom)

    update = asyncio.run(nodes.explain({"profile": PROFILE, "recommendations": RECS}))
    assert len(writer_calls) == 1
    assert update["expl_cache_key"] is None
    asyncio.run(
        nodes.verify_explanations({"profile": PROFILE, "recommendations": RECS, **update})
    )  # no put -> no AssertionError


# ---------- failure safety ----------


@pytest.mark.parametrize("op", ["get", "put"])
def test_unreachable_cache_is_a_miss_not_an_error(monkeypatch, op) -> None:
    # Connection refused fast on a closed local port; both ops must swallow it.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")
    if op == "get":
        assert asyncio.run(expl_cache.get("k")) is None
    else:
        assert asyncio.run(expl_cache.put("k", RECS)) is None
