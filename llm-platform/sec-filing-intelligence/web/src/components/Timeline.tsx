import type { TimelineStep } from "../types";

const TOOL_LABELS: Record<string, string> = {
  search_filings: "Searched filings",
  fetch_filing_section: "Read filing section",
  company_financials: "Pulled XBRL financials",
  price_reaction: "Measured price reaction",
};

function describeArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.join(",")}]` : String(v)}`)
    .join("  ");
}

interface Props {
  steps: TimelineStep[];
  running: boolean;
}

export function Timeline({ steps, running }: Props) {
  if (steps.length === 0) {
    return (
      <div className="panel">
        <h2>Agent run</h2>
        <p className="empty">
          Ask a question to watch the agent plan, call tools, and verify its own
          citations.
        </p>
      </div>
    );
  }

  return (
    <div className="panel">
      <h2>Agent run</h2>
      <ol className="timeline">
        {steps.map((step, i) => (
          <li className={`step ${classFor(step)}`} key={i}>
            <span className="dot" aria-hidden="true" />
            {render(step)}
          </li>
        ))}
        {running && (
          <li className="step">
            <span className="dot" aria-hidden="true" />
            <span className="title">
              <span className="spinner" aria-hidden="true" /> Working…
            </span>
          </li>
        )}
      </ol>
    </div>
  );
}

function classFor(step: TimelineStep): string {
  switch (step.kind) {
    case "plan":
      return "is-plan";
    case "tool":
      return step.call.ok ? "is-tool" : "is-failed";
    case "analysis":
      return "is-analysis";
    case "verified":
      return step.verified ? "is-verified" : "is-unverified";
    case "error":
      return "is-error";
    default:
      return "";
  }
}

function render(step: TimelineStep) {
  switch (step.kind) {
    case "started":
      return (
        <>
          <div className="title">Run started</div>
          <div className="meta">trace {step.trace_id.slice(0, 12)}</div>
        </>
      );
    case "plan":
      return (
        <>
          <div className="title">Planned the research</div>
          <div className="plan-text">{step.plan}</div>
        </>
      );
    case "tool":
      return (
        <>
          <div className="title">
            {TOOL_LABELS[step.call.tool] ?? step.call.tool}
            {!step.call.ok && " — failed"}
          </div>
          <div className="meta">{describeArgs(step.call.arguments ?? {})}</div>
          {!step.call.ok && step.call.error && (
            <div className="meta">{String(step.call.error)}</div>
          )}
        </>
      );
    case "analysis":
      return (
        <>
          <div className="title">Drafted the answer</div>
          <div className="meta">
            {step.findingCount} finding{step.findingCount === 1 ? "" : "s"}
          </div>
        </>
      );
    case "verified":
      return (
        <>
          <div className="title">
            {step.verified ? "Citations verified" : "Verification failed"}
          </div>
          {step.note && <div className="meta">{step.note}</div>}
        </>
      );
    case "error":
      return (
        <>
          <div className="title">Error</div>
          <div className="meta">{step.message}</div>
        </>
      );
  }
}
