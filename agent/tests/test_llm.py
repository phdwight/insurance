"""chat_model() provider fixes (no API calls).

OpenAI reasoning models (gpt-5.x) reject function tools + reasoning_effort on
/v1/chat/completions — which is exactly what with_structured_output(method=
"function_calling") and any tool binding send. Routing OpenAI through the
Responses API is what makes function tools work with a reasoning model, so the
flag must be set for OpenAI and left off for other providers.
"""

from agent.llm import chat_model


def test_openai_routes_through_responses_api(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = chat_model("openai:gpt-5.6-luna")
    assert getattr(model, "use_responses_api", None) is True


def test_non_openai_provider_is_untouched(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    model = chat_model("anthropic:claude-sonnet-4-5")
    # The flag is OpenAI-only; Anthropic models don't carry it at all.
    assert not hasattr(model, "use_responses_api")


def test_caller_can_still_override(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    model = chat_model("openai:gpt-4o", use_responses_api=False)
    assert model.use_responses_api is False
