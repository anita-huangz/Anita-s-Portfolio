import { useState } from "react";

import { useDemoData } from "../useDemoData";
import { BarChart, ConfusionMatrix, LineChart, ScatterChart, type ScatterGroup } from "./Chart";
import { Loading } from "./Loading";
import { Term } from "./Term";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

interface Classifier {
  rows: number;
  auc: number;
  accuracy: number;
  confusion: { tn: number; fp: number; fn: number; tp: number };
  roc: { x: number; y: number }[];
  importances: { feature: string; weight: number }[];
}

/** ROC with the coin-flip diagonal drawn, because that is the comparison. */
function RocChart({ roc, label }: { roc: { x: number; y: number }[]; label: string }) {
  return (
    <LineChart
      height={240}
      series={[
        { label, color: "var(--ai)", points: roc },
        {
          label: "Random guessing",
          color: "var(--muted)",
          dashed: true,
          points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
        },
      ]}
      formatX={(v) => v.toFixed(1)}
      formatY={(v) => v.toFixed(1)}
      yLabel="True positive rate"
    />
  );
}

function Stat({
  label,
  value,
  tone,
  term,
}: {
  label: string;
  value: string;
  tone?: string;
  /** Glossary id, when the label is jargon. */
  term?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {term ? <Term id={term}>{label}</Term> : label}
      </div>
      <div className="metric-value" style={tone ? { color: tone } : undefined}>{value}</div>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Churn extends Classifier {
  churn_rate: number;
  precision: number;
  recall: number;
  by_contract: { label: string; rate: number; count: number }[];
  scores: { p: number; y: number }[];
}

export function ChurnDemo() {
  const data = useDemoData<Churn>(() => import("../../data/demos/nb-churn.json"));
  const [threshold, setThreshold] = useState(0.5);
  if (!data) return <Loading label="Loading churn results…" />;

  // Recomputed in the browser from the stored per-customer scores. The
  // threshold is a business decision, not a property of the model, and 0.5 is
  // only a default -- so it is the control rather than a fixed number.
  let tp = 0, fp = 0, tn = 0, fn = 0;
  for (const { p, y } of data.scores) {
    const flagged = p >= threshold;
    if (y === 1) flagged ? tp++ : fn++;
    else flagged ? fp++ : tn++;
  }
  const recall = tp + fn ? tp / (tp + fn) : 0;
  const precision = tp + fp ? tp / (tp + fp) : 0;
  const accuracy = (tp + tn) / data.scores.length;
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0;

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Customers" value={data.rows.toLocaleString()} />
        <Stat label="Actually churned" value={pct(data.churn_rate)} />
        <Stat label="ROC AUC" term="auc" value={data.auc.toFixed(3)} tone="var(--se)" />
      </div>

      <div className="range" style={{ marginTop: 14 }}>
        <span className="control-label">
          Flag a customer as at-risk above <strong>{threshold.toFixed(2)}</strong>{" "}
          <Term id="threshold">decision threshold</Term>
        </span>
        <input
          type="range" min={0.05} max={0.95} step={0.01} value={threshold}
          aria-label="Decision threshold"
          onChange={(e) => setThreshold(Number(e.target.value))}
        />
        <div className="demo-controls" style={{ marginTop: 6 }}>
          <div className="control">
            <span className="control-label">Jump to</span>
            {[
              { v: 0.5, l: "Default (0.50)" },
              { v: 0.3, l: "Catch more" },
              { v: 0.7, l: "Be certain" },
            ].map((s) => (
              <button
                key={s.l} className="chip"
                aria-pressed={Math.abs(threshold - s.v) < 0.005}
                onClick={() => setThreshold(s.v)}
              >
                {s.l}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="metric-row">
        <Stat label="Recall — churners caught" term="recall" value={pct(recall)} tone="var(--se)" />
        <Stat label="Precision — flags that were right" term="precision" value={pct(precision)} tone="var(--ai)" />
        <Stat label="F1" term="f1" value={f1.toFixed(3)} />
        <Stat label="Accuracy" term="accuracy" value={pct(accuracy)} />
        <Stat label="Customers flagged" value={(tp + fp).toLocaleString()} />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        Drag the threshold and watch recall and precision move against each other.
        This is the decision the model does not make for you: lower it to catch more
        of the people who will actually leave, at the cost of contacting more who
        would have stayed. At {threshold.toFixed(2)} you reach {pct(recall)} of the
        churners and {pct(precision)} of your outreach lands on someone who really
        was leaving. Accuracy barely moves across the whole range, which is why it
        is the wrong number to optimise — only {pct(data.churn_rate)} of customers
        churn, so predicting "nobody leaves" already scores {pct(1 - data.churn_rate)}.
      </p>

      <div className="demo-split">
        <div>
          <h5 className="demo-h">ROC curve — every threshold at once</h5>
          <RocChart roc={data.roc} label="Random forest" />
        </div>
        <div>
          <h5 className="demo-h">
            At this threshold — <Term id="confusion-matrix" />
          </h5>
          <ConfusionMatrix tn={tn} fp={fp} fn={fn} tp={tp}
                           positiveLabel="churn" negativeLabel="stay" />
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 18 }}>Churn rate by contract</h5>
      <BarChart
        bars={data.by_contract.map((c) => ({
          label: c.label,
          value: c.rate,
          note: `${c.count.toLocaleString()} customers`,
          color: c.rate > 0.3 ? "var(--ds)" : "var(--se)",
        }))}
        formatValue={pct}
      />
      <p className="demo-note">
        The strongest single signal in the dataset, and it needs no model:
        month-to-month customers churn at {pct(data.by_contract[0].rate)} against{" "}
        {pct(data.by_contract[data.by_contract.length - 1].rate)} on the longest
        contract.
      </p>

      <h5 className="demo-h" style={{ marginTop: 18 }}>What the model leans on</h5>
      <BarChart
        bars={data.importances.map((f) => ({ label: f.feature, value: f.weight }))}
        formatValue={(v) => v.toFixed(3)}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Article {
  title: string;
  author: string;
  source: string;
  category: string;
  date: string;
  excerpt: string;
  words: number;
  readability: number;
  sentiment: number;
  actual: string;
  predicted: string;
  score: number;
}

interface FakeNews extends Classifier {
  fake_rate: number;
  sample: Article[];
  feature_corr: { feature: string; corr: number }[];
  rate_by: Record<string, { label: string; rate: number; n: number }[]>;
  distinct_titles: number | null;
}

type ArticleFilter = "all" | "wrong" | "fake" | "real";

export function FakeNewsDemo() {
  const data = useDemoData<FakeNews>(() => import("../../data/demos/nb-fakenews.json"));
  const [filter, setFilter] = useState<ArticleFilter>("all");
  const [index, setIndex] = useState(0);
  const [groupBy, setGroupBy] = useState("source");
  if (!data) return <Loading label="Loading classifier results…" />;

  const shown = data.sample.filter((a) =>
    filter === "all" ? true
    : filter === "wrong" ? a.actual !== a.predicted
    : a.actual === filter,
  );
  const article = shown[Math.min(index, shown.length - 1)];

  const maxCorr = Math.max(...data.feature_corr.map((f) => Math.abs(f.corr)));
  const rates = data.rate_by[groupBy] ?? [];
  const spread = rates.length ? rates[0].rate - rates[rates.length - 1].rate : 0;

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Articles" value={data.rows.toLocaleString()} />
        <Stat label="Labelled fake" value={pct(data.fake_rate)} />
        <Stat label="ROC AUC" term="auc" value={data.auc.toFixed(3)} tone="var(--ds)" />
        <Stat label="Accuracy" term="accuracy" value={pct(data.accuracy)} />
      </div>

      <p className="demo-warn">
        <strong>No model can beat chance here, and the reason is the dataset.</strong>{" "}
        An AUC of {data.auc.toFixed(2)} is at or below the 0.50 a coin flip scores.
        That has two possible causes — uninformative features, or uninformative
        labels — and the evidence below points at the labels. Read a few articles
        and the problem is visible without any statistics.
      </p>

      <h5 className="demo-h">Read the articles being classified</h5>
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Show</span>
          {([
            ["all", "All"],
            ["wrong", "Misclassified"],
            ["fake", "Labelled fake"],
            ["real", "Labelled real"],
          ] as [ArticleFilter, string][]).map(([id, label]) => (
            <button
              key={id} className="chip" aria-pressed={filter === id}
              onClick={() => { setFilter(id); setIndex(0); }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="control">
          <button className="chip" onClick={() => setIndex((i) => Math.max(0, i - 1))}
                  disabled={index === 0}>
            ‹ Prev
          </button>
          <span className="demo-hint">
            {shown.length ? index + 1 : 0} of {shown.length}
          </span>
          <button className="chip"
                  onClick={() => setIndex((i) => Math.min(shown.length - 1, i + 1))}
                  disabled={index >= shown.length - 1}>
            Next ›
          </button>
        </div>
      </div>

      {article ? (
        <article className="article-card">
          <header>
            <h4>{article.title}</h4>
            <div className="article-meta">
              <span>{article.source}</span>
              <span>{article.category}</span>
              <span>{article.author}</span>
              <span>{article.date}</span>
            </div>
          </header>
          <p className="article-body">{article.excerpt}</p>
          <div className="article-verdicts">
            <span className={`verdict ${article.actual}`}>
              labelled <strong>{article.actual}</strong>
            </span>
            <span className={`verdict ${article.predicted}`}>
              model said <strong>{article.predicted}</strong> ({article.score.toFixed(2)})
            </span>
            <span className={article.actual === article.predicted ? "tag-hit" : "tag-evict"}>
              {article.actual === article.predicted ? "correct" : "wrong"}
            </span>
            <span className="muted mono">
              {article.words} words · readability {article.readability} · sentiment{" "}
              {article.sentiment}
            </span>
          </div>
        </article>
      ) : (
        <p className="empty">Nothing matches that filter.</p>
      )}

      <p className="demo-note">
        Every title is "Breaking News N" and every body is the same sentence with the
        article number substituted in. There is nothing here to read, because the
        corpus is generated rather than collected — {data.distinct_titles?.toLocaleString()}{" "}
        distinct titles for {data.rows.toLocaleString()} rows, all of the same
        template. A classifier cannot find a pattern that was never written in.
      </p>

      <h5 className="demo-h" style={{ marginTop: 20 }}>
        The labels look randomly assigned
      </h5>
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Fake rate by</span>
          {Object.keys(data.rate_by).map((k) => (
            <button key={k} className="chip" aria-pressed={groupBy === k}
                    onClick={() => setGroupBy(k)}>
              {k}
            </button>
          ))}
        </div>
      </div>
      <BarChart
        bars={rates.map((r) => ({
          label: r.label,
          value: r.rate,
          note: `${r.n} articles`,
          color: "var(--ds)",
        }))}
        maxBars={14}
        formatValue={pct}
      />
      <p className="demo-note">
        If the labels meant anything, satire and wire services would sit at opposite
        ends. Instead every {groupBy} lands within {pct(spread)} of a coin flip — The
        Onion and Reuters are both about half fake. The strongest correlation between
        any feature and the label is {maxCorr.toFixed(3)}, which is noise.
      </p>

      <div className="demo-split" style={{ marginTop: 18 }}>
        <div>
          <h5 className="demo-h">ROC curve</h5>
          <RocChart roc={data.roc} label="Metadata features" />
        </div>
        <div>
          <h5 className="demo-h">Where it is wrong</h5>
          <ConfusionMatrix {...data.confusion} positiveLabel="fake" negativeLabel="real" />
        </div>
      </div>

      <p className="demo-note">
        The useful conclusion is about the data, not the model. Any accuracy reported
        on this dataset — including the {pct(data.accuracy)} above — is measuring
        nothing, and a write-up that quoted it without checking would have been
        confidently wrong. Real signal needs a corpus of real articles.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Threats {
  rows: number;
  years: number[];
  points: {
    x: number; y: number; c: number; o: boolean;
    t: string; i: string; yr: number; loss: number;
  }[];
  industries: string[];
  attack_types: string[];
  by_type: { label: string; count: number }[];
  loss_by_industry: { label: string; value: number }[];
  by_year: { year: number; count: number }[];
  outlier_count: number;
}

const CLUSTER_COLORS = ["var(--ai)", "var(--ds)", "var(--se)", "var(--dv4)"];

export function ThreatsDemo() {
  const data = useDemoData<Threats>(() => import("../../data/demos/nb-threats.json"));
  const [mode, setMode] = useState<"cluster" | "anomaly">("cluster");
  const [attack, setAttack] = useState<string | null>(null);
  const [industry, setIndustry] = useState<string | null>(null);
  const [minYear, setMinYear] = useState<number | null>(null);
  if (!data) return <Loading label="Loading 3,000 incidents…" />;

  const [firstYear, lastYear] = [data.years[0], data.years[1]];
  const from = minYear ?? firstYear;

  const visible = data.points.filter(
    (p) =>
      (!attack || p.t === attack) &&
      (!industry || p.i === industry) &&
      p.yr >= from,
  );

  const label = (p: Threats["points"][number]) =>
    `${p.t} · ${p.i} · ${p.yr} · $${p.loss}M`;

  const groups: ScatterGroup[] =
    mode === "cluster"
      ? CLUSTER_COLORS.map((color, i) => ({
          label: `Cluster ${i + 1}`,
          color,
          points: visible
            .filter((p) => p.c === i)
            .map((p) => ({ x: p.x, y: p.y, note: label(p) })),
        }))
      : [
          {
            label: "Typical",
            color: "var(--muted)",
            points: visible.filter((p) => !p.o).map((p) => ({ x: p.x, y: p.y, note: label(p) })),
          },
          {
            label: "Flagged anomalous",
            color: "var(--ds)",
            points: visible.filter((p) => p.o).map((p) => ({ x: p.x, y: p.y, note: label(p) })),
          },
        ];

  const avgLoss = visible.length
    ? visible.reduce((sum, p) => sum + p.loss, 0) / visible.length
    : 0;

  return (
    <div className="demo">
      <p className="demo-hint" style={{ margin: "0 0 10px" }}>
        Two unsupervised methods over the same incidents:{" "}
        <Term id="clustering">clustering</Term> groups them by similarity, and{" "}
        <Term id="anomaly" /> flags the ones that look unlike the rest. Both axes
        are <Term id="pca">principal components</Term>.
      </p>
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Colour by</span>
          <button className="chip" aria-pressed={mode === "cluster"}
                  onClick={() => setMode("cluster")}>
            K-Means cluster
          </button>
          <button className="chip" aria-pressed={mode === "anomaly"}
                  onClick={() => setMode("anomaly")}>
            Isolation Forest anomaly
          </button>
        </div>
        {(attack || industry || minYear) && (
          <button
            className="chip"
            onClick={() => { setAttack(null); setIndustry(null); setMinYear(null); }}
          >
            Clear filters
          </button>
        )}
      </div>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Attack</span>
          {data.attack_types.map((t) => (
            <button key={t} className="chip" aria-pressed={attack === t}
                    onClick={() => setAttack(attack === t ? null : t)}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Industry</span>
          {data.industries.map((t) => (
            <button key={t} className="chip" aria-pressed={industry === t}
                    onClick={() => setIndustry(industry === t ? null : t)}>
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="range">
        <span className="control-label">
          From <strong>{from}</strong> to {lastYear}
        </span>
        <input
          type="range" min={firstYear} max={lastYear} value={from}
          aria-label="Earliest year"
          onChange={(e) => setMinYear(Number(e.target.value))}
        />
      </div>

      <div className="metric-row">
        <Stat label="Incidents shown" value={visible.length.toLocaleString()} />
        <Stat label="of total" value={data.rows.toLocaleString()} />
        <Stat label="Average loss" value={`$${avgLoss.toFixed(1)}M`} />
        <Stat
          term="anomaly"
          label="Flagged anomalous"
          value={String(visible.filter((p) => p.o).length)}
          tone="var(--ds)"
        />
      </div>

      <ScatterChart
        groups={groups}
        height={340}
        xLabel="First principal component"
        yLabel="Second principal component"
        formatX={(v) => v.toFixed(1)}
        formatY={(v) => v.toFixed(1)}
      />

      <p className="demo-note" style={{ marginTop: 0 }}>
        Four numeric fields — financial loss, users affected, resolution time, year —
        standardised and projected onto two principal components. Filter by attack
        type or industry and the points stay spread across every cluster: the
        grouping tracks how costly and how long an incident was, not what kind of
        attack it was. The clusters separate cleanly on these axes, which is close
        to tautological, since K-Means was handed the same four columns PCA was.
      </p>

      <div className="demo-split" style={{ marginTop: 16 }}>
        <div>
          <h5 className="demo-h">Average loss by target industry ($M)</h5>
          <BarChart
            bars={data.loss_by_industry.map((d) => ({
              label: d.label, value: d.value,
              color: industry && d.label !== industry ? "var(--edge)" : "var(--ai)",
            }))}
            formatValue={(v) => `$${v.toFixed(1)}M`}
          />
        </div>
        <div>
          <h5 className="demo-h">Incidents by attack type</h5>
          <BarChart
            bars={data.by_type.map((d) => ({
              label: d.label, value: d.count,
              color: attack && d.label !== attack ? "var(--edge)" : "var(--se)",
            }))}
            formatValue={(v) => String(Math.round(v))}
          />
        </div>
      </div>
      <p className="demo-note">
        Average loss lands between roughly $50M and $53M across all seven industries,
        and incident counts are near-uniform across the six attack types. That
        flatness is itself the finding: this dataset does not separate industries by
        risk the way you would expect real incident data to.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Recommend {
  customers: number;
  products: number;
  segments: { label: string; count: number }[];
  by_category: { label: string; count: number; rating: number; price: number }[];
  spend_by_segment: { label: string; value: number }[];
  interest_by_segment: Record<string, { label: string; share: number }[]>;
}

export function RecommendDemo() {
  const data = useDemoData<Recommend>(() => import("../../data/demos/nb-recommend.json"));
  const [metric, setMetric] = useState<"count" | "rating" | "price">("count");
  const [segment, setSegment] = useState<string | null>(null);
  if (!data) return <Loading label="Loading catalogue…" />;

  const format =
    metric === "price"
      ? (v: number) => `$${v.toFixed(2)}`
      : metric === "rating"
        ? (v: number) => v.toFixed(2)
        : (v: number) => String(Math.round(v));

  const segments = Object.keys(data.interest_by_segment);
  const interest = segment ? data.interest_by_segment[segment] : null;

  // How far apart the segments actually are on spend. The recommender's
  // premise is that the segment label tells you something.
  const spends = data.spend_by_segment.map((s) => s.value);
  const spread = Math.max(...spends) - Math.min(...spends);
  const spreadPct = spread / (Math.min(...spends) || 1);

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Customers" value={data.customers.toLocaleString()} />
        <Stat label="Products" value={data.products.toLocaleString()} />
        <Stat label="Categories" value={String(data.by_category.length)} />
        <Stat
          label="Spend spread across segments"
          value={`${(spreadPct * 100).toFixed(1)}%`}
          tone={spreadPct < 0.1 ? "var(--ds)" : undefined}
        />
      </div>

      <p className="demo-warn">
        The three segments differ by only {(spreadPct * 100).toFixed(1)}% in average
        order value. That is the first thing to check before building on a
        segmentation, and here it does not hold up: the label barely predicts what a
        customer spends, so a recommender leaning on it is leaning on very little.
        Browsing and purchase history have to carry the work.
      </p>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Segment</span>
          {segments.map((name) => (
            <button key={name} className="chip" aria-pressed={segment === name}
                    onClick={() => setSegment(segment === name ? null : name)}>
              {name}
            </button>
          ))}
        </div>
      </div>

      {interest ? (
        <>
          <h5 className="demo-h">What {segment} customers browse</h5>
          <BarChart
            bars={interest.map((i) => ({ label: i.label, value: i.share }))}
            formatValue={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <p className="demo-note">
            Compare this against another segment — the browsing mix is nearly
            identical, which is the same conclusion the spend figures reach from a
            different direction.
          </p>
        </>
      ) : (
        <>
          <h5 className="demo-h">Average order value by segment</h5>
          <BarChart
            bars={data.spend_by_segment.map((s) => ({
              label: s.label, value: s.value, color: "var(--se)",
            }))}
            formatValue={(v) => `$${v.toFixed(0)}`}
          />
        </>
      )}

      <div className="demo-controls" style={{ marginTop: 18 }}>
        <div className="control">
          <span className="control-label">Catalogue by</span>
          {(["count", "rating", "price"] as const).map((m) => (
            <button key={m} className="chip" aria-pressed={metric === m}
                    onClick={() => setMetric(m)}>
              {m === "count" ? "Products" : m === "rating" ? "Avg rating" : "Avg price"}
            </button>
          ))}
        </div>
      </div>

      <BarChart
        bars={data.by_category.map((c) => ({
          label: c.label,
          value: c[metric],
          note: `${c.count} products, avg rating ${c.rating}`,
        }))}
        formatValue={format}
      />
    </div>
  );
}
