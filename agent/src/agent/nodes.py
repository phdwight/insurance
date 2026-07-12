"""Graph nodes — catalog-driven elicitation. See docs/03-agent-design.md.

Flow per turn:
    ingest (update profile) -> [no lines yet? ask bootstrap]
    -> match (fetch real candidates from catalog)
    -> decide (narrow by answers; ask the question that best splits
       remaining candidates, or finalize)
    -> verify -> explain -> verify_explanations -> present

Prompts and user-facing copy live in prompts.py; question/answer semantics
live with the discriminator registry; this module only orchestrates.
"""

import asyncio
import json

from langchain_core.messages import AIMessage, HumanMessage

from agent import mcp_client, prompts
from agent.discriminators import (
    MAX_QUESTIONS,
    TARGET_RESULTS,
    apply_answer,
    narrow,
    pick_question,
    region_of,
)
from agent.llm import get_model, llm_available
from agent.parsing import detect_product_lines
from agent.state import AgentState
from agent.verify import verify_candidates
from shared import NeedsProfile, merge_profiles

# Anti-loop guardrails (MAX_QUESTIONS caps the discriminator loop; these two
# bound everything else so no session can recurse forever):
MAX_BOOTSTRAP_TURNS = 3  # "what would you like to protect?" attempts
MAX_TURNS = 20  # absolute user-turn ceiling; decide() stops asking beyond it

TRANSCRIPT_CHAR_LIMIT = 600
SEARCH_LIMIT = 8


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _user_transcript(state: AgentState) -> str:
    parts = [str(m.content) for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    return " ".join(parts)[-TRANSCRIPT_CHAR_LIMIT:]


def _derive(profile: NeedsProfile) -> NeedsProfile:
    """Fill derivable values (e.g. destination string -> region)."""
    travel = profile.per_line.get("travel", {})
    if travel.get("destination") and not travel.get("destination_region"):
        region = region_of(travel["destination"])
        if region:
            travel["destination_region"] = region
    return profile


async def _extract_with_llm(profile: NeedsProfile, text: str) -> NeedsProfile:
    # NeedsProfile.per_line is an open-ended map, which OpenAI's strict
    # json_schema structured output can't represent (it demands
    # additionalProperties:false everywhere). function_calling is provider-
    # agnostic and accepts arbitrary-key dicts on both OpenAI and Anthropic.
    extractor = get_model("small").with_structured_output(
        NeedsProfile, method="function_calling"
    )
    update = await extractor.ainvoke(
        [("system", prompts.EXTRACT_SYSTEM), ("human", text or "(empty message)")]
    )
    return merge_profiles(profile, update)


async def ingest(state: AgentState) -> dict:
    """Update the profile from the latest user message (both modes)."""
    profile = NeedsProfile(**state.get("profile", {}))
    text = _last_user_text(state)
    pending = state.get("pending_disc")

    parsed = bool(pending) and apply_answer(profile, pending, text)

    detected = detect_product_lines(text)
    if detected:
        profile.product_lines = list(dict.fromkeys(profile.product_lines + detected))

    # Free-form extraction (also rescues unparsed guided answers) when a key exists.
    if llm_available() and (state.get("mode") == "freeform" or not parsed):
        profile = await _extract_with_llm(profile, text)

    return {
        "profile": _derive(profile).model_dump(mode="json"),
        "pending_disc": None,
        "pending_question": None,
        "question": None,
        "turn_count": state.get("turn_count", 0) + 1,
    }


def route_ingest(state: AgentState) -> str:
    profile = NeedsProfile(**state["profile"])
    return "match" if profile.product_lines else "bootstrap"


# Only if the catalog is unreachable — normally options come from it live.
FALLBACK_LINE_OPTIONS = ["Travel", "Life", "Health", "Pet"]


async def _available_line_options() -> list[str]:
    """Catalog-first: offer only product lines with published policies."""
    try:
        lines = await mcp_client.list_product_lines()
        options = [
            line["code"].capitalize() for line in lines if line.get("policy_count", 0) > 0
        ]
        return options or FALLBACK_LINE_OPTIONS
    except Exception:
        return FALLBACK_LINE_OPTIONS


async def ask_bootstrap(state: AgentState) -> dict:
    count = state.get("bootstrap_count", 0)
    if count >= MAX_BOOTSTRAP_TURNS:
        # Guardrail: never loop the bootstrap question forever.
        return {
            "messages": [AIMessage(content=prompts.BOOTSTRAP_GIVE_UP)],
            "pending_question": None,
            "question": None,
            "done": True,
        }
    return {
        "messages": [AIMessage(content=prompts.BOOTSTRAP_QUESTION)],
        "pending_question": prompts.BOOTSTRAP_QUESTION,
        "question": {
            "text": prompts.BOOTSTRAP_QUESTION,
            "input_type": "choice",
            "options": await _available_line_options(),
        },
        "bootstrap_count": count + 1,
        "done": False,
    }


async def match(state: AgentState) -> dict:
    """Fetch full candidate records from the catalog for every detected line."""
    profile = NeedsProfile(**state["profile"])
    needs_text = _user_transcript(state)

    async def fetch(line: str) -> tuple[str, list]:
        found = await mcp_client.search_policies(
            product_line=line,
            needs_description=needs_text or None,
            age=profile.age,
            limit=SEARCH_LIMIT,
        )
        slugs = [r["slug"] for r in found.get("results", []) if r.get("slug")]
        full = await asyncio.gather(*(mcp_client.get_policy(s) for s in slugs))
        return line, [p for p in full if p and "error" not in p]

    lines = [line.value for line in profile.product_lines]
    pairs = await asyncio.gather(*(fetch(line) for line in lines))
    return {"candidates": dict(pairs)}


def decide(state: AgentState) -> dict:
    """Narrow candidates by the user's answers; ask the best-splitting
    question, or finalize when narrowed / out of questions / no match."""
    profile = NeedsProfile(**state["profile"])
    asked = state.get("asked", [])
    questions_asked = state.get("questions_asked", 0)

    narrowed = {
        line: narrow(candidates, profile, line)
        for line, candidates in state.get("candidates", {}).items()
    }
    update: dict = {
        "candidates": narrowed,
        "pending_disc": None,
        "pending_question": None,
        "question": None,
    }

    if questions_asked >= MAX_QUESTIONS or state.get("turn_count", 0) >= MAX_TURNS:
        return update  # guardrail: out of questions or session too long — finalize

    # Ask about the line with the most remaining candidates first.
    for line in sorted(narrowed, key=lambda name: -len(narrowed[name])):
        candidates = narrowed[line]
        if len(candidates) <= TARGET_RESULTS:
            continue
        disc = pick_question(candidates, profile, line, asked)
        if disc:
            update.update(
                pending_disc=disc.id,
                pending_question=disc.question,
                question=disc.question_payload(),
                asked=asked + [disc.id],
                questions_asked=questions_asked + 1,
            )
            return update

    # Nothing left to discriminate on structurally; budget still splits by price.
    if profile.budget_amount is None and any(
        len(candidates) > TARGET_RESULTS for candidates in narrowed.values()
    ):
        update.update(
            pending_disc="budget",
            pending_question=prompts.BUDGET_QUESTION,
            question={"text": prompts.BUDGET_QUESTION, "input_type": "number", "options": None},
            asked=asked + ["budget"],
            questions_asked=questions_asked + 1,
        )
    return update


def route_decide(state: AgentState) -> str:
    return "ask_question" if state.get("pending_question") else "verify"


def ask_question(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content=state["pending_question"])],
        "question": state.get("question"),
        "done": False,
    }


