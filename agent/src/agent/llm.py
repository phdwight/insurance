"""Provider-agnostic chat models (config via the tiered LLM_MODEL_* slots)."""

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model

from agent.config import LLM_MODEL_LARGE_1, LLM_MODEL_MID_1, LLM_MODEL_SMALL_1

# Active model per tier. Roles ask for a tier, not a model, so swapping a slot in
# config (or its env var) re-points every role on that tier at once.
_TIER_MODELS = {
    "large": LLM_MODEL_LARGE_1,
    "mid": LLM_MODEL_MID_1,
    "small": LLM_MODEL_SMALL_1,
}


def llm_available() -> bool:
    """Free-form extraction and explanations need at least one provider key.
    Guided mode is fully deterministic and works without any."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def chat_model(model: str, **kwargs):
    """``init_chat_model`` with provider-specific fixes.

    OpenAI reasoning models (gpt-5.x) reject **function tools + reasoning_effort**
    on ``/v1/chat/completions`` — which is exactly what ``with_structured_output``
    (and any tool binding) sends. The Responses API supports both, and is OpenAI's
    current default endpoint, so we route every OpenAI model through it. Other
    providers are untouched (the flag is OpenAI-only)."""
    if model.split(":", 1)[0] == "openai":
        kwargs.setdefault("use_responses_api", True)
    return init_chat_model(model, **kwargs)


@lru_cache(maxsize=3)
def get_model(size: str = "large"):
    """A chat model for a tier: "large" (writer), "mid", or "small" (extractor)."""
    return chat_model(_TIER_MODELS.get(size, LLM_MODEL_LARGE_1))
