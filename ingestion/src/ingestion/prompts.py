"""Ingestion LLM prompts and structured-output contracts."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, get_args

from pydantic import BaseModel, field_validator, model_validator

from shared import (
    HealthCoverage,
    LifeCoverage,
    PetCoverage,
    PolicyVersion,
    ProductLine,
    TravelCoverage,
)

EXTRACT_POLICY_SYSTEM = """You extract insurance policy facts from a public \
brochure or product document into a structured draft for HUMAN REVIEW.
Rules:
- Record ONLY what the document states. NEVER guess, infer, or fill gaps;
  leave fields null when the document doesn't say.
- insurer_name: the insurance company's official name exactly as printed in
  the document (letterhead, footer, or regulatory line).
- Amounts are PHP unless the document explicitly states another currency.
- Tables usually hold premiums, limits, and age bands — read them carefully.
- summary: 2-4 factual sentences a comparison shopper would need.
- exclusions/riders: short verbatim-faithful phrases from the document.
- Structure matters: summary, premiums, currency, riders, exclusions, extras,
  eligibility, and dates are TOP-LEVEL fields. The `coverage` object holds ONLY
  line-specific fields (for life: policy_type, face amounts, maturity benefit,
  term years) — never put summary or premiums inside coverage.
- The draft will be reviewed and corrected by a human before publication;
  when unsure, prefer null over a plausible-looking value."""


CORRECT_DRAFT_SYSTEM = """A human tried to approve an extracted insurance policy \
draft and it FAILED VALIDATION. You are shown the source document's pages (as \
images), the current draft (JSON), and the exact validation error(s).

Re-read the document and fix the draft so it passes. Rules:
- The document images are the ground truth. Look at them to find the correct value.
- Fix ONLY what the error(s) point to; leave every other field exactly as-is.
- A common cause: a descriptive phrase landed in a field that must be a number,
  a date, or a specific enum (e.g. "110% of the single premium" in a numeric
  face-amount field). Put the descriptive text where it belongs (summary,
  maturity_benefit, extras…) and set the strict field to the real number the
  document states, or null if the document gives none — NEVER invent one.
- Keep amounts/dates as printed in the document; don't guess.
Return the FULL corrected draft."""


def _amount_field_names() -> frozenset[str]:
    """Every ``Decimal`` field across the policy + coverage models, derived from
    the schema so newly added money fields are covered automatically."""
    models = (PolicyVersion, LifeCoverage, HealthCoverage, TravelCoverage, PetCoverage)
    return frozenset(
        name
        for model in models
        for name, field in model.model_fields.items()
        if field.annotation is Decimal or Decimal in get_args(field.annotation)
    )


AMOUNT_FIELDS = _amount_field_names()


def _is_blank(value: object) -> bool:
    """Missing or empty — a value we can safely overwrite with a hoisted one."""
    return value is None or value == "" or value == [] or value == {}
_AMOUNT_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_AMOUNT_PATTERN = re.compile(r"([\d.]+)([kmb])?", re.IGNORECASE)
_CURRENCY_NOISE = re.compile(r"(?i)php|usd|eur|gbp|[₱$€£,_\s]")


def normalize_amount(value: object) -> object:
    """Accept money as printed in brochures/schedules — ``PHP 3,000,000``,
    ``₱2.5M``, ``P3,000,000.00`` — by stripping currency noise and thousands
    separators and expanding an explicit ``K``/``M``/``B`` suffix. Non-strings
    pass through untouched; anything unrecognised is returned as-is so Pydantic
    still raises its normal, clear error instead of silently guessing."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return None
    cleaned = _CURRENCY_NOISE.sub("", text)
    cleaned = re.sub(r"(?i)^p(?=[\d.])", "", cleaned)  # leading peso "P3,000,000"
    match = _AMOUNT_PATTERN.fullmatch(cleaned)
    if not match:
        return value
    digits, suffix = match.group(1), match.group(2)
    try:
        number = Decimal(digits)
    except InvalidOperation:
        return value
    if suffix:
        number *= _AMOUNT_MULTIPLIERS[suffix.lower()]
    if number == number.to_integral_value():
        number = number.to_integral_value()
    return format(number, "f")


