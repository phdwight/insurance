"""Ingestion model-tier resolution: the 6-slot roster, defaults, and the legacy
LLM_MODEL / LLM_MODEL_SMALL fallback that keeps existing .env files working."""

from ingestion import models

_ALL = (
    "LLM_MODEL",
    "LLM_MODEL_SMALL",
    "LLM_MODEL_LARGE_1",
    "LLM_MODEL_MID_1",
    "LLM_MODEL_SMALL_1",
)


def _clear(monkeypatch):
    for name in _ALL:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_the_three_tiers(monkeypatch):
    _clear(monkeypatch)
    assert models.large() == "anthropic:claude-opus-4-8"
    assert models.mid() == "anthropic:claude-sonnet-4-5"
    assert models.small() == "anthropic:claude-haiku-4-5"


def test_tier_slot_wins_over_default_and_legacy(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "legacy:writer")
    monkeypatch.setenv("LLM_MODEL_MID_1", "openai:gpt-4o-mini")
    assert models.mid() == "openai:gpt-4o-mini"


def test_legacy_llm_model_is_the_large_and_mid_fallback(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "openai:gpt-5.6-sol")
    # No _1 slots set → mid and large both fall back to the legacy writer var.
    assert models.mid() == "openai:gpt-5.6-sol"
    assert models.large() == "openai:gpt-5.6-sol"


def test_legacy_small_is_the_small_fallback(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_MODEL_SMALL", "openai:gpt-5.6-luna")
    assert models.small() == "openai:gpt-5.6-luna"


def test_empty_string_slot_is_skipped(monkeypatch):
    # docker-compose forwards the tier vars as empty strings when unset; those
    # must not shadow the legacy fallback.
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_MODEL_MID_1", "")
    monkeypatch.setenv("LLM_MODEL", "openai:gpt-5.6-sol")
    assert models.mid() == "openai:gpt-5.6-sol"
