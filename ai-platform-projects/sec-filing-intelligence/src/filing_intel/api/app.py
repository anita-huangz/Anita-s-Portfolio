"""HTTP surface.

Thin: parse, delegate to the runtime, serialize. The interesting behaviour lives
below this layer, which is the point -- the MCP server reaches the same runtime
without duplicating any of it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..config import Settings, get_settings
from ..contracts import ResearchRequest, ResearchResponse, Strict
from ..errors import FilingIntelError, UpstreamDataError
from ..runtime import FilingIntelRuntime
from ..telemetry import TelemetrySummary


class HealthResponse(Strict):
    status: str
    provider: str
    model: str
    cache: str
    tools: list[str]


class SessionResponse(Strict):
    session_id: str
    ticker: str | None
    turns: int
    estimated_cost_usd: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = FilingIntelRuntime.build(app.state.settings)
    app.state.runtime = runtime
    try:
        yield
    finally:
        await runtime.aclose()


def get_runtime(request: Request) -> FilingIntelRuntime:
    return request.app.state.runtime


#: FastAPI's modern dependency form. Using Annotated rather than a `Depends`
#: default keeps the signatures honest and avoids a call in a default arg.
Runtime = Annotated[FilingIntelRuntime, Depends(get_runtime)]


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="SEC Filing Intelligence",
        version="0.1.0",
        description=(
            "A multi-agent research service over SEC EDGAR filings, with "
            "per-call token, cost, and latency telemetry."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings or get_settings()

    @app.exception_handler(FilingIntelError)
    async def _domain_error(_: Request, exc: FilingIntelError) -> JSONResponse:
        # Upstream data problems are the caller's problem (bad ticker, no such
        # filing); everything else is ours.
        status = 502 if isinstance(exc, UpstreamDataError) else 500
        if isinstance(exc, UpstreamDataError) and "no SEC registrant" in str(exc):
            status = 404
        return JSONResponse(
            status_code=status, content={"error": str(exc), "kind": exc.kind}
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz(runtime: Runtime) -> HealthResponse:
        cache_ok = await runtime.cache.ping()
        return HealthResponse(
            status="ok",
            provider=getattr(runtime.provider, "name", "unknown"),
            model=runtime.settings.model,
            cache="ok" if cache_ok else "degraded",
            tools=runtime.registry.names,
        )

    @app.post("/v1/research", response_model=ResearchResponse)
    async def research(
        body: ResearchRequest, runtime: Runtime
    ) -> ResearchResponse:
        return await runtime.research(body)

    @app.get("/v1/sessions/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: str, runtime: Runtime
    ) -> SessionResponse:
        session = await runtime.sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="no such session")
        return SessionResponse(
            session_id=session.session_id,
            ticker=session.ticker,
            turns=session.turns,
            estimated_cost_usd=session.estimated_cost_usd,
        )

    @app.delete("/v1/sessions/{session_id}", status_code=204)
    async def delete_session(
        session_id: str, runtime: Runtime
    ) -> None:
        await runtime.sessions.delete(session_id)

    @app.get("/v1/telemetry/summary", response_model=TelemetrySummary)
    async def telemetry_summary(
        runtime: Runtime,
    ) -> TelemetrySummary:
        return runtime.telemetry_summary()

    @app.get("/v1/telemetry/events")
    async def telemetry_events(
        runtime: Runtime, limit: int = 100
    ) -> dict[str, Any]:
        events = runtime.telemetry.events[-limit:]
        return {
            "count": len(events),
            "events": [e.model_dump(mode="json") for e in events],
        }

    @app.get("/v1/tools")
    async def list_tools(runtime: Runtime) -> dict[str, Any]:
        from ..contracts import Capability

        return {
            "tools": [
                spec.model_dump() for spec in runtime.registry.specs_for(list(Capability))
            ]
        }

    return app


app = create_app()