class PolicyDraft(PolicyVersion):
    """PolicyVersion fields plus identity — what a reviewer approves.

    insurer_name comes FROM the document (extracted, then human-confirmed);
    publishing creates the insurer if it isn't in the catalog yet.
    """

    name: str
    product_line: ProductLine
    insurer_name: str

    @model_validator(mode="before")
    @classmethod
    def _normalize_document_formats(cls, data: object) -> object:
        """PDFs vary wildly in how they print money; normalize amount fields
        (top-level premiums and nested coverage limits) before validation so a
        reviewer pasting ``PHP 3,000,000`` doesn't trip a hard 422."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        coverage = data.get("coverage")
        if isinstance(coverage, dict):
            coverage = dict(coverage)
            # Small extractors sometimes file top-level policy facts (summary,
            # riders, premiums…) under coverage; the coverage models don't define
            # them, so Pydantic would drop them and a required top-level field
            # (e.g. summary) would silently go missing. Lift each back out when
            # the top level doesn't already carry a real value.
            for name in HOISTABLE_FIELDS & coverage.keys():
                if _is_blank(data.get(name)):
                    data[name] = coverage.pop(name)
            for name in AMOUNT_FIELDS & coverage.keys():
                coverage[name] = normalize_amount(coverage[name])
            data["coverage"] = coverage
        for name in AMOUNT_FIELDS & data.keys():
            data[name] = normalize_amount(data[name])
        return data

    @field_validator("insurer_name", mode="before")
    @classmethod
    def _reject_placeholder_insurer(cls, value: object) -> object:
        """The insurer is required to publish (publish get-or-creates it), so a
        null-ish placeholder must never pass as a real name. Strip it and reject
        'null'/'none'/'n/a'/'unknown' so approval forces a real insurer. A true
        None falls through to the normal required-field error (partial draft →
        human review)."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() in {"", "null", "none", "n/a", "na", "undefined", "unknown"}:
                raise ValueError(
                    "insurer_name is missing — enter the insurer exactly as "
                    "printed in the document"
                )
            return stripped
        return value

    @field_validator("effective_date", mode="before")
    @classmethod
    def _parse_document_date(cls, value: object) -> object:
        """Reviewers copy dates as printed in the brochure (e.g. ``06-Apr-2025``);
        accept the day-month-name forms these documents use alongside ISO."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
        for fmt in ("%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return value  # unrecognised -> let Pydantic raise its clear date error

    @model_validator(mode="after")
    def coverage_matches_product_line(self) -> PolicyDraft:
        if self.coverage.line != self.product_line:
            raise ValueError(
                f"coverage is for '{self.coverage.line}' but the draft's "
                f"product_line is '{self.product_line}'"
            )
        return self


def _oneof_to_anyof(node: object) -> None:
    """Rewrite JSON-Schema ``oneOf`` to ``anyOf`` in place, dropping the
    ``discriminator`` keyword alongside it."""
    if isinstance(node, dict):
        if "oneOf" in node:
            node["anyOf"] = node.pop("oneOf")
        node.pop("discriminator", None)
        for value in node.values():
            _oneof_to_anyof(value)
    elif isinstance(node, list):
        for item in node:
            _oneof_to_anyof(item)


# Identity/versioning/verification fields the database owns — the extractor must
# never see them, or it fills UUID slots with brochure reference numbers.
SERVER_MANAGED_FIELDS = ("id", "policy_id", "version", "verified_at")


def _hoistable_field_names() -> frozenset[str]:
    """Top-level ``PolicyVersion`` fields that are never a key of any coverage
    variant. Small extractors sometimes file these (summary, riders, premiums…)
    inside ``coverage``; the coverage models don't define them, so Pydantic would
    drop them and a required top-level field (e.g. summary) would silently go
    missing. Derived from the schema, so a new top-level field is covered too."""
    coverage_fields: set[str] = set()
    for model in (LifeCoverage, HealthCoverage, TravelCoverage, PetCoverage):
        coverage_fields |= set(model.model_fields)
    top = set(PolicyVersion.model_fields) - {"coverage"}
    return frozenset(top - coverage_fields - set(SERVER_MANAGED_FIELDS))


HOISTABLE_FIELDS = _hoistable_field_names()


def policy_draft_schema() -> dict:
    """OpenAI structured output rejects the ``oneOf`` that Pydantic emits for
    the discriminated ``coverage`` union; rewrite it to the supported ``anyOf``
    form. The ``line`` Literal still drives validation when the returned dict is
    re-parsed through ``PolicyDraft``. Server-managed fields are dropped so the
    model only extracts brochure facts."""
    schema = PolicyDraft.model_json_schema()
    _oneof_to_anyof(schema)
    properties = schema.get("properties", {})
    for field in SERVER_MANAGED_FIELDS:
        properties.pop(field, None)
    if "required" in schema:
        schema["required"] = [
            name for name in schema["required"] if name not in SERVER_MANAGED_FIELDS
        ]
    return schema


# --- Vision triage (large model looks at the PDF pages and routes) -----------

VISION_TRIAGE_SYSTEM = """You are triaging an insurance policy PDF for an \
extraction pipeline. You are shown images of its pages.

