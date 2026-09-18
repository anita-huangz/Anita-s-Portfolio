"""The model layer, exercised end to end with no network and no key.

Every provider's real request shape, real response shape, and the real
validator are used. Only the socket is replaced. That is the difference
between testing that the code compiles and testing that it works.
"""

import json

import pytest

from arranger.intent import Intent
from arranger.llm import PROVIDERS, interpret


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    """Records what was sent and replies with whatever the test set up."""

    def __init__(self, reply, status=200):
        self.reply = reply
        self.status = status
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "body": json})
        return FakeResponse(self.status, self.reply)


def wrap(provider: str, text: str) -> dict:
    """The text, in the envelope that provider actually returns."""
    return {
        "anthropic": {"content": [{"text": text}]},
        "groq": {"choices": [{"message": {"content": text}}]},
        "gemini": {"candidates": [{"content": {"parts": [{"text": text}]}}]},
        "ollama": {"message": {"content": text}},
    }[provider]


GOOD = json.dumps({
    "level": "advanced", "style": "jazzy", "bpm": 132,
    "beats_per_chord": 2, "note": "Swung and bright.",
})


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_every_provider_round_trips(provider):
    client = FakeClient(wrap(provider, GOOD))
    result = interpret("make it swing", provider=provider, api_key="k", client=client)
    assert result.source == provider
    assert result.intent.level == "advanced"
    assert result.intent.style == "jazzy"
    assert result.intent.bpm == 132
    assert result.note == "Swung and bright."


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
def test_every_provider_gets_the_system_prompt_and_the_request(provider):
    client = FakeClient(wrap(provider, GOOD))
    interpret("make it swing", provider=provider, api_key="k", client=client)
    sent = json.dumps(client.calls[0]["body"])
    assert "make it swing" in sent
    assert "beats_per_chord" in sent, "the schema must reach the model"


def test_the_key_is_sent_the_way_each_provider_expects():
    for provider, header in [
        ("anthropic", "x-api-key"),
        ("groq", "Authorization"),
        ("gemini", "x-goog-api-key"),
    ]:
        client = FakeClient(wrap(provider, GOOD))
        interpret("x", provider=provider, api_key="secret", client=client)
        assert "secret" in str(client.calls[0]["headers"][header])


def test_ollama_needs_no_key():
    client = FakeClient(wrap("ollama", GOOD))
    result = interpret("make it swing", provider="ollama", client=client)
    assert result.source == "ollama"


def test_json_wrapped_in_a_code_fence_is_recovered():
    client = FakeClient(wrap("groq", f"Here you go:\n```json\n{GOOD}\n```"))
    result = interpret("x", provider="groq", api_key="k", client=client)
    assert result.source == "groq"
    assert result.intent.style == "jazzy"


@pytest.mark.parametrize(
    "reply",
    [
        "I'm sorry, I can't help with that.",
        "",
        "{not json at all",
        json.dumps({"level": "expert", "style": "jazzy", "bpm": 120}),
        json.dumps({"level": "advanced", "style": "baroque", "bpm": 120}),
        json.dumps({"level": "advanced", "style": "jazzy", "bpm": 9000}),
    ],
)
def test_a_bad_completion_falls_back_instead_of_failing(reply):
    """The safety argument: nothing a model can say reaches the engine unchecked."""
    client = FakeClient(wrap("groq", reply))
    result = interpret("make it jazzy", provider="groq", api_key="k", client=client)
    assert result.source == "keywords"
    assert result.fallback_reason
    # And the deterministic reading still happened, so the user gets an answer.
    assert result.intent.style == "jazzy"


def test_an_http_error_falls_back_and_says_so():
    client = FakeClient(wrap("groq", GOOD), status=401)
    result = interpret("easy jazz", provider="groq", api_key="bad", client=client)
    assert result.source == "keywords"
    assert "401" in result.fallback_reason
    assert result.intent.level == "beginner"


def test_a_transport_failure_falls_back():
    class Broken:
        def post(self, *a, **k):
            raise TimeoutError("took too long")

    result = interpret("lush advanced", provider="groq", api_key="k", client=Broken())
    assert result.source == "keywords"
    assert "TimeoutError" in result.fallback_reason
    assert result.intent.style == "lush"


def test_a_missing_key_never_reaches_the_network():
    class Exploding:
        def post(self, *a, **k):
            raise AssertionError("must not be called without a key")

    result = interpret(
        "make it jazzy", provider="groq", api_key="", client=Exploding(),
    )
    assert result.source == "keywords"
    assert "GROQ_API_KEY" in result.fallback_reason


def test_no_provider_means_keywords_and_no_complaint():
    result = interpret("make it easy and jazzy")
    assert result.source == "keywords"
    assert result.fallback_reason == ""
    assert result.intent.level == "beginner"
    assert result.intent.style == "jazzy"


def test_an_unknown_provider_is_reported():
    result = interpret("easy", provider="not-a-provider")
    assert result.source == "keywords"
    assert "unknown provider" in result.fallback_reason


def test_fields_the_model_omits_keep_their_current_value():
    partial = json.dumps({"style": "sparse"})
    client = FakeClient(wrap("groq", partial))
    result = interpret(
        "thin it out", provider="groq", api_key="k",
        default=Intent(level="advanced", bpm=140), client=client,
    )
    assert result.intent.style == "sparse"
    assert result.intent.level == "advanced"
    assert result.intent.bpm == 140
