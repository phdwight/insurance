"""Agent model-tier config: the _model resolver, the 6-slot defaults, the writer
alias, and the legacy LLM_MODEL fallback. Also that get_model routes by tier."""

import importlib

import pytest

_TIER_ENV = (
    "LLM_MODEL",
    "LLM_MODEL_SMALL",
    "LLM_MODEL_LARGE_1",
    "LLM_MODEL_LARGE_2",
    "LLM_MODEL_MID_1",
    "LLM_MODEL_MID_2",
    "LLM_MODEL_SMALL_1",
    "LLM_MODEL_SMALL_2",
)


@pytest.fixture(autouse=True)
def _restore_config():
    """Reload agent.config after each test (post monkeypatch undo) so a reload
    under a doctored env never leaks tier values into another test."""
    yield
    import agent.config

    importlib.reload(agent.config)


def test_model_resolver_precedence_and_default(monkeypatch):
    from agent.config import _model

    monkeypatch.setenv("A", "first")
    monkeypatch.setenv("B", "second")
    assert _model("A", "B", default="d") == "first"
    monkeypatch.delenv("A")
    assert _model("A", "B", default="d") == "second"
    monkeypatch.delenv("B")
    assert _model("A", "B", default="d") == "d"


def test_model_resolver_skips_empty(monkeypatch):
    from agent.config import _model

    monkeypatch.setenv("A", "")
    monkeypatch.setenv("B", "second")
    assert _model("A", "B", default="d") == "second"


def test_default_tier_ladder(monkeypatch):
    for name in _TIER_ENV:
        monkeypatch.delenv(name, raising=False)
    import agent.config as cfg

    importlib.reload(cfg)
    assert cfg.LLM_MODEL_LARGE_1 == "anthropic:claude-opus-4-8"
    assert cfg.LLM_MODEL_MID_1 == "anthropic:claude-sonnet-4-5"
    assert cfg.LLM_MODEL_SMALL_1 == "anthropic:claude-haiku-4-5"
    # The writer keeps its old name, aliased to the large tier.
    assert cfg.LLM_MODEL == cfg.LLM_MODEL_LARGE_1


def test_legacy_llm_model_drives_large_and_mid(monkeypatch):
    for name in _TIER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_MODEL", "openai:gpt-5.6-sol")
    monkeypatch.setenv("LLM_MODEL_SMALL", "openai:gpt-5.6-luna")
    import agent.config as cfg

    importlib.reload(cfg)
    assert cfg.LLM_MODEL_LARGE_1 == "openai:gpt-5.6-sol"
    assert cfg.LLM_MODEL_MID_1 == "openai:gpt-5.6-sol"
    assert cfg.LLM_MODEL_SMALL_1 == "openai:gpt-5.6-luna"


def test_get_model_routes_by_tier(monkeypatch):
    from agent import llm

    captured = {}
    monkeypatch.setattr(
        llm, "chat_model", lambda model, **kw: captured.update(model=model) or model
    )
    for tier in ("large", "mid", "small"):
        llm.get_model.cache_clear()
        llm.get_model(tier)
        assert captured["model"] == llm._TIER_MODELS[tier]
    llm.get_model.cache_clear()
