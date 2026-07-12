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

__version__ = "0.1.0"

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
    "merge_profiles",
]
