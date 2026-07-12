"""rank_and_verify guardrail: pure functions, no LLM, no I/O.

Every recommendation must survive programmatic checks against the actual
policy record fetched from the catalog. Anything the data can't support is
dropped or flagged — this is the anti-hallucination layer.
"""

from typing import Any

from shared import NeedsProfile

# Rough multipliers to compare a user's budget with a policy premium when
# frequencies differ (both normalized to monthly).
_TO_MONTHLY = {
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "semi_annual": 1 / 6,
    "annual": 1 / 12,
    "single": None,  # one-time; not comparable to a recurring budget
}


def _monthly(amount: float | None, frequency: str | None) -> float | None:
    if amount is None or frequency is None:
        return None
    factor = _TO_MONTHLY.get(frequency)
    return None if factor is None else float(amount) * factor


def check_policy(policy: dict[str, Any], profile: NeedsProfile) -> dict[str, Any]:
    """Return verification result: {ok, violations[], verified_facts{}}."""
    violations: list[str] = []
    facts: dict[str, Any] = {
        "slug": policy.get("slug"),
        "name": policy.get("name"),
        "insurer_name": policy.get("insurer_name"),
        "premium_min": policy.get("premium_min"),
        "premium_max": policy.get("premium_max"),
        "premium_frequency": policy.get("premium_frequency"),
        "currency": policy.get("currency"),
        "verified_at": policy.get("verified_at"),
        "source_url": policy.get("source_url"),
        "coverage": policy.get("coverage"),
        "exclusions": policy.get("exclusions"),
        "eligibility": policy.get("eligibility"),
        "summary": policy.get("summary"),
    }

    eligibility = policy.get("eligibility") or {}
    if profile.age is not None:
        age_min = eligibility.get("age_min")
        age_max = eligibility.get("age_max")
        if age_min is not None and profile.age < age_min:
            violations.append(f"age {profile.age} below minimum {age_min}")
        if age_max is not None and profile.age > age_max:
            violations.append(f"age {profile.age} above maximum {age_max}")

    budget_monthly = _monthly(
        float(profile.budget_amount) if profile.budget_amount is not None else None,
        profile.budget_frequency.value if profile.budget_frequency else "monthly",
    )
    premium_monthly = _monthly(policy.get("premium_min"), policy.get("premium_frequency"))
    if budget_monthly is not None and premium_monthly is not None:
        if premium_monthly > budget_monthly:
            violations.append(
                f"minimum premium {policy.get('premium_min')} "
                f"{policy.get('premium_frequency')} exceeds budget"
            )

    return {"ok": not violations, "violations": violations, "verified_facts": facts}


def verify_candidates(
    candidates: list[dict[str, Any]], profile: NeedsProfile, keep: int = 3
) -> list[dict[str, Any]]:
    """Filter candidates through check_policy; keep at most `keep` passing."""
    verified = []
    for candidate in candidates:
        result = check_policy(candidate, profile)
        if result["ok"]:
            verified.append(result["verified_facts"])
        if len(verified) >= keep:
            break
    return verified
