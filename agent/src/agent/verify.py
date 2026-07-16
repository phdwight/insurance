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


def deterministic_reasons(policy: dict[str, Any], profile: NeedsProfile) -> list[dict[str, Any]]:
    """Template-rendered match/gap reasons from verified fields only — the
    zero-LLM explanation path (no provider key, or LLM_ECONOMY=deterministic).

    Honest by construction: every number and attribute comes straight from the
    policy record or the user's own answers, and anything the user asked about
    that the policy doesn't state becomes a ``gap`` — the same contract the
    writer is held to, minus the prose."""
    from agent import prompts

    reasons: list[dict[str, Any]] = []
    eligibility = policy.get("eligibility") or {}
    coverage = policy.get("coverage") or {}

    age_min, age_max = eligibility.get("age_min"), eligibility.get("age_max")
    if profile.age is not None and age_min is not None and age_max is not None:
        reasons.append(
            {
                "text": prompts.DET_REASON_AGE.format(
                    age=profile.age, age_min=age_min, age_max=age_max
                ),
                "kind": "match",
            }
        )

    budget = float(profile.budget_amount) if profile.budget_amount is not None else None
    frequency = policy.get("premium_frequency")
    budget_monthly = _monthly(
        budget, profile.budget_frequency.value if profile.budget_frequency else "monthly"
    )
    premium_monthly = _monthly(policy.get("premium_min"), frequency)
    if (
        budget_monthly is not None
        and premium_monthly is not None
        and premium_monthly <= budget_monthly
    ):
        reasons.append(
            {
                "text": prompts.DET_REASON_BUDGET.format(
                    premium=float(policy["premium_min"]),
                    frequency=prompts.FREQUENCY_LABELS.get(frequency, frequency),
                    budget=budget,
                ),
                "kind": "match",
            }
        )

    # Attributes the user explicitly answered: state them back, or flag the gap.
    line = coverage.get("line")
    for key, wanted in (profile.per_line.get(line) or {}).items() if line else ():
        stated = coverage.get(key)
        attribute = key.replace("_", " ")
        if stated is None:
            reasons.append(
                {"text": prompts.DET_GAP_ATTR.format(attribute=attribute), "kind": "gap"}
            )
        elif isinstance(stated, bool):
            if stated and wanted:
                reasons.append(
                    {"text": prompts.DET_REASON_FLAG.format(attribute=attribute), "kind": "match"}
                )
        elif str(stated).casefold() == str(wanted).casefold():
            reasons.append(
                {
                    "text": prompts.DET_REASON_ATTR.format(
                        attribute=attribute, value=str(wanted).replace("_", " ")
                    ),
                    "kind": "match",
                }
            )

    return reasons


def no_match_details(
    pool_by_line: dict[str, list[dict[str, Any]]], profile: NeedsProfile, max_items: int = 4
) -> list[str]:
    """Deterministic no-match diagnosis: for each line, why each candidate in
    the pre-narrowing pool was excluded — the discriminator whose keeps() failed
    (via exclusion_reason) or the first programmatic violation (check_policy).
    Grounded in the same checks that made the decision, zero LLM."""
    from agent import prompts
    from agent.discriminators import exclusion_reason

    details: list[str] = []
    for line, pool in pool_by_line.items():
        items: list[str] = []
        for policy in pool[:max_items]:
            reason = exclusion_reason(policy, profile, line)
            if reason is None:
                violations = check_policy(policy, profile)["violations"]
                reason = violations[0] if violations else None
            if reason:
                items.append(f"{policy.get('name') or policy.get('slug')} {reason}")
        if items:
            details.append(prompts.no_match_detail(line, items))
    return details


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
