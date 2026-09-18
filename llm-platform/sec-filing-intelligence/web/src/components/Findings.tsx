import type { Finding, ResearchResult } from "../types";
import { edgarUrl } from "../types";

interface Props {
  answer: string;
  findings: Finding[];
  result: ResearchResult | null;
  running: boolean;
}

export function Findings({ answer, findings, result, running }: Props) {
  if (!answer && !running) {
    return (
      <div className="panel">
        <h2>Answer</h2>
        <p className="empty">No answer yet.</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <h2>Answer</h2>

      {result && (
        <p style={{ margin: "0 0 12px" }}>
          {/* Glyph + label: the badge never relies on colour alone. */}
          <span className={`badge ${result.verified ? "verified" : "unverified"}`}>
            {result.verified ? "✓" : "!"}{" "}
            {result.verified ? "Citations verified" : "Unverified"}
          </span>
        </p>
      )}

      {answer ? <p className="answer">{answer}</p> : <p className="empty">Drafting…</p>}

      {result?.verifier_note && !result.verified && (
        <p className="empty" style={{ marginTop: -8 }}>
          {result.verifier_note}
        </p>
      )}

      {findings.map((finding, i) => (
        <div className="finding" key={i}>
          <div>
            <span className="claim">{finding.claim}</span>
            <span className="conf">{finding.confidence} confidence</span>
          </div>
          {finding.citations.length > 0 && (
            <ul className="citations">
              {finding.citations.map((citation, j) => (
                <li key={j}>
                  <a
                    href={citation.url ?? edgarUrl(citation.accession)}
                    target="_blank"
                    rel="noreferrer"
                    title={citation.detail}
                  >
                    {citation.form_type} · {citation.accession} · {citation.filed_at}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
