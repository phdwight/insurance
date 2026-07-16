"""Tiered model resolution for ingestion (mirrors the agent's tier slots).

Six models, two per tier; the code uses each tier's ``_1`` slot, and legacy
``LLM_MODEL`` / ``LLM_MODEL_SMALL`` stay honored so existing .env files keep
working. Resolved at call time (not import) so tests and reconfigs take effect.

Ingestion role -> tier:
  * mid   -> vision triage, intake gate, correction (capable + vision, cost-aware)
  * small -> extraction
"""

import os


def _model(*env_names: str, default: str) -> str:
    """First non-empty of the given env vars, else ``default``."""
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def large() -> str:
    return _model("LLM_MODEL_LARGE_1", "LLM_MODEL", default="anthropic:claude-opus-4-8")


def mid() -> str:
    return _model("LLM_MODEL_MID_1", "LLM_MODEL", default="anthropic:claude-sonnet-4-5")


def small() -> str:
    return _model("LLM_MODEL_SMALL_1", "LLM_MODEL_SMALL", default="anthropic:claude-haiku-4-5")
