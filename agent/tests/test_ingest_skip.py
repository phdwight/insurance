"""Deterministic-parse-first extraction (token economy phase 2).

In freeform mode the extractor LLM used to run on every turn — including chip
taps and bare-number answers the pending question's own parser already handled.
Those must now skip the LLM entirely; any message carrying MORE than the direct
answer (frequency words, risk notes, multi-line asks) must still extract."""

import asyncio

from agent import nodes

AGE_Q = "*.age"
TYPE_Q = "life.policy_type"


def run_ingest(monkeypatch, text: str, pending: str | None, mode: str = "freeform"):
    """Run the ingest node with a counting fake extractor; returns (update, calls)."""
    calls: list[str] = []

    async def fake_extract(profile, message):
        calls.append(message)
        return profile

    monkeypatch.setattr(nodes, "llm_available", lambda: True)
    monkeypatch.setattr(nodes, "_extract_with_llm", fake_extract)

    from langchain_core.messages import HumanMessage

    state = {
        "messages": [HumanMessage(content=text)],
        "mode": mode,
        "profile": {"product_lines": ["life"]} if pending else {},
        "pending_disc": pending,
    }
    return asyncio.run(nodes.ingest(state)), calls


def test_chip_tap_skips_extractor(monkeypatch) -> None:
    update, calls = run_ingest(monkeypatch, "Term", pending=TYPE_Q)
    assert calls == []  # exact choice option: nothing left to extract
    assert update["profile"]["per_line"]["life"]["policy_type"] == "term"


def test_bare_number_age_skips_extractor(monkeypatch) -> None:
    update, calls = run_ingest(monkeypatch, "35", pending=AGE_Q)
    assert calls == []
    assert update["profile"]["age"] == 35


def test_bare_budget_with_currency_noise_skips(monkeypatch) -> None:
    update, calls = run_ingest(monkeypatch, "₱3,000", pending="budget")
    assert calls == []
    assert update["profile"]["budget_amount"] == 3000


def test_answer_with_extra_signal_still_extracts(monkeypatch) -> None:
    # The parser consumes "35", but "and I smoke" is a risk note only the
    # extractor can capture — the LLM must still run.
    update, calls = run_ingest(monkeypatch, "35, and I smoke", pending=AGE_Q)
    assert len(calls) == 1
    assert update["profile"]["age"] == 35  # deterministic parse still applied


def test_budget_with_frequency_word_still_extracts(monkeypatch) -> None:
    # "monthly" is information the budget parser drops (amount only) — extract.
    _, calls = run_ingest(monkeypatch, "3000 monthly", pending="budget")
    assert len(calls) == 1


def test_short_line_pick_skips_extractor(monkeypatch) -> None:
    # Bootstrap chip: the message is just a product line.
    update, calls = run_ingest(monkeypatch, "Life", pending=None)
    assert calls == []
    assert update["profile"]["product_lines"] == ["life"]


def test_rich_first_message_still_extracts(monkeypatch) -> None:
    _, calls = run_ingest(monkeypatch, "I want life insurance for my father", pending=None)
    assert len(calls) == 1


def test_unparsed_guided_answer_still_rescued_by_llm(monkeypatch) -> None:
    # Guided mode's LLM rescue for answers the parser can't read is unchanged.
    _, calls = run_ingest(
        monkeypatch, "somewhere around mid-thirties", pending=AGE_Q, mode="guided"
    )
    assert len(calls) == 1
