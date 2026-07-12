"""Agent service: POST /chat streams SSE events per graph node.

Events: profile_update, question, recommendations, message, done.
Conversation state persists per session_id via the LangGraph checkpointer
(Postgres when DATABASE_URL is set, in-memory otherwise).
"""

import asyncio
import json
import logging
import os
import traceback
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from agent import retention
from agent.graph import build_graph

logger = logging.getLogger("agent")

_graph = None
_dsn: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _dsn
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # psycopg URL (checkpointer doesn't use SQLAlchemy)
        _dsn = database_url.replace("postgresql+psycopg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(_dsn) as saver:
            await saver.setup()
            _graph = build_graph(checkpointer=saver)
            purger = asyncio.create_task(retention.retention_loop(_dsn))
            try:
                yield
            finally:
                purger.cancel()
                with suppress(asyncio.CancelledError):
                    await purger
    else:
        from langgraph.checkpoint.memory import MemorySaver

        _dsn = None
        _graph = build_graph(checkpointer=MemorySaver())
        yield


app = FastAPI(title="Insurance Recommendation Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    mode: str = Field(default="freeform", pattern="^(freeform|guided)$")


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    # recursion_limit bounds a single turn's node executions (graph depth is
    # ~8; anything beyond 15 means a wiring bug, not a long conversation).
    config = {"configurable": {"thread_id": request.session_id}, "recursion_limit": 15}
    if _dsn:  # retention bookkeeping, off the request's critical path
        asyncio.get_running_loop().create_task(
            retention.record_activity(_dsn, request.session_id)
        )
    graph_input = {
        "messages": [HumanMessage(content=request.message)],
        "mode": request.mode,
        "done": False,
    }

    async def stream():
        try:
            async for update in _graph.astream(graph_input, config, stream_mode="updates"):
                for node, payload in update.items():
                    if not payload:
                        continue
                    if "profile" in payload:
                        yield _sse("profile_update", payload["profile"])
                    if node in ("ask_question", "ask_bootstrap"):
                        question = payload.get("question") or {
                            "text": payload["messages"][0].content,
                            "input_type": "text",
                            "options": None,
                        }
                        yield _sse("question", question)
                    if node == "explain" and payload.get("recommendations"):
                        yield _sse("recommendations", payload["recommendations"])
                    if node in ("present", "explain"):
                        for message in payload.get("messages", []):
                            if isinstance(message, AIMessage):
                                yield _sse("message", {"text": message.content})
        except Exception as error:  # surface failures to the client stream
            logger.error("chat stream failed: %s\n%s", error, traceback.format_exc())
            yield _sse("error", {"detail": f"{type(error).__name__}: {error}"})
        yield _sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agent"}
