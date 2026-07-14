"""Vision triage: the large model looks at a PDF's pages and either transcribes
them to Markdown itself (image-heavy / scanned docs a text parser would mangle)
or routes to docling (clean digital text + tables).

Pages are rendered with pypdfium2 (already a docling dependency), so this adds
no new packages and stays provider-agnostic via ``init_chat_model``. The model
is the frontier ``LLM_MODEL``. Any failure degrades to docling so an upload is
never lost. Enabled by default when an LLM key is present; ``VISION_TRIAGE=false``
forces every PDF straight to docling.
"""

import base64
import io
import logging
import os
import re

import anyio
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from ingestion.prompts import (
    VISION_TRANSCRIBE_SYSTEM,
    VISION_TRIAGE_SYSTEM,
    VisionTriage,
)

logger = logging.getLogger("ingestion")


def _model_name() -> str:
    return os.environ.get("LLM_MODEL", "anthropic:claude-sonnet-4-5")


def _llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def vision_enabled() -> bool:
    """On when an LLM key is present, unless VISION_TRIAGE is explicitly off."""
    if os.environ.get("VISION_TRIAGE", "auto").lower() in ("false", "0", "off", "no"):
        return False
    return _llm_available()


def _max_pages() -> int:
    return int(os.environ.get("VISION_MAX_PAGES", "8"))


def _render_pages(data: bytes) -> list[bytes]:
    """PDF bytes -> a capped list of PNG page images, downscaled to bound tokens."""
    import pypdfium2 as pdfium

    pngs: list[bytes] = []
    pdf = pdfium.PdfDocument(data)
    try:
        for i in range(min(len(pdf), _max_pages())):
            page = pdf[i]
            bitmap = page.render(scale=1.6)  # ~150 DPI — legible, not huge
            image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pngs.append(buffer.getvalue())
            bitmap.close()
            page.close()
    finally:
        pdf.close()
    return pngs


def _image_block(png: bytes, provider: str) -> dict:
    """Provider-native image content block (init_chat_model abstracts the model,
    but multimodal input format still differs between providers)."""
    b64 = base64.b64encode(png).decode()
    if provider == "openai":
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
    return {  # anthropic (and anthropic-compatible)
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": b64},
    }


def is_thin(text: str) -> bool:
    """A text parser on an image-only PDF returns mostly '<!-- image -->'
    placeholders and almost no real text — too thin to classify or extract, so
    the caller should fall back to vision transcription."""
    real = re.sub(r"<!--.*?-->", "", text or "", flags=re.DOTALL)
    return len(real.strip()) < 120


async def transcribe(filename: str, data: bytes) -> str | None:
    """Force full transcription of the PDF pages to Markdown — the recovery path
    when a text parser produced nothing usable (image-heavy PDF, no text layer).
    Returns None on failure."""
    try:
        pages = await anyio.to_thread.run_sync(_render_pages, data)
        if not pages:
            return None
        provider = _model_name().split(":", 1)[0]
        content: list[dict] = [{"type": "text", "text": VISION_TRANSCRIBE_SYSTEM}]
        content += [_image_block(png, provider) for png in pages]
        result = await init_chat_model(_model_name()).ainvoke([HumanMessage(content=content)])
        text = result.content if isinstance(result.content, str) else None
        return text if text and text.strip() else None
    except Exception:
        logger.warning("vision transcription failed", exc_info=True)
        return None


async def triage(filename: str, data: bytes) -> tuple[str | None, str, str]:
    """Returns (markdown, route, reason). markdown is set only when route ==
    'self'. On any error the route is 'docling' so parsing still proceeds."""
    try:
        pages = await anyio.to_thread.run_sync(_render_pages, data)
        if not pages:
            return None, "docling", "no rendered pages"

        provider = _model_name().split(":", 1)[0]
        content: list[dict] = [{"type": "text", "text": VISION_TRIAGE_SYSTEM}]
        content += [_image_block(png, provider) for png in pages]

        # Default structured-output method (json_schema on OpenAI, tools on
        # Anthropic) — forcing function_calling breaks OpenAI reasoning models.
        model = init_chat_model(_model_name()).with_structured_output(VisionTriage)
        result: VisionTriage = await model.ainvoke([HumanMessage(content=content)])

        if result.route == "self" and result.markdown and result.markdown.strip():
            return result.markdown, "self", result.reason
        return None, "docling", result.reason or "routed to docling"
    except Exception:
        logger.warning("vision triage failed; routing to docling", exc_info=True)
        return None, "docling", "vision triage error"
