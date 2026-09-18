import type { Finding, Health, ResearchResult, TimelineStep, ToolCallEvent } from "./types";

/** Which provider is live. Drives the demo-mode notice. */
export async function fetchHealth(): Promise<Health | null> {
  try {
    const response = await fetch("/healthz");
    return response.ok ? ((await response.json()) as Health) : null;
  } catch {
    return null;
  }
}

export interface StreamHandlers {
  onStep: (step: TimelineStep) => void;
  onAnswer: (answer: string, findings: Finding[]) => void;
  onResult: (result: ResearchResult) => void;
  onDone: () => void;
}

/**
 * Consume the SSE research stream.
 *
 * `EventSource` is not used here: it cannot be aborted mid-flight in a way that
 * reliably closes the server generator, and it offers no access to a non-200
 * status, so a 422 from a bad ticker would surface as an opaque connection
 * error. `fetch` + a reader gives both.
 */
export async function streamResearch(
  ticker: string,
  question: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const params = new URLSearchParams({ ticker, question });
  const response = await fetch(`/v1/research/stream?${params}`, {
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      detail?.detail?.[0]?.msg ?? detail?.error ?? `request failed (${response.status})`;
    handlers.onStep({ kind: "error", message });
    handlers.onDone();
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("streaming is not supported in this browser");

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line; the final fragment may be
      // incomplete, so it stays in the buffer until the next chunk.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const event = parseFrame(frame);
        if (event) dispatch(event, handlers);
      }
    }
  } finally {
    reader.releaseLock();
    handlers.onDone();
  }
}

function parseFrame(frame: string): { name: string; data: unknown } | null {
  let name: string | null = null;
  let raw: string | null = null;

  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7).trim();
    else if (line.startsWith("data: ")) raw = line.slice(6);
  }
  if (!name) return null;

  try {
    return { name, data: raw ? JSON.parse(raw) : null };
  } catch {
    return { name, data: null };
  }
}

function dispatch(
  event: { name: string; data: any },
  handlers: StreamHandlers,
): void {
  switch (event.name) {
    case "started":
      handlers.onStep({ kind: "started", trace_id: event.data.trace_id });
      break;
    case "plan":
      handlers.onStep({ kind: "plan", plan: event.data.plan });
      break;
    case "tool_call":
      handlers.onStep({ kind: "tool", call: event.data as ToolCallEvent });
      break;
    case "analysis":
      handlers.onStep({
        kind: "analysis",
        findingCount: (event.data.findings ?? []).length,
      });
      handlers.onAnswer(event.data.answer ?? "", event.data.findings ?? []);
      break;
    case "result": {
      const result = event.data as ResearchResult;
      handlers.onStep({
        kind: "verified",
        verified: result.verified,
        note: result.verifier_note,
      });
      handlers.onResult(result);
      break;
    }
    case "error":
      handlers.onStep({ kind: "error", message: event.data.message });
      break;
  }
}
