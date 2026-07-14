"""Intake gate: one frontier-model pass over a parsed document that (1) rejects
non-insurance uploads and (2) redacts personal identifying information (PII)
before anything is extracted or stored.

Runs on the document text after parsing/vision, using the large ``LLM_MODEL``
(good judgment for classification + thorough redaction). Gated by ``INTAKE_GATE``
and the presence of an LLM key; without a key it degrades to a pass-through
(accept, no redaction) so the pipeline still works keyless in local dev.
"""

import os

from langchain.chat_models import init_chat_model

from ingestion.prompts import INTAKE_SYSTEM, DocumentIntake

INTAKE_MAX_CHARS = 60_000  # bound the prompt for very long documents


def _model_name() -> str:
    return os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-4-5")


def _llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def intake_enabled() -> bool:
    """On when an LLM key is present, unless INTAKE_GATE is explicitly off."""
    if os.environ.get("INTAKE_GATE", "auto").lower() in ("false", "0", "off", "no"):
        return False
    return _llm_available()


async def classify(document_text: str) -> DocumentIntake:
    """Classify + redact. Returns a DocumentIntake; on error, fails OPEN (accept
    the document unredacted) so a transient LLM issue never blocks ingestion —
    the mandatory human review is still the backstop."""
    excerpt = document_text[:INTAKE_MAX_CHARS]
    try:
        gate = init_chat_model(_model_name()).with_structured_output(
            DocumentIntake, method="function_calling"
        )
        return await gate.ainvoke([("system", INTAKE_SYSTEM), ("human", excerpt)])
    except Exception as error:
        return DocumentIntake(
            is_insurance=True,
            category="other",
            reason=f"intake gate error, accepted unredacted: {type(error).__name__}",
            redacted_text=None,
        )
