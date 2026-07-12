"""Document text extraction.

PDFs: docling first (layout-aware — premium tables come out as structured
markdown the extractor LLM reads reliably), pypdf as the lightweight fallback
when docling is unavailable, disabled (DOCLING_ENABLED=false), or fails.
Plain text/markdown pass through. Returns (text, parser_used).
"""

import io
import logging
import os
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

logger = logging.getLogger("ingestion")

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md"}


class UnsupportedDocument(ValueError):
    pass


def docling_enabled() -> bool:
    return os.environ.get("DOCLING_ENABLED", "auto").lower() not in ("false", "0", "off")


@lru_cache(maxsize=1)
def _docling_converter():
    """Singleton — docling loads its layout/table models once per process."""
    from docling.document_converter import DocumentConverter

    return DocumentConverter()


def _docling_convert(filename: str, data: bytes) -> tuple[str | None, str | None]:
    """PDF -> (markdown, None) via docling, or (None, reason) to fall back."""
    try:
        from docling.datamodel.base_models import DocumentStream
    except ImportError:
        return None, "docling is not installed in this image (rebuild it)"
    try:
        stream = DocumentStream(name=Path(filename).name or "upload.pdf", stream=io.BytesIO(data))
        result = _docling_converter().convert(stream)
        return result.document.export_to_markdown(), None
    except Exception as error:
        logger.warning("docling conversion failed; falling back to pypdf", exc_info=True)
        return None, f"docling failed: {type(error).__name__}: {error}"


def _pypdf_convert(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text(filename: str, data: bytes) -> tuple[str, str, str | None]:
    """Returns (text, parser, note): parser is 'docling', 'pypdf', or 'text';
    note explains a docling->pypdf fallback so it is never silent."""
    note = None
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        text, parser = None, "docling"
        if docling_enabled():
            text, note = _docling_convert(filename, data)
        else:
            note = "docling disabled via DOCLING_ENABLED"
        if not (text and text.strip()):
            text, parser = _pypdf_convert(data), "pypdf"
        else:
            note = None
    elif suffix in (".txt", ".md"):
        text, parser = data.decode("utf-8", errors="replace"), "text"
    else:
        raise UnsupportedDocument(
            f"unsupported file type '{suffix}' — use one of {sorted(SUPPORTED_SUFFIXES)}"
        )

    text = text.strip()
    if not text:
        raise UnsupportedDocument(
            "no extractable text (scanned PDFs need OCR — install docling with an "
            "OCR extra, or upload a text-based PDF)"
        )
    return text, parser, note
