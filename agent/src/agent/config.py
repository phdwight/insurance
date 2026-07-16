"""Provider-agnostic LLM configuration.

Models are selected by env var so the provider is a deployment decision:
    anthropic:claude-opus-4-8   or   openai:gpt-4o

Six models organised into three tiers, two per tier — a roster you choose from.
The code uses each tier's ``_1`` slot; the ``_2`` slot is a vetted alternate you
can swap into ``_1``. Legacy ``LLM_MODEL`` / ``LLM_MODEL_SMALL`` are still honored
(as the large/small fallback) so existing .env files keep working unchanged.

Role -> tier (this package): writer = large, extractor = small. Ingestion wires
vision/intake/correction to mid and extraction to small (see ingestion/models.py).

Loaded lazily via langchain's init_chat_model.
"""

import os


def _model(*env_names: str, default: str) -> str:
    """First non-empty of the given env vars, else ``default``."""
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return value
    return default


# --- Tier roster (6 slots) ------------------------------------------------
# _1 is the active model for its tier; _2 is a documented alternate. The legacy
# names are consulted before the hard default so an old .env keeps its models.
LLM_MODEL_LARGE_1 = _model(
    "LLM_MODEL_LARGE_1", "LLM_MODEL", default="anthropic:claude-opus-4-8"
)
LLM_MODEL_LARGE_2 = _model("LLM_MODEL_LARGE_2", default="openai:gpt-4o")
LLM_MODEL_MID_1 = _model(
    "LLM_MODEL_MID_1", "LLM_MODEL", default="anthropic:claude-sonnet-4-5"
)
LLM_MODEL_MID_2 = _model("LLM_MODEL_MID_2", default="openai:gpt-4o-mini")
LLM_MODEL_SMALL_1 = _model(
    "LLM_MODEL_SMALL_1", "LLM_MODEL_SMALL", default="anthropic:claude-haiku-4-5"
)
LLM_MODEL_SMALL_2 = _model("LLM_MODEL_SMALL_2", default="openai:gpt-4o-mini")

# --- Active model per tier (what roles read) ------------------------------
LLM_MODEL_LARGE = LLM_MODEL_LARGE_1
LLM_MODEL_MID = LLM_MODEL_MID_1
LLM_MODEL_SMALL = LLM_MODEL_SMALL_1
# Back-compat alias: the writer's model kept its old name.
LLM_MODEL = LLM_MODEL_LARGE_1

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8002/mcp")
