"""Every LLM prompt, structured-output contract, and piece of user-facing copy.

One place to review wording — for prompt tuning, for compliance review of
user-facing text, and for future localization. Nothing here contains logic.
"""

from typing import Literal

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """You extract insurance needs from a user's message into a profile.
Rules:
- Only record what the user actually stated. NEVER guess or invent values; \
leave fields null when not mentioned.
- Detect all product lines mentioned or implied: life, health, travel, pet.
- Amounts are PHP unless another currency is explicit.
- per_line keys:
  travel: destination (string), destination_region (domestic|asia|europe|usa|worldwide), \
trip_days (int), covid_required (bool), schengen_required (bool)
  pet: species (dog|cat), age_months (int)
  health: plan_type (hmo|indemnity)
  life: policy_type (term|whole|vul|endowment)
- risk_notes: only risk factors the user volunteered (e.g. smoker, diabetes)."""

EXPLAIN_SYSTEM = """You write short reasons why each insurance policy matches the \
user's needs. STRICT rules:
- Use ONLY the facts in the provided policy JSON. Never invent coverage, \
amounts, or terms.
- 1-3 reasons per policy, each one sentence, each tied to a concrete field.
- Classify each reason with a kind: "match" when the policy MEETS a criterion \
the user asked about, or states a clearly positive fact; "gap" ONLY when a \
criterion THE USER ASKED ABOUT (present in their profile) is missing or not \
specified in the policy data. Do NOT flag fields the user never asked about \
(e.g. premium when they didn't mention budget). Be honest — surface real gaps \
as "gap", never dress them up as a match.
- Mention relevant exclusions or limits honestly if they matter to the user."""

JUDGE_SYSTEM = """You are a strict fact-checker for insurance policy explanations.
Given a policy's verified data (JSON) and a numbered list of claims written
about it, decide for EACH claim independently whether it is fully supported by
the data.

- grounded: every factual statement in the claim is directly supported by a
  field in the data. Paraphrase is fine; numbers must match.
- ungrounded: any part of the claim states something the data does not contain,
  contradicts the data, or embellishes (e.g. "best", "comprehensive" framed as
  fact, invented amounts/terms).

When unsure about a claim, answer ungrounded for that claim. Judge ONLY against
the provided data. Return exactly one verdict per claim, in claim order."""


# ---------------------------------------------------------------------------
# Structured-output contracts (paired with the prompts above)
# ---------------------------------------------------------------------------


class MatchReason(BaseModel):
    text: str
    # "match": the policy meets a criterion the user asked about (or a clearly
    # positive fact). "gap": a detail the user cares about is missing / not
    # specified in the policy data — surfaced honestly, and marks a partial match.
    kind: Literal["match", "gap"]


class PolicyReasons(BaseModel):
    slug: str
    reasons: list[MatchReason]


class ExplanationOutput(BaseModel):
    items: list[PolicyReasons]


class JudgePanelVerdicts(BaseModel):
    """One verdict per numbered claim, in claim order (batched judge call)."""

    grounded: list[bool]


# ---------------------------------------------------------------------------
# User-facing copy
# ---------------------------------------------------------------------------

BOOTSTRAP_QUESTION = (
    "What would you like to protect? For example: your family's income (life), "
    "health costs, an upcoming trip, or a pet."
)

BOOTSTRAP_GIVE_UP = (
    "I can only recommend policies for travel, life, health, or pet insurance "
    "right now, so I'll stop here. Start over anytime and pick one of those."
)

BUDGET_QUESTION = (
    "The remaining plans span different price ranges — roughly how much would "
    "you like to spend on premiums (in PHP)?"
)

NO_MATCH_MESSAGE = (
    "Based on your answers, no policy in the catalog currently matches — "
    "that's an honest no-match rather than a forced fit. Loosening the budget "
    "or requirements may open up options, or new policies may be added later."
)

FALLBACK_REASON = "Meets your stated criteria on record."

# Deterministic explanation templates — the zero-LLM path (no provider key, or
# LLM_ECONOMY=deterministic). Grounded by construction: every placeholder is
# filled straight from verified policy fields or the user's own answers.
DET_REASON_AGE = "At age {age}, you're within this plan's eligible range ({age_min}–{age_max})."
DET_REASON_BUDGET = (
    "Its minimum premium (₱{premium:,.0f} {frequency}) fits within your "
    "budget of ₱{budget:,.0f}."
)
DET_REASON_ATTR = "Matches your preference — {attribute}: {value}."
DET_REASON_FLAG = "Includes {attribute}."
DET_GAP_ATTR = "This plan doesn't state {attribute}, which you asked about."

# Premium-frequency wording for deterministic templates.
FREQUENCY_LABELS = {
    "monthly": "per month",
    "quarterly": "per quarter",
    "semi_annual": "every six months",
    "annual": "per year",
    "single": "one-time",
}

DISCLAIMER = (
    "This is information, not insurance advice — confirm final terms with the insurer."
)


def results_summary(total: int, lines: str) -> str:
    noun = "policy" if total == 1 else "policies"
    return (
        f"Found {total} matching {noun} ({lines}). Details and comparisons "
        f"are in the results panel. {DISCLAIMER}"
    )
