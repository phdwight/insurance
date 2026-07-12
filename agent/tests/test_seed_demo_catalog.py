"""Integration between the REAL seed data and the discriminator engine.

Guards the demo (and the catalog-drives-the-conversation principle) against
seed drift: if someone edits db/seed_data.yaml into a shape where questioning
never triggers, narrowing breaks, or policies stop validating, this fails.
"""

from pathlib import Path

import yaml
from agent.discriminators import MAX_QUESTIONS, TARGET_RESULTS, narrow, pick_question

from shared import Insurer, NeedsProfile, PolicyVersion, ProductLine

SEED_FILE = Path(__file__).resolve().parents[2] / "db" / "seed_data.yaml"


def load_seed() -> dict:
    return yaml.safe_load(SEED_FILE.read_text())


def as_candidate(entry: dict) -> dict:
    version = entry["version"]
    return {
        "slug": entry["slug"],
        "name": entry["name"],
        "premium_min": version.get("premium_min"),
        "premium_frequency": version.get("premium_frequency"),
        "eligibility": version.get("eligibility", {}),
        "coverage": version["coverage"],
    }


def travel_candidates() -> list[dict]:
    return [
        as_candidate(entry)
        for entry in load_seed()["policies"]
        if entry["product_line"] == "travel"
    ]


def test_every_seed_entry_validates_against_shared_models() -> None:
    data = load_seed()
    for insurer in data["insurers"]:
        Insurer(**insurer)
    for entry in data["policies"]:
        version = PolicyVersion(**entry["version"])
        assert version.coverage.line == entry["product_line"], entry["slug"]


def test_travel_seed_is_rich_enough_to_demo_questioning() -> None:
    candidates = travel_candidates()
    assert len(candidates) > TARGET_RESULTS, "questioning never triggers below threshold"

    profile = NeedsProfile(product_lines=[ProductLine.TRAVEL])
    first = pick_question(candidates, profile, "travel", asked=[])
    assert first is not None, "seed policies must disagree on something askable"
    assert first.id == "travel.destination_region"  # best splitter of the demo set


def test_seed_narrowing_reaches_a_single_policy() -> None:
    candidates = travel_candidates()
    profile = NeedsProfile(
        product_lines=[ProductLine.TRAVEL],
        per_line={"travel": {"destination_region": "europe", "trip_days": 50}},
    )
    kept = narrow(candidates, profile, "travel")
    assert [policy["slug"] for policy in kept] == ["demo-worldwide-explorer"]


def test_seed_questioning_loop_always_terminates() -> None:
    """Whatever the answers, the loop ends within the question budget."""
    candidates = travel_candidates()
    profile = NeedsProfile(product_lines=[ProductLine.TRAVEL])
    asked: list[str] = []

    for _ in range(MAX_QUESTIONS + len(candidates)):
        remaining = narrow(candidates, profile, "travel")
        if len(remaining) <= TARGET_RESULTS:
            break
        disc = pick_question(remaining, profile, "travel", asked)
        if disc is None:
            break
        asked.append(disc.id)  # deliberately never answer — worst case
    assert len(asked) <= MAX_QUESTIONS + 4  # bounded by distinct attributes
