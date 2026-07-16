"""LLM_ECONOMY degradation ladder (token economy phase 4).

full = writer + panel + extractor; lean = drop the panel; deterministic = zero
LLM calls with template explanations rendered from verified fields. Every rung
keeps the product fully usable and honest."""

import asyncio

from langchain_core.messages import HumanMessage

from agent import economy, expl_cache, nodes
from shared import NeedsProfile

RECS = {
    "life": [
        {
            "slug": "demo-term",
            "name": "Demo Term",
            "premium_min": 800,
            "premium_frequency": "monthly",
            "eligibility": {"age_min": 18, "age_max": 55},
            "coverage": {"line": "life", "policy_type": "term"},
        }
    ]
}

PROFILE = {
    "product_lines": ["life"],
    "age": 35,
    "budget_amount": 3000,
    "per_line": {"life": {"policy_type": "term"}},
}


def test_mode_parsing(monkeypatch) -> None:
    monkeypatch.delenv("LLM_ECONOMY", raising=False)
    assert economy.mode() == "full"
    monkeypatch.setenv("LLM_ECONOMY", "LEAN")
    assert economy.mode() == "lean"
    monkeypatch.setenv("LLM_ECONOMY", "nonsense")
    assert economy.mode() == "full"  # fail open to normal behavior
    monkeypatch.setenv("LLM_ECONOMY", "deterministic")
    assert not economy.writer_enabled()
    assert not economy.extractor_enabled()
    assert not economy.panel_enabled()
    monkeypatch.setenv("LLM_ECONOMY", "lean")
    assert economy.writer_enabled() and not economy.panel_enabled()


def test_deterministic_mode_explains_without_any_llm(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ECONOMY", "deterministic")
    monkeypatch.setattr(nodes, "llm_available", lambda: True)  # key present, still no calls

    async def boom(*args):
        raise AssertionError("LLM called in deterministic mode")

    monkeypatch.setattr(nodes, "_explain_with_llm", boom)
    monkeypatch.setattr(expl_cache, "get", boom)

    update = asyncio.run(nodes.explain({"profile": PROFILE, "recommendations": RECS}))
    reasons = update["recommendations"]["life"][0]["match_reasons"]
    texts = [reason["text"] for reason in reasons]
    # Grounded template reasons, not the generic fallback line.
    assert any("age 35" in text and "18–55" in text for text in texts)
    assert any("₱800" in text and "₱3,000" in text for text in texts)
    assert any("policy type: term" in text for text in texts)
    assert update["recommendations"]["life"][0]["match_strength"] == "strong"


def test_deterministic_mode_skips_extractor(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ECONOMY", "deterministic")
    monkeypatch.setattr(nodes, "llm_available", lambda: True)

    async def boom(*args):
        raise AssertionError("extractor called in deterministic mode")

    monkeypatch.setattr(nodes, "_extract_with_llm", boom)
    state = {
        "messages": [HumanMessage(content="I want life insurance for my father")],
        "mode": "freeform",
        "profile": {},
    }
    update = asyncio.run(nodes.ingest(state))  # rich message would normally extract
    assert update["profile"]["product_lines"] == ["life"]  # deterministic detection intact


def test_lean_mode_skips_panel_but_keeps_writer(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ECONOMY", "lean")
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:a,prov2:b")  # panel configured...
    monkeypatch.setattr(nodes, "llm_available", lambda: True)

    async def fake_writer(profile, recommendations):
        return {"demo-term": [{"text": "written", "kind": "match"}]}

    async def boom_panel(recommendations):
        raise AssertionError("panel called in lean mode")

    monkeypatch.setattr(nodes, "_explain_with_llm", fake_writer)
    monkeypatch.delenv("DATABASE_URL", raising=False)  # cache off — focus on gating

    from agent import verifier

    monkeypatch.setattr(verifier, "verify_recommendations", boom_panel)

    state = {"profile": PROFILE, "recommendations": RECS}
    update = asyncio.run(nodes.explain(state))
    assert update["recommendations"]["life"][0]["match_reasons"][0]["text"] == "written"
    result = asyncio.run(nodes.verify_explanations({**state, **update}))
    assert result["recommendations"]["life"][0]["match_reasons"][0]["text"] == "written"


def test_cache_key_separates_economy_modes(monkeypatch) -> None:
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)
    monkeypatch.setenv("LLM_ECONOMY", "full")
    full_key = expl_cache.cache_key(PROFILE, RECS)
    monkeypatch.setenv("LLM_ECONOMY", "lean")
    assert expl_cache.cache_key(PROFILE, RECS) != full_key


def test_renderer_flags_gaps_and_partial_strength(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ECONOMY", "deterministic")
    monkeypatch.setattr(nodes, "llm_available", lambda: True)
    recs = {
        "life": [
            {
                "slug": "vague-plan",
                "eligibility": {"age_min": 18, "age_max": 55},
                # user asked for a policy type; this plan doesn't state one
                "coverage": {"line": "life"},
            }
        ]
    }
    update = asyncio.run(nodes.explain({"profile": PROFILE, "recommendations": recs}))
    policy = update["recommendations"]["life"][0]
    kinds = {reason["kind"] for reason in policy["match_reasons"]}
    assert "gap" in kinds  # unstated policy_type surfaced honestly
    assert policy["match_strength"] == "partial"


def test_deterministic_reasons_are_grounded_only() -> None:
    # No profile answers, no bounds -> nothing to claim -> empty (caller falls
    # back to the generic line). The renderer never invents.
    from agent.verify import deterministic_reasons

    assert deterministic_reasons({"coverage": {"line": "life"}}, NeedsProfile()) == []
