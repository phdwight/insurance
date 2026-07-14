"""Unit tests for the LLM extraction contract. The structured-output schema
never exposes database-managed fields (so the model can't drop a brochure
reference number into a UUID slot), and a partial draft — e.g. the insurer name
isn't stated in the document — still reaches human review instead of being
discarded as an empty template."""

import asyncio
from datetime import date
from decimal import Decimal

import ingestion.extraction as extraction
import pytest
from ingestion.prompts import SERVER_MANAGED_FIELDS, PolicyDraft, policy_draft_schema
from pydantic import ValidationError

FULL_DRAFT = {
    "name": "Demo Voyager",
    "insurer_name": "Byahero Travel Insurance Co.",
    "product_line": "travel",
    "summary": "Single-trip travel cover.",
    "premium_min": "900",
    "coverage": {"line": "travel", "medical_limit": "3000000"},
}


class _FakeStructured:
    def __init__(self, result: dict):
        self._result = result

    async def ainvoke(self, _messages):
        return self._result


class _FakeModel:
    def __init__(self, result: dict):
        self._result = result

    def with_structured_output(self, schema):
        # The schema handed to the provider must be the sanitised one.
        assert not set(schema["properties"]) & set(SERVER_MANAGED_FIELDS)
        return _FakeStructured(self._result)


def _extract(monkeypatch, result: dict):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(extraction, "init_chat_model", lambda _name: _FakeModel(result))
    return asyncio.run(extraction.extract_draft("some brochure text"))


def test_schema_hides_server_managed_fields() -> None:
    props = policy_draft_schema()["properties"]
    for field in SERVER_MANAGED_FIELDS:
        assert field not in props
    assert "insurer_name" in props  # still extracted (and encouraged)


def test_full_draft_is_normalised_and_pending_review(monkeypatch) -> None:
    output, status, _model = _extract(monkeypatch, dict(FULL_DRAFT))
    assert status == "pending_review"
    assert output["insurer_name"] == "Byahero Travel Insurance Co."
    assert output["coverage"]["line"] == "travel"


def test_partial_draft_missing_insurer_still_reaches_review(monkeypatch) -> None:
    output, status, _model = _extract(monkeypatch, {**FULL_DRAFT, "insurer_name": None})
    # A missing insurer is the reviewer's job to fill — not a hard failure.
    assert status == "pending_review"
    assert output["insurer_name"] is None
    assert output["name"] == "Demo Voyager"


def test_provider_error_is_captured_as_extraction_failed(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class _BoomModel:
        def with_structured_output(self, _schema):
            raise RuntimeError("boom: response_format oneOf not permitted")

    monkeypatch.setattr(extraction, "init_chat_model", lambda _name: _BoomModel())
    output, status, _model = asyncio.run(extraction.extract_draft("brochure text"))
    assert status == "extraction_failed"
    assert "boom" in output["error"]
    assert output["raw_text"] == "brochure text"


def test_effective_date_accepts_brochure_format() -> None:
    # Reviewers copy dates as printed in the source document.
    draft = PolicyDraft.model_validate({**FULL_DRAFT, "effective_date": "06-Apr-2025"})
    assert draft.effective_date == date(2025, 4, 6)


def test_effective_date_still_accepts_iso_and_blank() -> None:
    iso = PolicyDraft.model_validate({**FULL_DRAFT, "effective_date": "2025-04-06"})
    assert iso.effective_date == date(2025, 4, 6)
    blank = PolicyDraft.model_validate({**FULL_DRAFT, "effective_date": "  "})
    assert blank.effective_date is None


def test_amounts_accept_brochure_formatting() -> None:
    # Premiums and nested coverage limits copied verbatim from a PDF.
    draft = PolicyDraft.model_validate({
        **FULL_DRAFT,
        "premium_min": "PHP 900",
        "premium_max": "1,200.00",
        "coverage": {
            "line": "travel",
            "medical_limit": "₱2.5M",
            "trip_cancellation_limit": "PHP 50,000",
            "baggage_loss_limit": "P30,000",
        },
    })
    assert draft.premium_min == Decimal("900")
    assert draft.premium_max == Decimal("1200")
    assert draft.coverage.medical_limit == Decimal("2500000")
    assert draft.coverage.trip_cancellation_limit == Decimal("50000")
    assert draft.coverage.baggage_loss_limit == Decimal("30000")


def test_misplaced_top_level_fields_are_hoisted_from_coverage() -> None:
    # Small extractors sometimes nest summary/riders/premiums/extras under
    # coverage (seen on a real Sun Life brochure); the coverage model would drop
    # them, losing the required top-level summary. They must be lifted back out.
    draft = PolicyDraft.model_validate({
        "name": "Sun Acceler8",
        "insurer_name": "Sun Life of Canada (Philippines), Inc.",
        "product_line": "life",
        "coverage": {
            "line": "life",
            "policy_type": "endowment",
            "maturity_benefit": "102% of Face Amount at year 20.",
            "summary": "A 20-year endowment plan with increasing coverage.",
            "premium_min": "PHP 12,000",
            "riders": ["Accident and disability riders."],
            "extras": {"bonus": "Special bonus after eight years."},
        },
    })
    assert draft.summary == "A 20-year endowment plan with increasing coverage."
    assert draft.premium_min == Decimal("12000")  # hoisted, then amount-normalized
    assert draft.riders == ["Accident and disability riders."]
    assert draft.extras == {"bonus": "Special bonus after eight years."}
    # coverage keeps only its own line-specific fields
    assert draft.coverage.policy_type == "endowment"
    assert not hasattr(draft.coverage, "summary")


def test_hoist_never_overwrites_a_real_top_level_value() -> None:
    # A genuine top-level value wins over a stray nested duplicate.
    draft = PolicyDraft.model_validate({
        **FULL_DRAFT,
        "summary": "Top-level summary wins.",
        "coverage": {
            "line": "travel",
            "medical_limit": "3000000",
            "summary": "nested duplicate that must be ignored",
        },
    })
    assert draft.summary == "Top-level summary wins."


def test_unparseable_amount_still_raises() -> None:
    # Genuinely bad input is not silently coerced — Pydantic surfaces the error.
    with pytest.raises(ValidationError):
        PolicyDraft.model_validate({**FULL_DRAFT, "premium_min": "ask agent"})
