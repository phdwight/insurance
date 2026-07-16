from agent.discriminators import narrow, pick_question, region_of

from shared import NeedsProfile, ProductLine

ASIA = {
    "slug": "demo-asia-traveler",
    "premium_min": 550,
    "premium_frequency": "single",
    "eligibility": {"age_min": 0, "age_max": 75},
    "coverage": {
        "line": "travel",
        "destinations": "asia",
        "schengen_compliant": False,
        "covid_covered": True,
        "max_trip_days": 30,
    },
}
WORLDWIDE = {
    "slug": "demo-worldwide-explorer",
    "premium_min": 1500,
    "premium_frequency": "single",
    "eligibility": {"age_min": 0, "age_max": 70},
    "coverage": {
        "line": "travel",
        "destinations": "worldwide",
        "schengen_compliant": True,
        "covid_covered": True,
        "max_trip_days": 60,
    },
}


def profile(**per_line_travel) -> NeedsProfile:
    return NeedsProfile(
        product_lines=[ProductLine.TRAVEL],
        per_line={"travel": per_line_travel} if per_line_travel else {},
    )


def test_region_mapping() -> None:
    assert region_of("two weeks in Japan") == "asia"
    assert region_of("Paris, France") == "europe"
    assert region_of("New York, USA") == "usa"
    assert region_of("Mars") is None


def test_question_comes_from_catalog_disagreement() -> None:
    disc = pick_question([ASIA, WORLDWIDE], profile(), "travel", asked=[])
    # candidates differ on destinations, schengen, trip days — but NOT covid
    assert disc is not None
    assert disc.id != "travel.covid_required"  # both cover COVID: never asked


def test_no_question_when_candidates_agree() -> None:
    # single candidate (or identical ones) -> nothing to discriminate
    assert pick_question([ASIA], profile(), "travel", asked=[]) is None


def test_narrow_by_destination() -> None:
    kept = narrow([ASIA, WORLDWIDE], profile(destination_region="asia"), "travel")
    assert {p["slug"] for p in kept} == {"demo-asia-traveler", "demo-worldwide-explorer"}

    kept = narrow([ASIA, WORLDWIDE], profile(destination_region="europe"), "travel")
    assert [p["slug"] for p in kept] == ["demo-worldwide-explorer"]


def test_narrow_by_trip_days_and_schengen() -> None:
    kept = narrow([ASIA, WORLDWIDE], profile(trip_days=45), "travel")
    assert [p["slug"] for p in kept] == ["demo-worldwide-explorer"]

    kept = narrow([ASIA, WORLDWIDE], profile(schengen_required=True), "travel")
    assert [p["slug"] for p in kept] == ["demo-worldwide-explorer"]


def test_narrow_to_empty_is_honest_no_match() -> None:
    picky = profile(destination_region="usa", trip_days=90)
    assert narrow([ASIA, WORLDWIDE], picky, "travel") == []


def test_asked_questions_not_repeated() -> None:
    disc = pick_question([ASIA, WORLDWIDE], profile(), "travel", asked=[])
    again = pick_question([ASIA, WORLDWIDE], profile(), "travel", asked=[disc.id])
    assert again is None or again.id != disc.id


def test_every_choice_option_parses_deterministically() -> None:
    from agent.discriminators import REGISTRY

    for disc in REGISTRY:
        if disc.kind == "choice":
            assert disc.options, disc.id
            for option in disc.options:
                assert disc.parse(option) is not None, (disc.id, option)
        payload = disc.question_payload()
        assert payload["input_type"] in ("choice", "number", "text")
        # Any plain-language gloss must key off a real option label and be
        # non-empty, or it silently never renders on its chip.
        if disc.option_help:
            assert set(disc.option_help) <= set(disc.options or ()), disc.id
            for label, gloss in disc.option_help.items():
                assert gloss.strip(), (disc.id, label)
            assert payload["option_help"] == disc.option_help


def test_jargon_options_carry_plain_language_help() -> None:
    """Insurance jargon a customer may not know must ship a plain-language gloss."""
    from agent.discriminators import by_id

    for disc_id, jargon in (
        ("life.policy_type", ("Term", "Whole life", "VUL", "Endowment")),
        ("health.plan_type", ("HMO", "Indemnity (reimbursement)")),
    ):
        disc = by_id(disc_id)
        assert disc is not None and disc.option_help, disc_id
        for term in jargon:
            assert disc.option_help.get(term), (disc_id, term)


def test_global_age_asked_only_if_eligibility_differs() -> None:
    same_band = [dict(ASIA), dict(ASIA, slug="asia-2")]
    disc = pick_question(same_band, profile(), "travel", asked=[])
    assert disc is None or disc.id != "*.age"
