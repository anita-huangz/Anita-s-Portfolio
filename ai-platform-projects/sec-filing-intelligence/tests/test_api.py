"""HTTP contract, driven through the real app with a scripted model."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import FakeEdgar, FakePrices, text_response
from filing_intel.api.app import create_app, get_runtime
from filing_intel.providers import ScriptedProvider
from filing_intel.runtime import FilingIntelRuntime

ANALYST_JSON = json.dumps(
    {
        "answer": "Apple flags supply-chain concentration.",
        "findings": [
            {
                "claim": "Concentrated manufacturing partners.",
                "confidence": "high",
                "citations": [
                    {
                        "accession": "0000320193-23-000106",
                        "form_type": "10-K",
                        "filed_at": "2023-11-03",
                        "detail": "Item 1A",
                    }
                ],
            }
        ],
    }
)
VERIFIER_JSON = json.dumps({"verified": True, "note": "ok", "unsupported_claims": []})


def script(turns: int = 6):
    return [
        text_response("plan"),
        text_response("done"),
        text_response(ANALYST_JSON),
        text_response(VERIFIER_JSON),
    ] * turns


@pytest.fixture
def client(settings, cache, telemetry):
    app = create_app(settings)
    runtime = FilingIntelRuntime(
        settings, ScriptedProvider(script()), cache, FakeEdgar(), FakePrices(), telemetry
    )
    # Override the dependency rather than the lifespan so no real runtime is built.
    app.dependency_overrides[get_runtime] = lambda: runtime
    app.state.runtime = runtime
    with TestClient(app) as c:
        c.runtime = runtime
        yield c


def test_healthz_reports_the_wiring(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["cache"] == "ok"
    assert sorted(body["tools"]) == [
        "company_financials", "fetch_filing_section", "price_reaction", "search_filings"
    ]


def test_research_returns_a_cited_answer(client):
    response = client.post(
        "/v1/research", json={"ticker": "aapl", "question": "What are the risks?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert body["verified"] is True
    assert body["findings"][0]["citations"][0]["accession"] == "0000320193-23-000106"
    assert body["estimated_cost_usd"] > 0
    assert body["session_id"]


def test_invalid_ticker_is_a_422_not_a_500(client):
    response = client.post("/v1/research", json={"ticker": "!!!", "question": "hi?"})
    assert response.status_code == 422


def test_unknown_body_field_is_rejected(client):
    response = client.post(
        "/v1/research",
        json={"ticker": "AAPL", "question": "What are the risks?", "sneaky": True},
    )
    assert response.status_code == 422


def test_question_is_required(client):
    assert client.post("/v1/research", json={"ticker": "AAPL"}).status_code == 422


def test_session_is_reusable_across_requests(client):
    first = client.post(
        "/v1/research", json={"ticker": "AAPL", "question": "First question?"}
    ).json()
    client.post(
        "/v1/research",
        json={
            "ticker": "AAPL",
            "question": "Second question?",
            "session_id": first["session_id"],
        },
    )
    session = client.get(f"/v1/sessions/{first['session_id']}").json()
    assert session["turns"] == 2
    assert session["estimated_cost_usd"] > 0


def test_unknown_session_is_404(client):
    assert client.get("/v1/sessions/nope").status_code == 404


def test_session_can_be_deleted(client):
    created = client.post(
        "/v1/research", json={"ticker": "AAPL", "question": "A question?"}
    ).json()
    assert client.delete(f"/v1/sessions/{created['session_id']}").status_code == 204
    assert client.get(f"/v1/sessions/{created['session_id']}").status_code == 404


def test_telemetry_summary_reflects_the_requests_made(client):
    client.post("/v1/research", json={"ticker": "AAPL", "question": "What are the risks?"})
    summary = client.get("/v1/telemetry/summary").json()
    assert summary["total_model_calls"] == 4
    assert summary["total_estimated_cost_usd"] > 0
    assert summary["by_model"]["claude-opus-5"]["calls"] == 4
    assert summary["model_failure_rate"] == 0.0


def test_telemetry_events_are_listable_and_limited(client):
    client.post("/v1/research", json={"ticker": "AAPL", "question": "What are the risks?"})
    body = client.get("/v1/telemetry/events?limit=2").json()
    assert body["count"] == 2
    assert body["events"][0]["type"] in {"model_call", "tool_call"}


def test_tools_endpoint_exposes_strict_schemas(client):
    tools = client.get("/v1/tools").json()["tools"]
    assert len(tools) == 4
    assert all(t["strict"] for t in tools)
    assert all(t["input_schema"]["additionalProperties"] is False for t in tools)


def test_openapi_schema_is_generated(client):
    schema = client.get("/openapi.json").json()
    assert "/v1/research" in schema["paths"]
    assert "/v1/telemetry/summary" in schema["paths"]


# --------------------------------------------------------------------------- #
# Streaming
# --------------------------------------------------------------------------- #


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """Split an SSE body into (event, payload) pairs."""
    events = []
    for block in text.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = json.loads(line.removeprefix("data: "))
        if name is not None:
            events.append((name, data))
    return events


def test_stream_emits_nodes_in_order_and_closes(client):
    response = client.get(
        "/v1/research/stream",
        params={"ticker": "AAPL", "question": "What are the supply chain risks?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = parse_sse(response.text)
    names = [name for name, _ in events]

    assert names[0] == "started"
    assert "plan" in names
    assert "analysis" in names
    assert names[-2:] == ["result", "close"]


def test_stream_result_matches_the_non_streaming_shape(client):
    response = client.get(
        "/v1/research/stream",
        params={"ticker": "AAPL", "question": "What are the supply chain risks?"},
    )
    result = next(data for name, data in parse_sse(response.text) if name == "result")
    assert result["ticker"] == "AAPL"
    assert result["verified"] is True
    assert result["findings"][0]["citations"][0]["accession"] == "0000320193-23-000106"
    assert result["estimated_cost_usd"] > 0


def test_stream_reports_the_trace_id_up_front(client):
    response = client.get(
        "/v1/research/stream", params={"ticker": "AAPL", "question": "A question?"}
    )
    events = parse_sse(response.text)
    started = next(data for name, data in events if name == "started")
    result = next(data for name, data in events if name == "result")
    # The client can correlate telemetry before the run finishes.
    assert started["trace_id"] == result["trace_id"]


def test_stream_rejects_a_bad_ticker_with_422(client):
    response = client.get(
        "/v1/research/stream", params={"ticker": "!!!", "question": "A question?"}
    )
    assert response.status_code == 422


def test_stream_updates_the_session(client):
    first = client.get(
        "/v1/research/stream", params={"ticker": "AAPL", "question": "First question?"}
    )
    session_id = next(
        d for n, d in parse_sse(first.text) if n == "result"
    )["session_id"]
    assert client.get(f"/v1/sessions/{session_id}").json()["turns"] == 1


# --------------------------------------------------------------------------- #
# UI mount
# --------------------------------------------------------------------------- #


def test_ui_dist_ignores_a_directory_without_an_index(monkeypatch, tmp_path):
    """A stale or half-built dist must not be mounted as if it were a UI."""
    from filing_intel.api.app import _ui_dist

    empty = tmp_path / "dist"
    empty.mkdir()
    monkeypatch.setenv("FILING_INTEL_UI_DIST", str(empty))
    # Falls through to the other candidates; either way it never returns the
    # index-less directory.
    assert _ui_dist() != empty


def test_ui_dist_honours_an_explicit_override(monkeypatch, tmp_path):
    from filing_intel.api.app import _ui_dist

    build = tmp_path / "dist"
    build.mkdir()
    (build / "index.html").write_text("<!doctype html>")
    monkeypatch.setenv("FILING_INTEL_UI_DIST", str(build))
    assert _ui_dist() == build


def test_api_routes_still_work_with_the_ui_mounted(client):
    """The UI is mounted last so it cannot shadow an API route."""
    assert client.get("/healthz").status_code == 200
    assert client.get("/v1/tools").status_code == 200
