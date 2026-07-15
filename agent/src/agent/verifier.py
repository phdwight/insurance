"""Multi-LLM groundedness verifier for match reasons.

A panel of judge models from different providers cross-checks every
LLM-written match reason against the policy's verified fields. A reason
survives only if ALL judges independently rule it grounded (unanimous).
Failed reasons are dropped silently; a policy whose reasons all fail gets a
generic fallback line — the verifier never removes a policy (the programmatic
guardrail in verify.py already decided the policy itself is valid).

Config:
    VERIFIER_MODELS  comma-separated init_chat_model strings, e.g.
                     "anthropic:claude-haiku-4-5,openai:gpt-4o-mini"
                     (judges should differ from the writer model and ideally
                     from each other's provider to avoid self-consistency bias)
"""

import asyncio
import json
import os
from typing import Any

from agent.llm import chat_model
from agent.prompts import FALLBACK_REASON, JUDGE_SYSTEM, JudgeVerdict

__all__ = ["FALLBACK_REASON", "judge_models", "panel_enabled", "verify_recommendations"]


def judge_models() -> list[str]:
    raw = os.environ.get("VERIFIER_MODELS", "")
    return [model.strip() for model in raw.split(",") if model.strip()]


def panel_enabled() -> bool:
    return len(judge_models()) >= 2


async def _judge_one(model_name: str, policy_facts: dict, claim: str) -> bool:
    judge = chat_model(model_name).with_structured_output(JudgeVerdict)
    prompt = f"POLICY DATA:\n{json.dumps(policy_facts, default=str)}\n\nCLAIM:\n{claim}"
    try:
        verdict = await judge.ainvoke([("system", JUDGE_SYSTEM), ("human", prompt)])
        return verdict.grounded
    except Exception:
        # A failing judge must not take the product down; treat as "no vote"
        # by rejecting — unanimity then falls back to the generic reason.
        return False


async def verify_reasons(policy: dict[str, Any]) -> dict[str, Any]:
    """Return the policy with only unanimously grounded reasons kept.

    Only positive "match" claims are grounded — an honest "gap" note ("no term
    is specified") is not a coverage claim a judge could confirm and must never
    be dropped, or a partial match would silently look strong."""
    reasons = policy.get("match_reasons", [])
    if not reasons:
        return policy

    facts = {
        key: value
        for key, value in policy.items()
        if key not in ("match_reasons", "match_strength", "verification")
    }
    models = judge_models()

    async def grounded(text: str) -> bool:
        votes = await asyncio.gather(*(_judge_one(m, facts, text) for m in models))
        return all(votes)

    matches = [reason for reason in reasons if reason.get("kind") != "gap"]
    keep_flags = await asyncio.gather(*(grounded(reason["text"]) for reason in matches))

    kept: list[dict[str, Any]] = []
    match_index = 0
    for reason in reasons:  # preserve original order; gaps always survive
        if reason.get("kind") == "gap":
            kept.append(reason)
        else:
            if keep_flags[match_index]:
                kept.append(reason)
            match_index += 1

    dropped = len(matches) - sum(keep_flags)
    policy["match_reasons"] = kept or [{"text": FALLBACK_REASON, "kind": "match"}]
    policy["verification"] = {
        "judges": models,
        "reasons_checked": len(matches),
        "reasons_dropped": dropped,
    }
    return policy


async def verify_recommendations(
    recommendations: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    for policies in recommendations.values():
        await asyncio.gather(*(verify_reasons(policy) for policy in policies))
    return recommendations
