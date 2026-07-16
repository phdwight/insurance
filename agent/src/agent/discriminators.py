"""Catalog-driven elicitation: questions come from the policies, not a form.

Given the current candidate set (real policy records from the catalog), this
module decides (a) which candidates the user's answers so far still allow
(`narrow`), and (b) which single question would best split the remaining
candidates (`pick_question`). If candidates differ on an attribute, it's worth
asking about; if they all agree, asking wastes the user's time. All of this is
deterministic — the LLM never invents a question the catalog can't act on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from shared import NeedsProfile

TARGET_RESULTS = 3  # stop asking once a line is narrowed to this many
MAX_QUESTIONS = 5  # total question budget per session

# Destination regions, from narrow to broad. A policy covering a broader
# region also covers narrower ones (worldwide_ex_us excludes the US).
_REGION_COVERS = {
    "domestic": {"domestic", "asia", "worldwide", "worldwide_ex_us"},
    "asia": {"asia", "worldwide", "worldwide_ex_us"},
    "europe": {"worldwide", "worldwide_ex_us"},
    "usa": {"worldwide"},
    "worldwide": {"worldwide"},
}

_DESTINATION_REGIONS = {
    "asia": [
        "japan", "korea", "south korea", "taiwan", "hong kong", "china",
        "singapore", "thailand", "vietnam", "indonesia", "malaysia", "india",
        "asia",
    ],
    "domestic": ["philippines", "domestic", "local", "boracay", "palawan", "cebu"],
    "europe": ["europe", "schengen", "france", "germany", "italy", "spain", "uk"],
    "usa": ["usa", "us", "united states", "america", "canada"],
    "worldwide": ["worldwide", "anywhere", "multiple countries"],
}


def region_of(destination: str) -> str | None:
    lowered = destination.lower()
    for region, names in _DESTINATION_REGIONS.items():
        if any(name in lowered for name in names):
            return region
    return None


def _first_int(text: str) -> int | None:
    match = re.search(r"\d+", text.replace(",", ""))
    return int(match.group()) if match else None


def _yes_no(text: str) -> bool | None:
    lowered = text.strip().lower()
    if any(w in lowered for w in ("yes", "yeah", "oo", "sure", "need", "please")):
        return True
    if any(w in lowered for w in ("no", "hindi", "don't", "dont", "skip")):
        return False
    return None


@dataclass(frozen=True)
class Discriminator:
    """One catalog attribute worth asking about when candidates differ on it."""

    id: str  # "<line>.<profile_key>"
    line: str  # product line, or "*" for any
    profile_key: str  # key in profile.per_line[line] (or global: age)
    question: str
    extract: Any  # (policy) -> comparable value | None
    parse: Any  # (answer text) -> profile value | None
    keeps: Any  # (profile value, policy) -> bool
    kind: str = "text"  # UI input type: "choice" | "number" | "text"
    options: tuple[str, ...] | None = None  # tap answers; each must parse()
    # Plain-language gloss per option, keyed by option label. Renders under the
    # chip so a customer who doesn't know the jargon (VUL, endowment…) can still
    # choose confidently. Optional — self-explanatory options omit it.
    option_help: dict[str, str] | None = None

    def question_payload(self) -> dict:
        return {
            "text": self.question,
            "input_type": self.kind,
            "options": list(self.options) if self.options else None,
            "option_help": self.option_help or None,
        }


YES_NO = ("Yes", "No")


def _cov(policy: dict, key: str) -> Any:
    return (policy.get("coverage") or {}).get(key)


def _elig(policy: dict, key: str) -> Any:
    return (policy.get("eligibility") or {}).get(key)


def _keeps_destination(region: str, policy: dict) -> bool:
    covered = _cov(policy, "destinations")
    if covered is None:
        return True
    allowed = _REGION_COVERS.get(region)
    if allowed is None:
        return True
    if region == "europe" and _cov(policy, "schengen_compliant"):
        return True
    return covered in allowed


REGISTRY: list[Discriminator] = [
    Discriminator(
        id="travel.destination_region",
        line="travel",
        profile_key="destination_region",
        question="Where are you traveling to? Available plans differ by "
        "destination — some cover Asia only, others worldwide.",
        extract=lambda p: _cov(p, "destinations"),
        parse=lambda t: region_of(t),
        keeps=_keeps_destination,
        kind="choice",
        options=("Philippines", "Asia", "Europe", "USA", "Worldwide"),
    ),
    Discriminator(
        id="travel.trip_days",
        line="travel",
        profile_key="trip_days",
        question="How long is your trip, in days? Plans have different "
        "maximum trip lengths.",
        extract=lambda p: _cov(p, "max_trip_days"),
        parse=_first_int,
        keeps=lambda days, p: _cov(p, "max_trip_days") is None
        or days <= _cov(p, "max_trip_days"),
        kind="number",
    ),
    Discriminator(
        id="travel.covid_required",
        line="travel",
        profile_key="covid_required",
        question="Do you need COVID-19 medical coverage? Not all plans include it.",
        extract=lambda p: _cov(p, "covid_covered"),
        parse=_yes_no,
        keeps=lambda wanted, p: not wanted or bool(_cov(p, "covid_covered")),
        kind="choice",
        options=YES_NO,
    ),
    Discriminator(
        id="travel.schengen_required",
        line="travel",
        profile_key="schengen_required",
        question="Do you need a Schengen-compliant policy (required for "
        "European visa applications)?",
        extract=lambda p: _cov(p, "schengen_compliant"),
        parse=_yes_no,
        keeps=lambda wanted, p: not wanted or bool(_cov(p, "schengen_compliant")),
        kind="choice",
        options=YES_NO,
    ),
    Discriminator(
        id="pet.species",
        line="pet",
        profile_key="species",
        question="Is your pet a dog or a cat? Coverage differs by species.",
        extract=lambda p: tuple(sorted(_cov(p, "species") or [])),
        parse=lambda t: next(
            (s for s, words in {"dog": ("dog", "aso"), "cat": ("cat", "pusa")}.items()
             if any(w in t.lower() for w in words)),
            None,
        ),
        keeps=lambda species, p: _cov(p, "species") is None
        or species in _cov(p, "species"),
        kind="choice",
        options=("Dog", "Cat"),
    ),
    Discriminator(
        id="pet.age_months",
        line="pet",
        profile_key="age_months",
        question="How old is your pet? Plans have different age limits.",
        parse=lambda t: (_first_int(t) or 0) * 12
        if "year" in t.lower() or "taon" in t.lower()
        else _first_int(t),
        extract=lambda p: (_cov(p, "pet_age_min_months"), _cov(p, "pet_age_max_months")),
        keeps=lambda months, p: (
            (_cov(p, "pet_age_min_months") is None or months >= _cov(p, "pet_age_min_months"))
            and (_cov(p, "pet_age_max_months") is None or months <= _cov(p, "pet_age_max_months"))
        ),
        kind="number",
    ),
    Discriminator(
        id="health.plan_type",
        line="health",
        profile_key="plan_type",
        question="Do you prefer an HMO-style plan (network hospitals, cashless) "
        "or a reimbursement/indemnity plan?",
        extract=lambda p: _cov(p, "plan_type"),
        parse=lambda t: "hmo"
        if "hmo" in t.lower()
        else ("indemnity" if any(w in t.lower() for w in ("indemnity", "reimburse")) else None),
        keeps=lambda plan, p: _cov(p, "plan_type") is None or _cov(p, "plan_type") == plan,
        kind="choice",
        options=("HMO", "Indemnity (reimbursement)"),
        option_help={
            "HMO": "Use the insurer's hospital network — cashless, nothing to file.",
            "Indemnity (reimbursement)": "Pay first at any hospital, then claim the money back.",
        },
    ),
    Discriminator(
        id="life.policy_type",
        line="life",
        profile_key="policy_type",
        question="Are you looking for pure protection for a set period (term), "
        "lifetime coverage (whole life), or insurance with investment (VUL)?",
        extract=lambda p: _cov(p, "policy_type"),
        parse=lambda t: next(
            (k for k in ("term", "whole", "vul", "endowment") if k in t.lower()), None
        ),
        keeps=lambda kind, p: _cov(p, "policy_type") is None
        or _cov(p, "policy_type") == kind,
        kind="choice",
        options=("Term", "Whole life", "VUL", "Endowment"),
        option_help={
            "Term": "Pure protection for a set number of years — lowest cost, no cash value.",
            "Whole life": "Covers you for life and builds guaranteed cash value over time.",
            "VUL": "Life cover plus investment funds — the value can grow or fall with the market.",
            "Endowment": "Pays a lump sum on a set date, with life protection until then.",
        },
    ),
    # Global: only asked when candidates actually differ on age eligibility.
    Discriminator(
        id="*.age",
        line="*",
        profile_key="age",
        question="How old is the person to be insured? Eligibility differs "
        "between these plans.",
        extract=lambda p: (_elig(p, "age_min"), _elig(p, "age_max")),
        parse=lambda t: v if (v := _first_int(t)) is not None and 0 <= v <= 120 else None,
        keeps=lambda age, p: (
            (_elig(p, "age_min") is None or age >= _elig(p, "age_min"))
            and (_elig(p, "age_max") is None or age <= _elig(p, "age_max"))
        ),
        kind="number",
    ),
]

def by_id(disc_id: str) -> Discriminator | None:
    return next((d for d in REGISTRY if d.id == disc_id), None)


def _profile_value(profile: NeedsProfile, disc: Discriminator, line: str) -> Any:
    if disc.line == "*":
        return getattr(profile, disc.profile_key, None)
    return profile.per_line.get(line, {}).get(disc.profile_key)


def _line_discriminators(line: str) -> list[Discriminator]:
    return [d for d in REGISTRY if d.line in (line, "*")]


def apply_answer(profile: NeedsProfile, pending: str, text: str) -> bool:
    """Apply the user's answer to the pending question ("budget" or a
    discriminator id), deterministically. Returns True if it parsed."""
    if pending == "budget":
        value = _first_int(text)
        if value is None:
            return False
        profile.budget_amount = value
        return True

    disc = by_id(pending)
    if disc is None:
        return False
    value = disc.parse(text)
    if value is None:
        return False
    if disc.line == "*":
        setattr(profile, disc.profile_key, value)
    else:
        profile.per_line.setdefault(disc.line, {})[disc.profile_key] = value
    return True


def narrow(candidates: list[dict], profile: NeedsProfile, line: str) -> list[dict]:
    """Keep only candidates consistent with every answer given so far."""
    kept = candidates
    for disc in _line_discriminators(line):
        value = _profile_value(profile, disc, line)
        if value is None:
            continue
        kept = [p for p in kept if disc.keeps(value, p)]
    return kept


def exclusion_reason(policy: dict, profile: NeedsProfile, line: str) -> str | None:
    """Why the user's answers exclude this policy, or None if it survives.

    Runs the exact keeps() checks narrow() uses, so the no-match diagnosis can
    never disagree with the narrowing that produced it. Copy in prompts.py."""
    from agent import prompts

    for disc in _line_discriminators(line):
        value = _profile_value(profile, disc, line)
        if value is None or disc.keeps(value, policy):
            continue
        attribute = disc.profile_key.replace("_", " ")
        wanted = str(value).replace("_", " ")
        if disc.profile_key == "age":
            eligibility = policy.get("eligibility") or {}
            return prompts.NO_MATCH_REASON_AGE.format(
                age_min=eligibility.get("age_min", 0),
                age_max=eligibility.get("age_max", "any"),
                age=value,
            )
        stated = disc.extract(policy)
        if isinstance(stated, bool):
            return prompts.NO_MATCH_REASON_FLAG.format(attribute=attribute)
        if stated is None or isinstance(stated, tuple):
            return prompts.NO_MATCH_REASON_UNSUPPORTED.format(
                attribute=attribute, wanted=wanted
            )
        return prompts.NO_MATCH_REASON_ATTR.format(
            attribute=attribute, stated=str(stated).replace("_", " "), wanted=wanted
        )
    return None


def pick_question(
    candidates: list[dict], profile: NeedsProfile, line: str, asked: list[str]
) -> Discriminator | None:
    """The unanswered attribute that best splits the current candidates.

    Best = the attribute whose most common value covers the fewest candidates
    (closest to an even split). Attributes all candidates agree on are never
    asked — the catalog answered them already.
    """
    best: tuple[float, Discriminator] | None = None
    for disc in _line_discriminators(line):
        if disc.id in asked or _profile_value(profile, disc, line) is not None:
            continue
        values = [v for p in candidates if (v := disc.extract(p)) is not None]
        if len(values) < len(candidates) or len(set(values)) < 2:
            continue  # unknown for some candidates, or no disagreement
        biggest_group = max(values.count(v) for v in set(values))
        score = 1 - biggest_group / len(values)
        if best is None or score > best[0]:
            best = (score, disc)
    return best[1] if best else None