def verify(state: AgentState) -> dict:
    """Programmatic guardrail on the final narrowed candidates."""
    profile = NeedsProfile(**state["profile"])
    return {
        "recommendations": {
            line: verify_candidates(candidates, profile)
            for line, candidates in state.get("candidates", {}).items()
        }
    }


async def _explain_with_llm(profile: dict, recommendations: dict) -> dict[str, list[str]]:
    payload = {
        "user_profile": profile,
        "policies": {
            line: [{k: v for k, v in p.items() if k != "summary"} for p in policies]
            for line, policies in recommendations.items()
        },
    }
    writer = get_model("large").with_structured_output(prompts.ExplanationOutput)
    result = await writer.ainvoke(
        [("system", prompts.EXPLAIN_SYSTEM), ("human", json.dumps(payload, default=str))]
    )
    return {item.slug: item.reasons for item in result.items}


async def explain(state: AgentState) -> dict:
    recommendations = state.get("recommendations", {})
    if not any(recommendations.values()):
        return {"messages": [AIMessage(content=prompts.NO_MATCH_MESSAGE)], "done": True}

    reason_map = (
        await _explain_with_llm(state["profile"], recommendations) if llm_available() else {}
    )
    for policies in recommendations.values():
        for policy in policies:
            policy["match_reasons"] = reason_map.get(policy["slug"], [prompts.FALLBACK_REASON])

    return {"recommendations": recommendations}


async def verify_explanations(state: AgentState) -> dict:
    """Multi-LLM panel: drop match reasons not unanimously grounded.

    Skipped (no-op) unless VERIFIER_MODELS configures at least two judges.
    """
    from agent import verifier

    recommendations = state.get("recommendations", {})
    if not verifier.panel_enabled() or not any(recommendations.values()):
        return {}
    return {"recommendations": await verifier.verify_recommendations(recommendations)}


def present(state: AgentState) -> dict:
    recommendations = state.get("recommendations", {})
    total = sum(len(policies) for policies in recommendations.values())
    if total == 0:
        return {"done": True}  # explain already messaged the no-match case
    lines = ", ".join(line for line, policies in recommendations.items() if policies)
    return {
        "messages": [AIMessage(content=prompts.results_summary(total, lines))],
        "done": True,
    }
