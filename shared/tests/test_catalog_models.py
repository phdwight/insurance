from decimal import Decimal

import pytest
from pydantic import ValidationError

from shared import PolicyVersion, ProductLine, TravelCoverage


def make_version(**overrides) -> PolicyVersion:
    defaults = dict(
        summary="Single-trip travel cover for Asia",
        premium_min=Decimal("500"),
        premium_max=Decimal("1500"),
        premium_frequency="single",
        coverage=TravelCoverage(
            medical_limit=Decimal("2500000"),
            destinations="asia",
            schengen_compliant=False,
            max_trip_days=30,
        ),
    )
    defaults.update(overrides)
    return PolicyVersion(**defaults)


def test_travel_version_roundtrip() -> None:
    v = make_version()
    dumped = v.model_dump(mode="json")
    restored = PolicyVersion.model_validate(dumped)
    assert restored.coverage.line == ProductLine.TRAVEL
    assert restored.coverage.medical_limit == Decimal("2500000")
    assert restored.currency == "PHP"


def test_coverage_discriminator_rejects_mismatch() -> None:
    v = make_version()
    dumped = v.model_dump(mode="json")
    dumped["coverage"]["line"] = "life"  # travel fields under life discriminator
    with pytest.raises(ValidationError):
        PolicyVersion.model_validate(dumped)


def test_defaults() -> None:
    v = make_version()
    assert v.version == 1
    assert v.eligibility.residency == ["PH"]
    assert v.exclusions == []
