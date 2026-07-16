"""Verifier panel tests with faked judges (no API calls).

The panel is batched (token economy phase 3): ONE call per judge per policy
judges every claim against the same policy facts, instead of one call per
(judge, claim). Unanimity-per-reason semantics are unchanged."""

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


def _patch_judges(monkeypatch, vote_by_model: dict[str, bool], calls: list | None = None):
    monkeypatch.setenv("VERIFIER_MODELS", ",".join(vote_by_model))

    async def fake_judge(model_name: str, facts: dict, claims: list[str]) -> list[bool]:
        if calls is not None:
            calls.append((model_name, len(claims)))
        # judge grounds only the real claim; per-model override rejects all
        return [vote_by_model[model_name] and "2,500,000" in claim for claim in claims]

    monkeypatch.setattr(verifier, "_judge_policy", fake_judge)


def test_unanimous_panel_drops_ungrounded_reason(monkeypatch) -> None:
    _patch_judges(monkeypatch, {"prov1:judge-a": True, "prov2:judge-b": True})
    policy = run(make_policy())
    assert policy["match_reasons"] == [{"text": GROUNDED, "kind": "match"}]
    assert policy["verification"]["reasons_dropped"] == 1
    assert policy["verification"]["judges"] == ["prov1:judge-a", "prov2:judge-b"]


def test_one_batched_call_per_judge(monkeypatch) -> None:
    calls: list = []
    _patch_judges(monkeypatch, {"prov1:judge-a": True, "prov2:judge-b": True}, calls)
    run(make_policy())
    # 2 reasons x 2 judges used to be 4 calls; batching makes it 1 per judge,
    # each carrying both claims.
    assert sorted(calls) == [("prov1:judge-a", 2), ("prov2:judge-b", 2)]


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


def test_judge_error_fails_closed(monkeypatch) -> None:
    # _judge_policy swallows judge/provider errors into all-False; a policy
    # judged by a healthy grounder + a dead judge falls back (unanimity broken).
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:a,prov2:b")

    async def flaky(model_name: str, facts: dict, claims: list[str]) -> list[bool]:
        if model_name == "prov2:b":
            return [False] * len(claims)  # what _judge_policy returns on error
        return [True] * len(claims)

    monkeypatch.setattr(verifier, "_judge_policy", flaky)
    policy = run(make_policy())
    assert policy["match_reasons"] == [{"text": verifier.FALLBACK_REASON, "kind": "match"}]


def test_misaligned_judge_output_rejects_all(monkeypatch) -> None:
    # Exercise the real _judge_policy: a judge returning the wrong number of
    # verdicts must fail closed (every claim rejected), never misattribute.
    from agent.prompts import JudgePanelVerdicts

    class FakeStructured:
        async def ainvoke(self, messages):
            return JudgePanelVerdicts(grounded=[True])  # 1 verdict for 2 claims

    class FakeChat:
        def with_structured_output(self, schema):
            return FakeStructured()

    monkeypatch.setattr(verifier, "chat_model", lambda name: FakeChat())
    votes = asyncio.run(verifier._judge_policy("prov:x", {"a": 1}, ["claim 1", "claim 2"]))
    assert votes == [False, False]


def test_judge_exception_rejects_all(monkeypatch) -> None:
    # A provider blowup inside the batched call also fails closed.
    def boom(name):
        raise RuntimeError("provider down")

    monkeypatch.setattr(verifier, "chat_model", boom)
    votes = asyncio.run(verifier._judge_policy("prov:x", {"a": 1}, ["c1", "c2", "c3"]))
    assert votes == [False, False, False]


def test_panel_disabled_with_fewer_than_two_judges(monkeypatch) -> None:
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:only-one")
    assert not verifier.panel_enabled()
    monkeypatch.setenv("VERIFIER_MODELS", "")
    assert not verifier.panel_enabled()
    monkeypatch.setenv("VERIFIER_MODELS", "prov1:a, prov2:b")
    assert verifier.panel_enabled()
