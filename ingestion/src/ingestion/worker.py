"""Durable background worker for the ingestion queue.

POST /documents enqueues an extraction run as 'queued' and returns immediately,
so slow parsing (and any future OCR) never trips a proxy timeout. This worker
claims runs from the catalog (Postgres FOR UPDATE SKIP LOCKED — safe to run
several workers), reads the stored file, parses + extracts, and finalizes.

Because the queue lives in the database, a restart never loses a job: a run a
crashed worker abandoned mid-parse is requeued by the stale sweep on startup.
Run it as its own process: `python -m ingestion.worker`.
"""

import asyncio
import logging
import os
from pathlib import Path

import anyio

from ingestion import extraction, parsing, repository

logger = logging.getLogger("ingestion")


def poll_interval_seconds() -> float:
    return float(os.environ.get("WORKER_POLL_SECONDS", "2"))


def stale_after_seconds() -> int:
    # Generous: a large or scanned PDF parse legitimately takes minutes, so only
    # reclaim runs a crashed worker truly abandoned (default 30 min).
    return int(os.environ.get("WORKER_STALE_SECONDS", "1800"))


async def _process(run_id: str, document_id: str, file_ref: str | None) -> None:
    """Parse + extract a claimed run and finalize it. A parse failure is
    recorded as 'failed' with the reason — never lost, visible in the queue."""
    try:
        if not file_ref or not Path(file_ref).exists():
            raise FileNotFoundError(f"stored file missing: {file_ref}")
        data = await anyio.to_thread.run_sync(Path(file_ref).read_bytes)
        # docling/pypdf are blocking and CPU-bound — keep them off the loop.
        document_text, parser, parser_note = await anyio.to_thread.run_sync(
            parsing.extract_text, Path(file_ref).name, data
        )
    except parsing.UnsupportedDocument as error:
        repository.update_parse_status(document_id, "parse_failed")
        repository.finalize_extraction_run(run_id, "none", {"error": str(error)}, "failed")
        return
    except Exception as error:  # missing file / parser blow-up — surface, don't crash
        logger.exception("parsing failed for run %s", run_id)
        repository.update_parse_status(document_id, "parse_failed")
        repository.finalize_extraction_run(
            run_id, "none", {"error": f"{type(error).__name__}: {error}"}, "failed"
        )
        return

    # Fold parser, size, and any docling->pypdf fallback reason into parse_status
    # so the fallback stays visible in the reviewer UI.
    parse_status = f"parsed:{parser} ({len(document_text)} chars)"
    if parser_note:
        parse_status += f" — ⚠ {parser_note}"
    repository.update_parse_status(document_id, parse_status)

    output, status, model = await extraction.extract_draft(document_text)
    repository.finalize_extraction_run(run_id, model, output, status)


async def process_one() -> bool:
    """Claim and process a single queued run. Returns False when the queue is
    empty. Exposed so tests can drive the worker deterministically."""
    claim = repository.claim_next_run()
    if claim is None:
        return False
    logger.info("processing extraction run %s", claim["id"])
    await _process(claim["id"], claim["source_document_id"], claim.get("file_ref"))
    return True


async def run_forever() -> None:
    reclaimed = repository.reclaim_stale_runs(stale_after_seconds())
    if reclaimed:
        logger.info("requeued %d stale run(s) on startup", reclaimed)
    logger.info("ingestion worker started; polling every %ss", poll_interval_seconds())
    while True:
        try:
            worked = await process_one()
        except Exception:  # one bad job must never kill the worker
            logger.exception("worker iteration failed; continuing")
            worked = False
        if not worked:
            await asyncio.sleep(poll_interval_seconds())


def main() -> None:
    # Match the uvicorn services' timestamped log shape (see log_config.yaml).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
