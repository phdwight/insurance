"""End-to-end graph tests: catalog-driven elicitation, no LLM key, mocked MCP.

Fake catalog has 4 travel policies so the agent must ask discriminating
questions (finalization threshold is TARGET_RESULTS = 3).
"""

import asyncio

from agent.graph import build_graph
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent import nodes


def travel_policy(slug, destinations, schengen, covid, max_days, age_max, premium):
    return {
        "slug": slug,
        "name": slug.replace("-", " ").title(),
        "insurer_name": "Byahero (Demo)",
        "premium_min": premium,
        "premium_max": premium * 3,
        "premium_frequency": "single",
        "currency": "PHP",
        "eligibility": {"age_min": 0, "age_max": age_max},
        "coverage": {
            "line": "travel",
            "destinations": destinations,
            "schengen_compliant": schengen,
            "covid_covered": covid,
            "max_trip_days": max_days,
        },
        "exclusions": ["Extreme sports"],
        "summary": f"{destinations} cover.",
        "verified_at": "2026-07-10",
    }


# max_trip_days all distinct (15/30/45/60) -> trip_days has the best split
# score (0.75) and is deterministically the first question asked.
CATALOG = {
    p["slug"]: p
    for p in (
        travel_policy("domestic-hopper", "domestic", False, False, 15, 85, 200),
        travel_policy("asia-lite", "asia", False, False, 30, 75, 400),
        travel_policy("asia-plus", "asia", False, True, 45, 75, 700),
        travel_policy("worldwide-explorer", "worldwide", True, True, 60, 70, 1500),
    )
}


def install_fake_catalog(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)

    async def fake_search(**kwargs):
        assert kwargs["product_line"] == "travel"
        return {"results": [{"slug": s} for s in CATALOG]}

    async def fake_get(slug):
        return dict(CATALOG[slug])

    async def fake_lines():
        return [{"code": "travel", "name": "Travel Insurance", "policy_count": len(CATALOG)}]

    monkeypatch.setattr(nodes.mcp_client, "search_policies", fake_search)
    monkeypatch.setattr(nodes.mcp_client, "get_policy", fake_get)
    monkeypatch.setattr(nodes.mcp_client, "list_product_lines", fake_lines)


def run_turn(graph, session: str, text: str) -> dict:
    return asyncio.run(
        graph.ainvoke(
            {"messages": [HumanMessage(content=text)], "mode": "guided", "done": False},
            {"configurable": {"thread_id": session}},
        )
    )


def test_bootstrap_question_when_no_line_detected(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())
    state = run_turn(graph, "s0", "hello po")
    assert "What would you like to protect" in state["pending_question"]
    # options are catalog-sourced: only travel has published policies here
    assert state["question"]["options"] == ["Travel"]
    assert state["done"] is False


def test_bootstrap_falls_back_to_static_options_if_catalog_down(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)

    async def broken_lines():
        raise RuntimeError("catalog down")

    monkeypatch.setattr(nodes.mcp_client, "list_product_lines", broken_lines)
    graph = build_graph(checkpointer=MemorySaver())
    state = run_turn(graph, "s0b", "hello po")
    assert state["question"]["options"] == nodes.FALLBACK_LINE_OPTIONS


def test_questions_derive_from_catalog_and_narrow(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())

    # Turn 1: catalog fetched (4 candidates) -> asks the attribute with the
    # best split across REAL policies: trip length (all four differ on it)
    state = run_turn(graph, "s1", "I need travel insurance")
    assert state["pending_disc"] == "travel.trip_days"
    assert state["question"]["input_type"] == "number"  # UI shows numeric input
    assert len(state["candidates"]["travel"]) == 4

    # Turn 2: "45 days" keeps only asia-plus (45) and worldwide (60)
    # -> under threshold -> finalized, both recommended, no more questions
    state = run_turn(graph, "s1", "about 45 days")
    assert state["done"] is True
    slugs = [p["slug"] for p in state["recommendations"]["travel"]]
    assert set(slugs) == {"asia-plus", "worldwide-explorer"}
    assert all(p["match_reasons"] for p in state["recommendations"]["travel"])


def test_covid_never_asked_if_it_stops_discriminating(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())
    state = run_turn(graph, "s4", "travel insurance")
    # after trip_days=50 only covid-covered policies remain -> covid question
    # would be pointless and must never surface
    state = run_turn(graph, "s4", "50 days")
    assert state["done"] is True or state["pending_disc"] != "travel.covid_required"


def test_honest_no_match_when_answers_exclude_everything(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())

    run_turn(graph, "s2", "travel insurance please")
    state = run_turn(graph, "s2", "90 days")  # exceeds every policy's max

    assert state["done"] is True
    assert not any(state["recommendations"].values())
    assert "no policy in the catalog" in state["messages"][-1].content


def test_bootstrap_never_loops_forever(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())
    state = run_turn(graph, "s5", "hello")
    turns = 1
    while not state.get("done") and turns < 10:
        state = run_turn(graph, "s5", "kamusta")  # never names a product line
        turns += 1
    assert state["done"] is True
    assert turns <= 4  # 3 bootstrap attempts + final goodbye
    assert "stop here" in state["messages"][-1].content


def test_unparseable_answers_never_loop_forever(monkeypatch) -> None:
    install_fake_catalog(monkeypatch)
    graph = build_graph(checkpointer=MemorySaver())
    state = run_turn(graph, "s3", "travel insurance")
    turns = 0
    while not state.get("done") and turns < 10:
        state = run_turn(graph, "s3", "hmm not sure")  # unparseable answers
        turns += 1
    assert state["done"] is True  # question budget forces finalization
    assert turns <= 7
