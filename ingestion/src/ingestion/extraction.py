"""LLM extraction of a PolicyDraft from parsed document text.

Model tier: extractor = small (see .env.example). Without a provider key the
pipeline still works — the run is stored as 'extraction_skipped' with the raw
text, and the reviewer enters the draft manually at approval time.
"""

import os

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from ingestion.prompts import EXTRACT_POLICY_SYSTEM, PolicyDraft, policy_draft_schema

MAX_DOCUMENT_CHARS = 60_000  # keep prompts bounded for very long brochures


def _llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _model_name() -> str:
    return os.environ.get("LLM_MODEL_SMALL", "anthropic:claude-haiku-4-5")


async def extract_draft(document_text: str) -> tuple[dict | None, str, str]:
    """Returns (output, status, model): status is pending_review,
    extraction_skipped, or extraction_failed."""
    excerpt = document_text[:MAX_DOCUMENT_CHARS]
    if not _llm_available():
        return {"raw_text": excerpt}, "extraction_skipped", "none"

    try:
        extractor = init_chat_model(_model_name()).with_structured_output(
            policy_draft_schema()
        )
        result = await extractor.ainvoke(
            [("system", EXTRACT_POLICY_SYSTEM), ("human", excerpt)]
        )
    except Exception as error:
        return (
            {"error": str(error), "raw_text": excerpt},
            "extraction_failed",
            _model_name(),
        )

    try:
        draft = PolicyDraft.model_validate(result).model_dump(mode="json")
    except ValidationError:
        # Partial extraction (e.g. the insurer name wasn't stated in the
        # document): keep what the model produced so the reviewer can complete
        # it. The mandatory approval step re-validates the full PolicyDraft.
        draft = dict(result)
    return draft, "pending_review", _model_name()
