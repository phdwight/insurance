"""No-match diagnosis: a no-match must say WHY each candidate was excluded,
derived from the exact keeps()/check_policy checks that made the decision —
so a correct no-match never reads like the agent "missed" a policy, and a
corrupted profile value becomes visible ("you said 63")."""

import asyncio

from agent.discriminators import exclusion_reason
from agent.verify import no_match_details

from agent import nodes, usage
from shared import NeedsProfile

TERM_POLICY = {
    "slug": "safeguard-term-20",
    "name": "SafeGuard Term 20",
    "eligibility": {"age_min": 18, "age_max": 60},
    "coverage": {"line": "life", "policy_type": "term"},
}
WHOLE_POLICY = {
    "slug": "legacy-whole-life",
    "name": "Legacy Whole Life",
    "eligibility": {"age_min": 0, "age_max": 70},
    "coverage": {"line": "life", "policy_type": "whole"},
}


def profile(**kwargs) -> NeedsProfile:
    return NeedsProfile(product_lines=["life"], **kwargs)


def test_age_exclusion_names_the_band_and_the_answer() -> None:
    reason = exclusion_reason(TERM_POLICY, profile(age=63), "life")
    assert reason == "accepts ages 18–60 (you said 63)"


def test_attribute_mismatch_names_stated_vs_wanted() -> None:
    reason = exclusion_reason(
        WHOLE_POLICY, profile(per_line={"life": {"policy_type": "term"}}), "life"
    )
    assert reason == "has policy type whole, you asked for term"


def test_surviving_policy_has_no_reason() -> None:
    assert exclusion_reason(TERM_POLICY, profile(age=35), "life") is None


def test_details_cover_the_whole_pool() -> None:
    details = no_match_details(
        {"life": [TERM_POLICY, WHOLE_POLICY]},
        profile(age=63, per_line={"life": {"policy_type": "term"}}),
    )
    assert len(details) == 1
    text = details[0]
    assert text.startswith("Why nothing matched for life:")
    assert "SafeGuard Term 20 accepts ages 18–60 (you said 63)" in text
    assert "Legacy Whole Life has policy type whole, you asked for term" in text


def test_budget_violation_used_when_narrowing_passes() -> None:
    pricey = dict(TERM_POLICY, premium_min=5000, premium_frequency="monthly")
    details = no_match_details({"life": [pricey]}, profile(age=35, budget_amount=1000))
    assert len(details) == 1
    assert "exceeds budget" in details[0]


def test_explain_no_match_includes_diagnosis_and_ledgers_it(monkeypatch) -> None:
    events: list[str] = []

    async def fake_event(role, model="-"):
        events.append(role)

    monkeypatch.setattr(usage, "record_event", fake_event)
    state = {
        "profile": profile(age=63, per_line={"life": {"policy_type": "term"}}).model_dump(
            mode="json"
        ),
        "recommendations": {"life": []},
        "candidate_pool": {"life": [TERM_POLICY, WHOLE_POLICY]},
    }
    update = asyncio.run(nodes.explain(state))
    assert update["done"] is True
    message = update["messages"][0].content
    assert "no policy in the catalog" in message  # honest headline unchanged
    assert "accepts ages 18–60 (you said 63)" in message  # ...now with the why
    assert events == ["no_match"]


def test_explain_no_match_without_pool_still_honest(monkeypatch) -> None:
    async def fake_event(role, model="-"):
        pass

    monkeypatch.setattr(usage, "record_event", fake_event)
    update = asyncio.run(
        nodes.explain(
            {"profile": profile().model_dump(mode="json"), "recommendations": {"life": []}}
        )
    )
    assert "no policy in the catalog" in update["messages"][0].content
