"""Provider-agnostic chat models (config via LLM_MODEL / LLM_MODEL_SMALL)."""

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model

from agent.config import LLM_MODEL, LLM_MODEL_SMALL


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


@lru_cache(maxsize=2)
def get_model(size: str = "large"):
    return chat_model(LLM_MODEL_SMALL if size == "small" else LLM_MODEL)
