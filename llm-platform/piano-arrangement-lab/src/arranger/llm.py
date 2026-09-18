"""The optional language-model layer, and the wall it sits behind.

The model's entire job is to fill in an `Intent` — four fields, every one of
them validated against an enumeration or a numeric range before it reaches the
engine. It never chooses a note. That is not modesty about what models can do;
it is what makes the feature safe to ship on a page where anyone can type
anything, because the worst a bad completion can do is fail validation and fall
back to the keyword parser.

Four providers are supported because the interesting constraint on this project
was never technical. A static site cannot hold a secret, so a visitor either
brings their own key or gets the deterministic path — and a visitor who brings
one will not be bringing an Anthropic key specifically. Groq and Google both
issue free keys to anyone; Ollama needs none but only works locally.

`interpret()` never raises on a provider problem. A timeout, a bad key, a
malformed completion and a refusal all land in the same place: the keyword
parser, with the reason recorded on the result.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .intent import STYLES, Intent, parse_intent

SYSTEM_PROMPT = """\
You translate a musician's request into settings for a piano arranger.

Reply with ONLY a JSON object, no prose and no code fence, with these keys:
  "level": one of "beginner", "intermediate", "advanced"
  "style": one of {styles}
  "bpm": a number between 20 and 300
  "beats_per_chord": a number between 0.25 and 16
  "note": one short sentence, for the player, explaining your choices

Guidance:
- "easy", "for a child", "I just started" -> beginner
- "jazz", "bluesy", "smoky" -> jazzy; "chorale", "hymn", "Bach" -> hymn
- "quiet", "minimal", "sparse" -> sparse; "rich", "full", "cinematic" -> lush
- A sad or slow mood means a lower bpm; energetic means higher.
- If the request says nothing about a field, keep the current value.
"""


@dataclass(frozen=True)
class Provider:
    """How to talk to one API. Enough of a shape to cover the four that matter."""

    name: str
    url: str
    env_key: str
    model: str
    build: Callable[[str, str, str], tuple[dict[str, str], dict[str, Any]]]
    extract: Callable[[dict[str, Any]], str]
    needs_key: bool = True


def _anthropic(model: str, key: str, prompt: str):
    return (
        {"x-api-key": key, "anthropic-version": "2023-06-01",
         "content-type": "application/json"},
        {"model": model, "max_tokens": 300, "system": SYSTEM_PROMPT.format(
            styles=sorted(STYLES)),
         "messages": [{"role": "user", "content": prompt}]},
    )


def _openai_compatible(model: str, key: str, prompt: str):
    return (
        {"Authorization": f"Bearer {key}", "content-type": "application/json"},
        {"model": model, "max_tokens": 300, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(styles=sorted(STYLES))},
            {"role": "user", "content": prompt},
        ]},
    )


def _gemini(model: str, key: str, prompt: str):
    return (
        {"content-type": "application/json", "x-goog-api-key": key},
        {"systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT.format(styles=sorted(STYLES))}]},
         "contents": [{"parts": [{"text": prompt}]}]},
    )


def _ollama(model: str, key: str, prompt: str):
    return (
        {"content-type": "application/json"},
        {"model": model, "stream": False, "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(styles=sorted(STYLES))},
            {"role": "user", "content": prompt},
        ]},
    )


PROVIDERS: dict[str, Provider] = {
    "anthropic": Provider(
        "anthropic", "https://api.anthropic.com/v1/messages",
        "ANTHROPIC_API_KEY", "claude-sonnet-5", _anthropic,
        lambda body: body["content"][0]["text"],
    ),
    # Groq and OpenRouter both speak the OpenAI shape and both issue free keys.
    "groq": Provider(
        "groq", "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY", "llama-3.3-70b-versatile", _openai_compatible,
        lambda body: body["choices"][0]["message"]["content"],
    ),
    "gemini": Provider(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent",
        "GEMINI_API_KEY", "gemini-2.0-flash", _gemini,
        lambda body: body["candidates"][0]["content"]["parts"][0]["text"],
    ),
    # Local, free, and the only one that needs no key at all -- but it cannot
    # serve a public page, so it is a development convenience rather than a
    # deployment option.
    "ollama": Provider(
        "ollama", "http://localhost:11434/api/chat",
        "", "llama3.2", _ollama,
        lambda body: body["message"]["content"],
        needs_key=False,
    ),
}


@dataclass(frozen=True)
class Interpretation:
    """What the request was understood to mean, and how it was understood."""

    intent: Intent
    #: "keywords" or the provider name. Shown to the user, because "the model
    #: read this" and "a regex read this" are different claims.
    source: str
    #: One sentence for the player. Empty unless a model wrote one.
    note: str = ""
    #: Why the model was not used, when it was not.
    fallback_reason: str = ""


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the object out of a completion that may be wrapped in prose.

    Models are asked for bare JSON and usually comply. When they do not, the
    failure is almost always a code fence or a sentence of preamble, and
    recovering from that is cheaper than a retry.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return json.loads(fenced.group(1))
    braced = re.search(r"\{.*\}", text, re.S)
    if braced:
        return json.loads(braced.group(0))
    raise ValueError("no JSON object in the reply")


def interpret(
    request: str,
    provider: str | None = None,
    api_key: str | None = None,
    default: Intent | None = None,
    client: Any = None,
    timeout: float = 20.0,
) -> Interpretation:
    """Read a request, with a model if one is available and keywords if not.

    `client` takes an injected httpx-compatible client, which is how the tests
    exercise the whole path -- prompt, transport, parsing, validation -- with
    no network and no key.
    """
    default = default or Intent()
    keywords = parse_intent(request, default)

    if provider is None:
        return Interpretation(keywords, "keywords")
    if provider not in PROVIDERS:
        return Interpretation(
            keywords, "keywords", fallback_reason=f"unknown provider {provider!r}"
        )

    spec = PROVIDERS[provider]
    key = api_key or (os.environ.get(spec.env_key, "") if spec.env_key else "")
    if spec.needs_key and not key:
        return Interpretation(
            keywords, "keywords",
            fallback_reason=f"no API key ({spec.env_key} is unset)",
        )

    try:
        if client is None:
            import httpx  # imported lazily: the engine does not depend on it

            client = httpx.Client(timeout=timeout)
        headers, payload = spec.build(spec.model, key, request)
        response = client.post(spec.url, headers=headers, json=payload)
        if response.status_code >= 400:
            return Interpretation(
                keywords, "keywords",
                fallback_reason=f"{provider} returned HTTP {response.status_code}",
            )
        data = _extract_json(spec.extract(response.json()))
        intent = Intent(
            level=str(data.get("level", default.level)),
            style=str(data.get("style", default.style)),
            bpm=float(data.get("bpm", default.bpm)),
            beats_per_chord=float(data.get("beats_per_chord", default.beats_per_chord)),
        ).validated()
    except ImportError:
        return Interpretation(
            keywords, "keywords", fallback_reason="httpx is not installed (pip install '.[llm]')"
        )
    except Exception as exc:
        # Deliberately broad. A timeout, a refusal, a renamed JSON field and a
        # hallucinated style are all the same event here: the model did not
        # produce something usable, so the deterministic answer is used and the
        # reason is shown rather than swallowed.
        return Interpretation(
            keywords, "keywords",
            fallback_reason=f"{type(exc).__name__}: {exc}"[:160],
        )

    return Interpretation(intent, provider, note=str(data.get("note", "")))
