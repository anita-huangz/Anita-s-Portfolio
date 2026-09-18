"""Tool registry: typed boundaries, least privilege, caching, telemetry.

Every tool call goes through `ToolRegistry.execute`, which is the single place
that enforces the capability grant, validates arguments against the tool's
Pydantic model, consults the cache, times the call, and emits a telemetry event.
A tool handler therefore only ever sees arguments that already validated, and
can only be reached by a caller that was granted its capability.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ..cache import CacheBackend, cache_key
from ..contracts import Capability, ToolResult
from ..errors import (
    FilingIntelError,
    ToolInputInvalid,
    ToolNotPermitted,
)
from ..providers.base import ToolSpec
from ..telemetry import TelemetryRecorder, ToolCallEvent

Handler = Callable[[Any], Awaitable[Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    capability: Capability
    handler: Handler
    #: 0 disables caching for this tool.
    cache_ttl_seconds: int = 3600

    def spec(self) -> ToolSpec:
        """The model-facing definition.

        `strict=True` requires `additionalProperties: false` and an explicit
        `required` list, which Pydantic's schema gives us as long as the model
        forbids extras -- which `Strict` does.
        """
        schema = self.args_model.model_json_schema()
        schema["additionalProperties"] = False
        # Strict tool use requires *every* property in `required` -- Pydantic
        # only lists fields without defaults, which the API rejects under
        # strict. Defaults stay in the schema as documentation for the model.
        schema["required"] = sorted(schema.get("properties", {}).keys())
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=_inline_defs(schema),
            strict=True,
        )


def _inline_defs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref`/`$defs` so the schema is self-contained.

    Pydantic hoists enums into `$defs`. Inlining keeps the tool schema readable
    in a request log and avoids depending on `$ref` support at the boundary.
    """
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                target = defs.get(ref.split("/")[-1], {})
                merged = {**resolve(target), **{k: v for k, v in node.items() if k != "$ref"}}
                return merged
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


class ToolRegistry:
    def __init__(
        self,
        cache: CacheBackend,
        telemetry: TelemetryRecorder,
        default_ttl: int = 3600,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._cache = cache
        self._telemetry = telemetry
        self._default_ttl = default_ttl

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs_for(self, capabilities: list[Capability]) -> list[ToolSpec]:
        """Only tools the caller may actually invoke are shown to the model.

        Hiding them is half the control; `execute` still enforces the grant, so
        a model that hallucinates a tool name gets a typed refusal rather than
        an unauthorized call.
        """
        granted = set(capabilities)
        return [
            tool.spec()
            for _, tool in sorted(self._tools.items())
            if tool.capability in granted
        ]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        capabilities: list[Capability],
        trace_id: str,
        session_id: str | None = None,
    ) -> ToolResult:
        started = time.perf_counter()
        tool = self._tools.get(name)

        if tool is None:
            return await self._fail(
                name, "unknown_tool", f"no such tool: {name}", trace_id, session_id, started
            )
        if tool.capability not in set(capabilities):
            return await self._fail(
                name,
                ToolNotPermitted.kind,
                f"tool {name!r} requires capability {tool.capability.value!r}",
                trace_id,
                session_id,
                started,
            )

        try:
            args = tool.args_model.model_validate(arguments)
        except ValidationError as exc:
            return await self._fail(
                name,
                ToolInputInvalid.kind,
                f"invalid arguments: {exc.errors(include_url=False)}",
                trace_id,
                session_id,
                started,
            )

        ttl = tool.cache_ttl_seconds or self._default_ttl
        key = cache_key(f"tool:{name}", args.model_dump(mode="json"))

        if tool.cache_ttl_seconds:
            hit = await self._cache.get(key)
            if hit is not None:
                latency_ms = (time.perf_counter() - started) * 1000
                await self._telemetry.record(
                    ToolCallEvent(
                        trace_id=trace_id,
                        session_id=session_id,
                        tool=name,
                        latency_ms=latency_ms,
                        ok=True,
                        cached=True,
                    )
                )
                return ToolResult(
                    tool=name,
                    ok=True,
                    data=json.loads(hit),
                    cached=True,
                    latency_ms=latency_ms,
                )

        try:
            data = await tool.handler(args)
        except FilingIntelError as exc:
            return await self._fail(
                name, exc.kind, str(exc), trace_id, session_id, started
            )
        except Exception as exc:
            return await self._fail(
                name, "unhandled", f"{type(exc).__name__}: {exc}", trace_id, session_id, started
            )

        payload = _jsonable(data)
        if tool.cache_ttl_seconds:
            await self._cache.set(key, json.dumps(payload, default=str, sort_keys=True), ttl)

        latency_ms = (time.perf_counter() - started) * 1000
        await self._telemetry.record(
            ToolCallEvent(
                trace_id=trace_id,
                session_id=session_id,
                tool=name,
                latency_ms=latency_ms,
                ok=True,
                cached=False,
            )
        )
        return ToolResult(tool=name, ok=True, data=payload, latency_ms=latency_ms)

    async def _fail(
        self,
        name: str,
        kind: str,
        message: str,
        trace_id: str,
        session_id: str | None,
        started: float,
    ) -> ToolResult:
        latency_ms = (time.perf_counter() - started) * 1000
        await self._telemetry.record(
            ToolCallEvent(
                trace_id=trace_id,
                session_id=session_id,
                tool=name,
                latency_ms=latency_ms,
                ok=False,
                failure_kind=kind,
            )
        )
        return ToolResult(
            tool=name, ok=False, error=message, error_kind=kind, latency_ms=latency_ms
        )


def _jsonable(data: Any) -> Any:
    """Normalise handler output into plain JSON types."""
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_jsonable(item) for item in data]
    if isinstance(data, dict):
        return {k: _jsonable(v) for k, v in data.items()}
    return data
