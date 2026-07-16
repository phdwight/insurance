"""Operational LLM-spend ladder — the kill switch for a spend spike.

``LLM_ECONOMY`` selects how much LLM work a conversation may buy, without a
rebuild and without breaking anyone:

  * ``full`` (default)  — writer + judge panel + extractor, as designed.
  * ``lean``            — drop the judge panel. The panel only ever makes
                          output stricter, so skipping it is safe by
                          construction; explanations ship writer-only.
  * ``deterministic``   — zero LLM calls. Explanations render from verified
                          catalog fields via templates (grounded by
                          construction); profile updates use the deterministic
                          parsers only. The product stays fully usable — this
                          is the same posture as running with no LLM keys.

Read at call time so an operator can flip modes with a container env change;
an unknown value falls back to ``full`` (fail open to normal behavior, never
to silence). The mode participates in the explanation-cache key, so results
produced under a leaner mode can never be served as fully-verified ones.
"""

import os

MODES = ("full", "lean", "deterministic")


def mode() -> str:
    value = os.environ.get("LLM_ECONOMY", "full").lower()
    return value if value in MODES else "full"


def writer_enabled() -> bool:
    """May the frontier writer be called? (full and lean)"""
    return mode() != "deterministic"


def extractor_enabled() -> bool:
    """May the small extractor be called? (full and lean)"""
    return mode() != "deterministic"


def panel_enabled() -> bool:
    """May the judge panel run? (full only)"""
    return mode() == "full"