Decide how the document should be turned into text:
- route "docling": the pages are mostly selectable text and tables that a
  layout-aware PDF parser reads accurately. Prefer this for normal digital
  brochures — it is cheaper and more precise. Leave markdown empty.
- route "self": the pages are image-heavy, scanned, or have complex visual
  layout/tables a text parser would mangle or miss. Then YOU transcribe the
  document to clean, faithful Markdown: preserve tables as Markdown tables, and
  keep headings, premiums, coverage limits, age bands, and exclusions exactly as
  shown. Do NOT summarize, infer, or omit content.

Return the route, a one-line reason, and — only for "self" — the full Markdown."""


class VisionTriage(BaseModel):
    """Router output for VISION_TRIAGE_SYSTEM: how to turn the PDF into text.
    ``markdown`` is the full transcription, populated only when route == 'self'."""

    route: Literal["self", "docling"]
    reason: str
    markdown: str | None = None


# --- Intake gate: classify (reject non-insurance) + redact PII ---------------

INTAKE_SYSTEM = """You are the intake gate for an insurance policy catalog. You \
are given the text of a document a user uploaded.

1. Decide if it is an insurance document — a policy, brochure, product summary,
   schedule of benefits, certificate, or similar from an insurer. Set
   is_insurance. If it is NOT insurance-related (a resume, invoice, ID, receipt,
   or unrelated PDF), set is_insurance=false, give a one-line reason, and stop
   (leave redacted_text empty).

2. If it IS insurance-related:
   - category: brochure, product_summary, policy_contract, or other.
   - redacted_text: return the FULL document text with every piece of personal
     identifying information (PII) removed — the policyholder's/insured's name,
     address, phone, email, birth date, and any government / policy / certificate
     / account / reference numbers and signatures. Replace each with [REDACTED].
     KEEP all product facts: plan/product name, the INSURER's company name,
     premiums, coverage limits, age bands, exclusions, and riders. Do not
     summarize or drop product content — only redact PII."""


class DocumentIntake(BaseModel):
    """Intake-gate output (see INTAKE_SYSTEM). redacted_text is the full document
    with PII removed, populated only when is_insurance is true."""

    is_insurance: bool
    category: Literal["brochure", "product_summary", "policy_contract", "other"]
    reason: str
    redacted_text: str | None = None


# --- Vision transcription (recovery when a text parser yields nothing) --------

VISION_TRANSCRIBE_SYSTEM = """Transcribe this document's pages to clean, faithful \
Markdown. Preserve tables as Markdown tables and keep every heading, product
name, premium, coverage limit, benefit, age band, and exclusion exactly as
shown. Do not summarize, infer, or omit content."""
