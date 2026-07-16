"""LLM spend ledger (token economy phase 5): call sites record usage by
(model, role), cache hits record as zero-token events, the daily budget warns
once per day, and a broken ledger never breaks a conversation."""

import asyncio
import logging

import agent.main as agent_main
from fastapi.testclient import TestClient

from agent import usage


def test_record_writes_one_row_per_model(monkeypatch) -> None:
    written: list = []

    async def fake_write(rows):
        written.extend(rows)

    monkeypatch.setattr(usage, "_write", fake_write)
    monkeypatch.setenv("DAILY_TOKEN_BUDGET", "0")  # skip the budget query
    asyncio.run(
        usage.record(
            "judge",
            {
                "openai:gpt-5.6-terra": {"input_tokens": 1200, "output_tokens": 40},
                "openai:gpt-5.6-luna": {"input_tokens": 1100, "output_tokens": 35},
            },
        )
    )
    assert sorted(written) == [
        ("openai:gpt-5.6-luna", "judge", 1100, 35),
        ("openai:gpt-5.6-terra", "judge", 1200, 40),
    ]


def test_record_event_is_zero_token(monkeypatch) -> None:
    written: list = []

    async def fake_write(rows):
        written.extend(rows)

    monkeypatch.setattr(usage, "_write", fake_write)
    asyncio.run(usage.record_event("explain_cache_hit"))
    assert written == [("-", "explain_cache_hit", 0, 0)]


def test_empty_usage_writes_nothing(monkeypatch) -> None:
    async def boom(rows):
        raise AssertionError("write called with no usage")

    monkeypatch.setattr(usage, "_write", boom)
    asyncio.run(usage.record("writer", {}))


def test_budget_warns_once_per_day(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DAILY_TOKEN_BUDGET", "1000")
    monkeypatch.setattr(usage, "_warned_days", set())

    async def fake_total():
        return 5000

    monkeypatch.setattr(usage, "_today_total", fake_total)
    with caplog.at_level(logging.WARNING, logger="agent"):
        asyncio.run(usage._check_budget())
        asyncio.run(usage._check_budget())
    warnings = [r for r in caplog.records if "DAILY_TOKEN_BUDGET exceeded" in r.message]
    assert len(warnings) == 1
    assert "5000" in warnings[0].message


def test_budget_quiet_when_unset_or_under(monkeypatch, caplog) -> None:
    monkeypatch.setattr(usage, "_warned_days", set())

    async def fake_total():
        return 5000

    monkeypatch.setattr(usage, "_today_total", fake_total)
    monkeypatch.setenv("DAILY_TOKEN_BUDGET", "")  # no budget
    with caplog.at_level(logging.WARNING, logger="agent"):
        asyncio.run(usage._check_budget())
    monkeypatch.setenv("DAILY_TOKEN_BUDGET", "9999999")  # under budget
    with caplog.at_level(logging.WARNING, logger="agent"):
        asyncio.run(usage._check_budget())
    assert not [r for r in caplog.records if "DAILY_TOKEN_BUDGET" in r.message]


def test_write_failure_is_swallowed(monkeypatch) -> None:
    # Unreachable DB: recording must not raise into the conversation.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:1/x")
    monkeypatch.setenv("DAILY_TOKEN_BUDGET", "0")
    asyncio.run(usage.record("writer", {"m": {"input_tokens": 1, "output_tokens": 1}}))


def test_ops_usage_endpoint_shape(monkeypatch) -> None:
    async def fake_summary(days=7):
        return {
            "rows": [
                {
                    "day": "2026-07-16",
                    "model": "openai:gpt-5.6-sol",
                    "role": "writer",
                    "calls": 3,
                    "input_tokens": 9000,
                    "output_tokens": 1200,
                },
                {
                    "day": "2026-07-16",
                    "model": "-",
                    "role": "explain_cache_hit",
                    "calls": 41,
                    "input_tokens": 0,
                    "output_tokens": 0,
                },
            ],
            "budget": 100000,
            "today_total": 10200,
            "over_budget": False,
        }

    monkeypatch.setattr(usage, "summary", fake_summary)
    client = TestClient(agent_main.app)
    body = client.get("/ops/usage?days=7").json()
    assert body["today_total"] == 10200 and body["over_budget"] is False
    roles = {row["role"] for row in body["rows"]}
    assert {"writer", "explain_cache_hit"} <= roles  # avoided spend is visible
