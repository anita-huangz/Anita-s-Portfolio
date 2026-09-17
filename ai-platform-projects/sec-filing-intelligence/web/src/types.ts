/** Mirrors the Pydantic contracts in `src/filing_intel/contracts.py`. */

export interface Citation {
  accession: string;
  form_type: string;
  filed_at: string;
  detail: string;
  url?: string | null;
}

export interface Finding {
  claim: string;
  confidence: "low" | "medium" | "high";
  citations: Citation[];
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
}

export interface ResearchResult {
  ticker: string;
  question: string;
  answer: string;
  findings: Finding[];
  session_id: string;
  trace_id: string;
  tool_calls_made: number;
  usage: TokenUsage;
  estimated_cost_usd: number;
  latency_ms: number;
  verified: boolean;
  verifier_note?: string | null;
}

export interface ToolCallEvent {
  tool: string;
  ok: boolean;
  arguments: Record<string, unknown>;
  error?: string | null;
}

/** A step in the agent's run, rendered in order as it arrives. */
export type TimelineStep =
  | { kind: "started"; trace_id: string }
  | { kind: "plan"; plan: string }
  | { kind: "tool"; call: ToolCallEvent }
  | { kind: "analysis"; findingCount: number }
  | { kind: "verified"; verified: boolean; note?: string | null }
  | { kind: "error"; message: string };

/**
 * EDGAR's canonical URL for a filing. The accession number is dashed in the
 * API and undashed in the archive path, which is the usual way these links
 * end up broken.
 */
export function edgarUrl(accession: string): string {
  const bare = accession.replace(/-/g, "");
  return `https://www.sec.gov/Archives/edgar/data/${bare.slice(0, 10).replace(/^0+/, "")}/${bare}`;
}
