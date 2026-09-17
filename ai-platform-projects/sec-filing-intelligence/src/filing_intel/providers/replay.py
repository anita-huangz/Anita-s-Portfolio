"""Deterministic replay of recorded model responses.

This is what lets the test suite and CI exercise the whole agent graph -- tool
loop, telemetry, cost accounting, verification -- without a key and without
spending money, while the same code path runs against the live API in
production.

A fixture is keyed by a digest of the semantically meaningful parts of the
request. Latency and token counts come from the recording, so cost assertions in
tests are exercising the real arithmetic on real usage numbers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..contracts import ModelResponse
from ..errors import ReplayMiss
from .base import ModelProvider, ModelRequest


def fixture_key(request: ModelRequest) -> str:
    """Digest of the parts of a request that should change the response.

    `max_tokens` and `cache_prefix` are excluded deliberately: they affect
    billing and truncation, not which answer a deterministic fixture stands for.
    """
    payload = {
        "model": request.model,
        "system": request.system,
        "messages": request.messages,
        "tools": sorted(t.name for t in request.tools),
        "effort": request.effort,
    }
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


class ReplayProvider:
    """Serves recorded responses; optionally records misses against a real provider."""

    name = "replay"

    def __init__(
        self,
        fixture_dir: str | Path,
        *,
        record_with: ModelProvider | None = None,
    ) -> None:
        self._dir = Path(fixture_dir)
        self._record_with = record_with
        #: Keys requested during this process, in order. Useful in tests to
        #: assert how many model calls a graph actually made.
        self.requested: list[str] = []

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        key = fixture_key(request)
        self.requested.append(key)
        path = self._path(key)

        if path.exists():
            data = json.loads(path.read_text())
            response = ModelResponse.model_validate(data["response"])
            # Preserve the recorded provider/model so cost maths stays honest.
            return response

        if self._record_with is None:
            raise ReplayMiss(
                f"no recorded fixture for key {key} (model={request.model}, "
                f"{len(request.messages)} messages). Re-record with "
                f"FILING_INTEL_REPLAY_RECORD=true and a live provider."
            )

        response = await self._record_with.complete(request)
        self.save(key, request, response)
        return response

    def save(self, key: str, request: ModelRequest, response: ModelResponse) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(
            json.dumps(
                {
                    "key": key,
                    "request": {
                        "model": request.model,
                        "effort": request.effort,
                        "tools": sorted(t.name for t in request.tools),
                        "message_count": len(request.messages),
                    },
                    "response": response.model_dump(mode="json"),
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
            + "\n"
        )


class ScriptedProvider:
    """Returns a fixed sequence of responses. For unit tests of the graph itself."""

    name = "scripted"

    def __init__(self, responses: list[ModelResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if not self._responses:
            raise ReplayMiss("ScriptedProvider ran out of responses")
        return self._responses.pop(0)


