"""Shared models for the insurance recommender."""

from shared.catalog import (
    Coverage,
    Eligibility,
    HealthCoverage,
    Insurer,
    LifeCoverage,
    PetCoverage,
    Policy,
    PolicySearchResult,
    PolicyStatus,
    PolicyVersion,
    PremiumFrequency,
    ProductLine,
    TravelCoverage,
)
from shared.needs import NeedsProfile, merge_profiles
from shared.version import app_version, build_id

# Resolved, never hardcoded — see shared/version.py (a literal here would drift
# from the git tag the moment CI cut a release).
__version__ = app_version()

__all__ = [
    "Coverage",
    "Eligibility",
    "HealthCoverage",
    "Insurer",
    "LifeCoverage",
    "NeedsProfile",
    "PetCoverage",
    "Policy",
    "PolicySearchResult",
    "PolicyStatus",
    "PolicyVersion",
    "PremiumFrequency",
    "ProductLine",
    "TravelCoverage",
    "app_version",
    "build_id",
    "merge_profiles",
]
