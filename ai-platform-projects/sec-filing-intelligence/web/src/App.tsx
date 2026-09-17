import { useCallback, useEffect, useRef, useState } from "react";

import { streamResearch } from "./api";
import { Findings } from "./components/Findings";
import { StatTiles } from "./components/StatTiles";
import { Timeline } from "./components/Timeline";
import type { Finding, ResearchResult, TimelineStep } from "./types";

const EXAMPLES: Array<{ ticker: string; question: string; label: string }> = [
  {
    ticker: "AAPL",
    question: "What supply chain risks does Apple disclose?",
    label: "Apple supply chain risk",
  },
  {
    ticker: "MSFT",
    question: "How does Microsoft describe risks related to artificial intelligence?",
    label: "Microsoft AI risk",
  },
  {
    ticker: "NVDA",
    question: "How has NVIDIA's annual revenue changed over recent fiscal years?",
    label: "NVIDIA revenue trend",
  },
];

type Theme = "light" | "dark";

export default function App() {
  const [ticker, setTicker] = useState("AAPL");
  const [question, setQuestion] = useState(EXAMPLES[0].question);
  const [steps, setSteps] = useState<TimelineStep[]>([]);
  const [answer, setAnswer] = useState("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Abort an in-flight stream if the component goes away, so the server
  // generator is not left running for a page nobody is watching.
  useEffect(() => () => abortRef.current?.abort(), []);

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setSteps([]);
    setAnswer("");
    setFindings([]);
    setResult(null);
    setError(null);
    setRunning(true);

    try {
      await streamResearch(ticker.trim().toUpperCase(), question.trim(), {
        onStep: (step) => {
          setSteps((prev) => [...prev, step]);
          if (step.kind === "error") setError(step.message);
        },
        onAnswer: (text, items) => {
          setAnswer(text);
          setFindings(items);
        },
        onResult: (res) => {
          setResult(res);
          setAnswer(res.answer);
          setFindings(res.findings);
        },
        onDone: () => setRunning(false),
      }, controller.signal);
    } catch (exc) {
      if ((exc as Error).name !== "AbortError") {
        setError((exc as Error).message);
      }
      setRunning(false);
    }
  }, [ticker, question]);

  const canSubmit = ticker.trim().length > 0 && question.trim().length >= 3 && !running;

  return (
    <div className="shell">
      <header className="masthead">
        <div>
          <h1>SEC Filing Intelligence</h1>
          <p>
            Multi-agent research over SEC EDGAR filings. The agent plans, pulls the
            filings it needs, drafts a cited answer, then verifies every citation
            against the evidence it actually gathered.
          </p>
        </div>
        <button
          className="theme-toggle"
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        >
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </header>

      <form
        className="query"
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) void run();
        }}
      >
        <div className="field">
          <label htmlFor="ticker">Ticker</label>
          <input
            id="ticker"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            maxLength={10}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="field">
          <label htmlFor="question">Question</label>
          <input
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What does the company disclose about…"
          />
        </div>
        <button className="submit" type="submit" disabled={!canSubmit}>
          {running ? "Researching…" : "Research"}
        </button>
      </form>

      <div className="examples">
        <span>Try:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            onClick={() => {
              setTicker(example.ticker);
              setQuestion(example.question);
            }}
          >
            {example.label}
          </button>
        ))}
      </div>

      <StatTiles result={result} />

      {error && <div className="error-box">{error}</div>}

      <div className="columns">
        <Timeline steps={steps} running={running} />
        <Findings
          answer={answer}
          findings={findings}
          result={result}
          running={running}
        />
      </div>

      <footer>
        Data from{" "}
        <a href="https://www.sec.gov/edgar" target="_blank" rel="noreferrer">
          SEC EDGAR
        </a>
        . Research output is generated by a language model and is not investment
        advice.
      </footer>
    </div>
  );
}
