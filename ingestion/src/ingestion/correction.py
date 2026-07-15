"""Auto-correction pass.

When a reviewer approves a draft that fails validation, the large model re-reads
the document images WITH the exact error and returns a corrected draft for another
human review — capped at MAX_CORRECTION_ATTEMPTS. Reuses the vision page renderer
(pypdfium2) and the same ``policy_draft_schema`` as extraction, so the corrected
draft is contract-identical. Uses the frontier ``LLM_MODEL`` (the "large" model),
not the small extractor.
"""

import json
import logging

import anyio
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from ingestion import vision
from ingestion.prompts import CORRECT_DRAFT_SYSTEM, policy_draft_schema

logger = logging.getLogger("ingestion")

MAX_CORRECTION_ATTEMPTS = 3


def correction_enabled() -> bool:
    """On when an LLM key is present (same providers as extraction/vision)."""
    return vision._llm_available()


async def correct_draft(data: bytes, draft: dict, errors: str) -> dict | None:
    """Show the document pages + the failing draft + the validation error(s) to
    the large model and return a corrected draft dict. Returns None on any
    failure — the caller then surfaces the original error for manual fixing."""
    try:
        pages = await anyio.to_thread.run_sync(vision._render_pages, data)
        if not pages:
            return None
        provider = vision._model_name().split(":", 1)[0]
        prompt = (
            f"{CORRECT_DRAFT_SYSTEM}\n\nCURRENT DRAFT:\n"
            f"{json.dumps(draft, ensure_ascii=False, default=str)}\n\n"
            f"VALIDATION ERRORS:\n{errors}"
        )
        content: list[dict] = [{"type": "text", "text": prompt}]
        content += [vision._image_block(png, provider) for png in pages]
        model = init_chat_model(vision._model_name()).with_structured_output(
            policy_draft_schema()
        )
        result = await model.ainvoke([HumanMessage(content=content)])
        return result if isinstance(result, dict) else None
    except Exception:
        logger.warning("draft auto-correction failed", exc_info=True)
        return None
