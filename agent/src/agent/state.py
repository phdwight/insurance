from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["freeform", "guided"]
    profile: dict[str, Any]  # NeedsProfile.model_dump()
    pending_question: str | None
    pending_disc: str | None  # discriminator id (or "budget") being asked
    question: dict | None  # {text, input_type, options} for the UI
    asked: list[str]  # discriminator ids already used this session
    questions_asked: int
    turn_count: int  # total user turns (hard session cap)
    bootstrap_count: int  # times we've asked "what to protect" (capped)
    candidates: dict[str, list[dict[str, Any]]]  # line -> search results
    recommendations: dict[str, list[dict[str, Any]]]  # line -> verified + explained
    expl_cache_key: str | None  # content hash of (models, prompts, profile, facts)
    explanations_cached: bool  # hit — writer & judge panel were skipped this turn
    done: bool
