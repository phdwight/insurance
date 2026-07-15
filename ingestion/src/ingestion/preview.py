"""Cover-page preview: render a PDF's first page to a PNG thumbnail.

Uses pypdfium2 (already a docling dependency, so no new package) — the same
renderer vision triage uses. Rendered covers are cached to disk keyed by the
source file's name, so a brochure is rasterized once and re-served cheaply."""

import logging
from pathlib import Path

import pypdfium2 as pdfium

logger = logging.getLogger("ingestion")

COVER_SCALE = 2.0  # ~200 DPI — crisp on hi-dpi screens, still small


def render_cover(pdf_path: Path, cache_path: Path) -> Path | None:
    """Render page 1 of ``pdf_path`` to a PNG at ``cache_path`` (returned).
    Reuses the cached file if present. Returns None if the PDF can't be read."""
    if cache_path.exists():
        return cache_path
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            if len(pdf) == 0:
                return None
            page = pdf[0]
            bitmap = page.render(scale=COVER_SCALE)
            image = bitmap.to_pil()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(cache_path), format="PNG")
            bitmap.close()
            page.close()
        finally:
            pdf.close()
    except Exception:
        logger.warning("cover render failed for %s", pdf_path, exc_info=True)
        return None
    return cache_path
