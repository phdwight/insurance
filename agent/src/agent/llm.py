"""Provider-agnostic chat models (config via LLM_MODEL / LLM_MODEL_SMALL)."""

import os
from functools import lru_cache

from langchain.chat_models import init_chat_model

from agent.config import LLM_MODEL, LLM_MODEL_SMALL


def llm_available() -> bool:
    """Free-form extraction and explanations need at least one provider key.
    Guided mode is fully deterministic and works without any."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


@lru_cache(maxsize=2)
def get_model(size: str = "large"):
    return init_chat_model(LLM_MODEL_SMALL if size == "small" else LLM_MODEL)
