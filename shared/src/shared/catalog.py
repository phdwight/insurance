"""Policy catalog models.

These mirror the `catalog` schema tables (db/migrations) and define the
per-product-line coverage shapes stored in the JSONB columns. See
docs/02-ingestion-mcp.md.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProductLine(StrEnum):
    LIFE = "life"
    HEALTH = "health"
    TRAVEL = "travel"
    PET = "pet"


class PremiumFrequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"
    SINGLE = "single"  # one-time payment (common for travel)


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Insurer(BaseModel):
    id: UUID | None = None
    name: str
    slug: str
    website: str | None = None
    ic_license_ref: str | None = Field(
        default=None, description="Philippine Insurance Commission license reference"
    )


class Eligibility(BaseModel):
    age_min: int | None = None
    age_max: int | None = None
    residency: list[str] = Field(default_factory=lambda: ["PH"])
    medical_exam_required: bool | None = None
    notes: str | None = None


# --- Per-line coverage shapes (stored in policy_versions.coverage JSONB) ---


class LifeCoverage(BaseModel):
    line: Literal[ProductLine.LIFE] = ProductLine.LIFE
    policy_type: Literal["term", "whole", "vul", "endowment"]
    face_amount_min: Decimal | None = None
    face_amount_max: Decimal | None = None
    term_years_options: list[int] = Field(default_factory=list)
    accidental_death_benefit: bool | None = None
    maturity_benefit: str | None = None
    contestability_years: int | None = None


class HealthCoverage(BaseModel):
    line: Literal[ProductLine.HEALTH] = ProductLine.HEALTH
    plan_type: Literal["hmo", "indemnity", "hospital_cash"]
    annual_limit: Decimal | None = None
    room_and_board_limit_per_day: Decimal | None = None
    inpatient: bool = True
    outpatient: bool | None = None
    emergency_coverage: bool | None = None
    preexisting_covered_after_months: int | None = Field(
        default=None, description="None = pre-existing conditions not covered"
    )


class TravelCoverage(BaseModel):
    line: Literal[ProductLine.TRAVEL] = ProductLine.TRAVEL
    medical_limit: Decimal | None = None
    trip_cancellation_limit: Decimal | None = None
    baggage_loss_limit: Decimal | None = None
    flight_delay_per_hours: int | None = None
    covid_covered: bool | None = None
    schengen_compliant: bool | None = None
    destinations: Literal["domestic", "asia", "worldwide", "worldwide_ex_us"] | None = None
    max_trip_days: int | None = None


class PetCoverage(BaseModel):
    line: Literal[ProductLine.PET] = ProductLine.PET
    species: list[Literal["dog", "cat"]] = Field(default_factory=lambda: ["dog", "cat"])
    pet_age_min_months: int | None = None
    pet_age_max_months: int | None = None
    vet_fee_annual_limit: Decimal | None = None
    accident_coverage: bool | None = None
    illness_coverage: bool | None = None
    wellness_addon_available: bool | None = None
    waiting_period_days: int | None = None


Coverage = LifeCoverage | HealthCoverage | TravelCoverage | PetCoverage


class PolicyVersion(BaseModel):
    id: UUID | None = None
    policy_id: UUID | None = None
    version: int = 1
    effective_date: date | None = None
    verified_at: datetime | None = None
    summary: str
    currency: str = "PHP"
    premium_min: Decimal | None = None
    premium_max: Decimal | None = None
    premium_frequency: PremiumFrequency | None = None
    eligibility: Eligibility = Field(default_factory=Eligibility)
    coverage: Coverage = Field(discriminator="line")
    exclusions: list[str] = Field(default_factory=list)
    riders: list[str] = Field(default_factory=list)
    extras: dict = Field(default_factory=dict)
    source_url: str | None = None


class Policy(BaseModel):
    id: UUID | None = None
    insurer: Insurer
    product_line: ProductLine
    name: str
    slug: str
    status: PolicyStatus = PolicyStatus.DRAFT
    current_version: PolicyVersion | None = None


class PolicySearchResult(BaseModel):
    """Compact shape returned by the MCP search_policies tool."""

    policy_id: UUID
    slug: str
    name: str
    insurer_name: str
    product_line: ProductLine
    summary: str
    premium_min: Decimal | None
    premium_max: Decimal | None
    premium_frequency: PremiumFrequency | None
    currency: str
    verified_at: datetime | None
    match_score: float | None = None
