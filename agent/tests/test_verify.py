from decimal import Decimal

from agent.verify import check_policy, verify_candidates

from shared import NeedsProfile, PremiumFrequency

POLICY = {
    "slug": "demo-term-life-20",
    "name": "Demo Term Life 20",
    "insurer_name": "Maharlika Life (Demo)",
    "premium_min": 800,
    "premium_max": 4500,
    "premium_frequency": "monthly",
    "currency": "PHP",
    "eligibility": {"age_min": 18, "age_max": 55},
    "coverage": {"line": "life"},
    "exclusions": [],
}


def test_age_violations_caught() -> None:
    result = check_policy(POLICY, NeedsProfile(age=60))
    assert not result["ok"]
    assert "above maximum" in result["violations"][0]

    assert check_policy(POLICY, NeedsProfile(age=30))["ok"]


def test_budget_violation_normalizes_frequency() -> None:
    # 6,000 PHP annual budget = 500/month < 800/month minimum premium
    profile = NeedsProfile(
        age=30, budget_amount=Decimal("6000"), budget_frequency=PremiumFrequency.ANNUAL
    )
    result = check_policy(POLICY, profile)
    assert not result["ok"]
    assert "exceeds budget" in result["violations"][0]


def test_verify_candidates_filters_and_caps() -> None:
    ok_policy = dict(POLICY, slug="ok")
    too_old = dict(POLICY, slug="bad", eligibility={"age_min": 18, "age_max": 25})
    kept = verify_candidates([too_old, ok_policy], NeedsProfile(age=30), keep=3)
    assert [p["slug"] for p in kept] == ["ok"]


def test_missing_data_never_violates() -> None:
    bare = {"slug": "bare", "name": "Bare", "coverage": {}}
    assert check_policy(bare, NeedsProfile(age=40, budget_amount=Decimal("100")))["ok"]
