"""Functional test of the full HTTP surface: FastAPI /chat SSE endpoint ->
graph -> discriminator engine -> verify -> present, across a multi-turn
session persisted by the checkpointer. Only the MCP catalog is faked."""

import json

import agent.main as agent_main
from fastapi.testclient import TestClient

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
        "exclusions": [],
        "summary": f"{destinations} cover.",
        "verified_at": "2026-07-10",
    }


CATALOG = {
    p["slug"]: p
    for p in (
        travel_policy("domestic-hopper", "domestic", False, False, 15, 85, 200),
        travel_policy("asia-lite", "asia", False, False, 30, 75, 400),
        travel_policy("asia-plus", "asia", False, True, 45, 75, 700),
        travel_policy("worldwide-explorer", "worldwide", True, True, 60, 70, 1500),
    )
}


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for frame in body.strip().split("\n\n"):
        event, data = "message", "{}"
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:]
        events.append((event, json.loads(data)))
    return events


def install_fakes(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VERIFIER_MODELS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)  # -> MemorySaver

    async def fake_search(**kwargs):
        return {"results": [{"slug": s} for s in CATALOG]}

    async def fake_get(slug):
        return dict(CATALOG[slug])

    async def fake_lines():
        return [
            {"code": "travel", "name": "Travel Insurance", "policy_count": 4},
            {"code": "life", "name": "Life Insurance", "policy_count": 2},
            {"code": "pet", "name": "Pet Insurance", "policy_count": 0},  # hidden
        ]

    monkeypatch.setattr(nodes.mcp_client, "search_policies", fake_search)
    monkeypatch.setattr(nodes.mcp_client, "get_policy", fake_get)
    monkeypatch.setattr(nodes.mcp_client, "list_product_lines", fake_lines)


def post_turn(client: TestClient, session: str, message: str) -> list[tuple[str, dict]]:
    response = client.post(
        "/chat", json={"session_id": session, "message": message, "mode": "guided"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def test_multi_turn_conversation_over_sse(monkeypatch) -> None:
    install_fakes(monkeypatch)

    with TestClient(agent_main.app) as client:  # `with` runs the lifespan
        # Turn 1: line detected -> profile event + a typed question, then done
        events = post_turn(client, "sse-1", "I need travel insurance")
        kinds = [event for event, _ in events]
        assert kinds[-1] == "done"
        question = dict(events)[ "question"]
        assert question["input_type"] == "number"  # trip length splits best
        profile = dict(events)["profile_update"]
        assert profile["product_lines"] == ["travel"]

        # Turn 2 (same session — checkpointer must remember the pending
        # question): answer narrows 4 -> 2 -> final recommendations
        events = post_turn(client, "sse-1", "45 days")
        by_kind = dict(events)
        slugs = [p["slug"] for p in by_kind["recommendations"]["travel"]]
        assert set(slugs) == {"asia-plus", "worldwide-explorer"}
        assert "message" in by_kind  # human-readable summary with disclaimer
        assert [event for event, _ in events][-1] == "done"

        # A different session id starts clean (no leakage between sessions),
        # and bootstrap options come from the CATALOG: only lines with
        # published policies are offered (pet has 0 -> hidden)
        events = post_turn(client, "sse-2", "hello po")
        assert dict(events)["question"]["options"] == ["Travel", "Life"]


def test_stream_reports_errors_instead_of_crashing(monkeypatch) -> None:
    install_fakes(monkeypatch)

    async def broken_search(**kwargs):
        raise RuntimeError("catalog exploded")

    monkeypatch.setattr(nodes.mcp_client, "search_policies", broken_search)

    with TestClient(agent_main.app) as client:
        events = post_turn(client, "sse-err", "travel insurance please")
        by_kind = dict(events)
        assert "catalog exploded" in by_kind["error"]["detail"]
        assert [event for event, _ in events][-1] == "done"  # stream still terminates
