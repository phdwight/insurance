"""Provider-agnostic LLM configuration.

Models are selected by env var so the provider is a deployment decision:
    LLM_MODEL="anthropic:claude-sonnet-4-5"   or   "openai:gpt-4o"
    LLM_MODEL_SMALL="anthropic:claude-haiku-4-5"  (extraction/routing)

Loaded lazily via langchain's init_chat_model in Phase 2.
"""

import os

LLM_MODEL = os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-4-5")
LLM_MODEL_SMALL = os.environ.get("LLM_MODEL_SMALL", "anthropic:claude-haiku-4-5")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8002/mcp")
