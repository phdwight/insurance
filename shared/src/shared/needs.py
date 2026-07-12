"""User needs profile.

There is deliberately NO static question form here: questions are derived at
runtime from the catalog — the agent asks only about attributes on which the
current candidate policies actually differ (agent/discriminators.py).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from shared.catalog import PremiumFrequency, ProductLine


class NeedsProfile(BaseModel):
    product_lines: list[ProductLine] = Field(default_factory=list)
    age: int | None = Field(default=None, ge=0, le=120)
    dependents: int | None = Field(default=None, ge=0)
    location: str | None = None
    occupation: str | None = None
    budget_amount: Decimal | None = Field(default=None, ge=0, description="PHP")
    budget_frequency: PremiumFrequency | None = None
    per_line: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Line-specific details, e.g. per_line['travel']['destination_region']",
    )
    risk_notes: list[str] = Field(
        default_factory=list,
        description="Sensitive risk factors volunteered by the user (smoker, "
        "pre-existing conditions). Collect only what's needed for matching.",
    )


def merge_profiles(base: NeedsProfile, update: NeedsProfile) -> NeedsProfile:
    """Merge newly extracted info into the existing profile.

    Never overwrites a known scalar with None; unions lists; per-line dicts
    merge key-wise with new values winning (user corrections must stick).
    """
    data = base.model_dump()
    new = update.model_dump()

    for key in ("age", "dependents", "location", "occupation",
                "budget_amount", "budget_frequency"):
        if new[key] is not None:
            data[key] = new[key]

    data["product_lines"] = list(dict.fromkeys(data["product_lines"] + new["product_lines"]))
    data["risk_notes"] = list(dict.fromkeys(data["risk_notes"] + new["risk_notes"]))

    for line, details in new["per_line"].items():
        merged = dict(data["per_line"].get(line, {}))
        merged.update({k: v for k, v in details.items() if v is not None})
        data["per_line"][line] = merged

    return NeedsProfile(**data)
