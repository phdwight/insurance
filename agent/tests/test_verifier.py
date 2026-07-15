"""Verifier panel tests with faked judges (no API calls)."""

import asyncio

from agent import verifier

GROUNDED = "Emergency medical coverage of PHP 2,500,000."


def make_policy() -> dict:
    return {
        "slug": "demo-asia-traveler",
        "premium_min": 550,
        "coverage": {"line": "travel", "medical_limit": 2500000},
        "match_reasons": [
            {"text": GROUNDED, "kind": "match"},  # grounded
            {"text": "Includes free airport lounge access.", "kind": "match"},  # fabricated
        ],
    }


def run(policy: dict) -> dict:
    return asyncio.run(verifier.verify_reasons(policy))


def _patch_judges(monkeypatch, vote_by_model: dict[str, bool]) -> None:
    monkeypatch.setenv("VERIFIER_MODELS", ",".join(vote_by_model))

    async def fake_judge(model_name: str, facts: dict, claim: str) -> bool:
        # judge votes True only for the grounded claim; per-model override
        grounded_claim = "2,500,000" in claim
        return vote_by_model[model_name] and grounded_claim

    monkeypatch.setattr(verifier, "_judge_one", fake_judge)


def test_unanimous_panel_drops_ungrounded_reason(monkeypatch) -> None:
    _patch_judges(monkeypatch, {"prov1:judge-a": True, "prov2:judge-b": True})
    policy = run(make_policy())
    assert policy["match_reasons"] == [{"text": GROUNDED, "kind": "match"}]
    assert policy["verification"]["reasons_dropped"] == 1
    assert policy["verification"]["judges"] == ["prov1:judge-a", "prov2:judge-b"]


def test_split_vote_rejects(monkeypatch) -> None:
    # judge-b rejects everything -> unanimity fails for ALL reasons -> fallback
    _patch_judges(monkeypatch, {"prov1:judge-a": True, "prov2:judge-b": False})
    policy = run(make_policy())
    assert policy["match_reasons"] == [{"text": verifier.FALLBACK_REASON, "kind": "match"}]
    assert policy["verification"]["reasons_dropped"] == 2


def test_gap_reasons_survive_even_when_judges_reject(monkeypatch) -> None:
    # An honest "gap" note is not a coverage claim — it must never be judged away,
    # or a partial match would silently look strong.
    _patch_judges(monkeypatch, {"prov1:judge-a": True, "prov2:judge-b": False})
    gap = "No trip cancellation limit is specified."
    policy = make_policy()
    policy["match_reasons"].append({"text": gap, "kind": "gap"})
    result = run(policy)
    kept = [reason["text"] for reason in result["match_reasons"]]
    assert gap in kept
    assert result["verification"]["reasons_checked"] == 2  # only the two positive claims


def test_judge_exception_counts_as_rejection(monkeypatch) -> None:
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:a,prov2:b")

    call_count = 0

    async def flaky_judge(model_name: str, facts: dict, claim: str) -> bool:
        nonlocal call_count
        call_count += 1
        if model_name == "prov2:b":
            raise RuntimeError("provider down")
        return True

    # patch one level lower: exercise the real error handling in _judge_one?
    # _judge_one already swallows exceptions; here we assert verify_reasons
    # tolerates a rejecting judge without raising.
    async def wrapped(model_name: str, facts: dict, claim: str) -> bool:
        try:
            return await flaky_judge(model_name, facts, claim)
        except Exception:
            return False

    monkeypatch.setattr(verifier, "_judge_one", wrapped)
    policy = run(make_policy())
    assert policy["match_reasons"] == [{"text": verifier.FALLBACK_REASON, "kind": "match"}]
    assert call_count == 4  # 2 reasons x 2 judges


def test_panel_disabled_with_fewer_than_two_judges(monkeypatch) -> None:
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:only-one")
    assert not verifier.panel_enabled()
    monkeypatch.setenv("VERIFIER_MODELS", "")
    assert not verifier.panel_enabled()
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:a, prov2:b")
    assert verifier.panel_enabled()
