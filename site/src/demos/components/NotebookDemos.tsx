import { useState } from "react";

import { useDemoData } from "../useDemoData";
import { BarChart, ConfusionMatrix, LineChart, ScatterChart, type ScatterGroup } from "./Chart";
import { Loading } from "./Loading";

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

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
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
}

export function ChurnDemo() {
  const data = useDemoData<Churn>(() => import("../../data/demos/nb-churn.json"));
  if (!data) return <Loading label="Loading churn results…" />;

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Customers" value={data.rows.toLocaleString()} />
        <Stat label="Actually churned" value={pct(data.churn_rate)} />
        <Stat label="ROC AUC" value={data.auc.toFixed(3)} tone="var(--se)" />
        <Stat label="Accuracy" value={pct(data.accuracy)} />
        <Stat label="Recall" value={pct(data.recall)} tone="var(--ds)" />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        An AUC of {data.auc.toFixed(2)} means the model ranks a churner above a
        non-churner about {pct(data.auc)} of the time. Accuracy of {pct(data.accuracy)}{" "}
        sounds better than it is — only {pct(data.churn_rate)} of customers churn, so
        predicting "nobody leaves" would already score {pct(1 - data.churn_rate)}. The
        number that matters is recall: at the default threshold it catches{" "}
        {pct(data.recall)} of the people who actually left.
      </p>

      <div className="demo-split">
        <div>
          <h5 className="demo-h">ROC curve</h5>
          <RocChart roc={data.roc} label="Random forest" />
        </div>
        <div>
          <h5 className="demo-h">Where it is wrong</h5>
          <ConfusionMatrix {...data.confusion} positiveLabel="churn" negativeLabel="stay" />
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
        The strongest single signal in the dataset, and it needs no model: month-to-month
        customers churn at {pct(data.by_contract[0].rate)} against{" "}
        {pct(data.by_contract[data.by_contract.length - 1].rate)} on the longest contract.
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

interface FakeNews extends Classifier {
  fake_rate: number;
}

export function FakeNewsDemo() {
  const data = useDemoData<FakeNews>(() => import("../../data/demos/nb-fakenews.json"));
  if (!data) return <Loading label="Loading classifier results…" />;

  const worthless = data.auc < 0.55;

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Articles" value={data.rows.toLocaleString()} />
        <Stat label="Labelled fake" value={pct(data.fake_rate)} />
        <Stat
          label="ROC AUC"
          value={data.auc.toFixed(3)}
          tone={worthless ? "var(--ds)" : "var(--se)"}
        />
        <Stat label="Accuracy" value={pct(data.accuracy)} />
      </div>

      {worthless && (
        <p className="demo-warn">
          <strong>This model does not work, and that is the finding.</strong> An AUC of{" "}
          {data.auc.toFixed(2)} is at or below the 0.50 a coin flip scores — the metadata
          in this dataset carries no usable signal about whether an article is fake. The
          curve below sits on the diagonal rather than bowing above it. Reporting the
          accuracy figure alone would have made it look like a working classifier;
          on a near 50/50 split, {pct(data.accuracy)} accuracy is noise.
        </p>
      )}

      <div className="demo-split">
        <div>
          <h5 className="demo-h">ROC curve</h5>
          <RocChart roc={data.roc} label="Metadata features" />
        </div>
        <div>
          <h5 className="demo-h">Where it is wrong</h5>
          <ConfusionMatrix {...data.confusion} positiveLabel="fake" negativeLabel="real" />
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 18 }}>
        Feature importance — high ranks here mean nothing when the model has no skill
      </h5>
      <BarChart
        bars={data.importances.map((f) => ({
          label: f.feature,
          value: f.weight,
          color: "var(--muted)",
        }))}
        formatValue={(v) => v.toFixed(3)}
      />
      <p className="demo-note">
        A random forest always ranks its inputs, whether or not any of them predict
        anything. These weights describe how the trees split, not evidence that
        readability or word count reveals a fake article. Getting real signal here needs
        the article text — TF-IDF over the body — not the metadata around it.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Threats {
  rows: number;
  years: number[];
  points: { x: number; y: number; c: number; o: boolean; t: string }[];
  by_type: { label: string; count: number }[];
  loss_by_industry: { label: string; value: number }[];
  by_year: { year: number; count: number }[];
  outlier_count: number;
}

const CLUSTER_COLORS = ["var(--ai)", "var(--ds)", "var(--se)", "var(--dv4)"];

export function ThreatsDemo() {
  const data = useDemoData<Threats>(() => import("../../data/demos/nb-threats.json"));
  const [mode, setMode] = useState<"cluster" | "anomaly">("cluster");
  if (!data) return <Loading label="Loading 3,000 incidents…" />;

  const groups: ScatterGroup[] =
    mode === "cluster"
      ? CLUSTER_COLORS.map((color, i) => ({
          label: `Cluster ${i + 1}`,
          color,
          points: data.points
            .filter((p) => p.c === i)
            .map((p) => ({ x: p.x, y: p.y, note: p.t })),
        }))
      : [
          {
            label: "Typical",
            color: "var(--muted)",
            points: data.points.filter((p) => !p.o).map((p) => ({ x: p.x, y: p.y, note: p.t })),
          },
          {
            label: `Flagged anomalous (${data.outlier_count})`,
            color: "var(--ds)",
            points: data.points.filter((p) => p.o).map((p) => ({ x: p.x, y: p.y, note: p.t })),
          },
        ];

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Incidents" value={data.rows.toLocaleString()} />
        <Stat label="Years" value={`${data.years[0]}–${data.years[1]}`} />
        <Stat label="Attack types" value={String(data.by_type.length)} />
        <Stat label="Flagged anomalous" value={String(data.outlier_count)} tone="var(--ds)" />
      </div>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Colour by</span>
          <button className="chip" aria-pressed={mode === "cluster"} onClick={() => setMode("cluster")}>
            K-Means cluster
          </button>
          <button className="chip" aria-pressed={mode === "anomaly"} onClick={() => setMode("anomaly")}>
            Isolation Forest anomaly
          </button>
        </div>
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
        standardised and projected onto two principal components. The clusters separate
        cleanly on those axes, but that is close to tautological: K-Means was given the
        same four columns PCA was. The honest reading is that incidents vary mostly
        along cost and duration, not that four natural kinds of attack were discovered.
      </p>

      <div className="demo-split" style={{ marginTop: 16 }}>
        <div>
          <h5 className="demo-h">Average loss by target industry ($M)</h5>
          <BarChart
            bars={data.loss_by_industry.map((d) => ({ label: d.label, value: d.value }))}
            formatValue={(v) => `$${v.toFixed(1)}M`}
          />
        </div>
        <div>
          <h5 className="demo-h">Incidents by attack type</h5>
          <BarChart
            bars={data.by_type.map((d) => ({
              label: d.label,
              value: d.count,
              color: "var(--se)",
            }))}
            formatValue={(v) => String(Math.round(v))}
          />
        </div>
      </div>
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
}

export function RecommendDemo() {
  const data = useDemoData<Recommend>(() => import("../../data/demos/nb-recommend.json"));
  const [metric, setMetric] = useState<"count" | "rating" | "price">("count");
  if (!data) return <Loading label="Loading catalogue…" />;

  const format =
    metric === "price"
      ? (v: number) => `$${v.toFixed(2)}`
      : metric === "rating"
        ? (v: number) => v.toFixed(2)
        : (v: number) => String(Math.round(v));

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Customers" value={data.customers.toLocaleString()} />
        <Stat label="Products" value={data.products.toLocaleString()} />
        <Stat label="Segments" value={String(data.segments.length)} />
        <Stat label="Categories" value={String(data.by_category.length)} />
      </div>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">By category</span>
          {(["count", "rating", "price"] as const).map((m) => (
            <button key={m} className="chip" aria-pressed={metric === m} onClick={() => setMetric(m)}>
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

      <h5 className="demo-h" style={{ marginTop: 18 }}>Average order value by segment</h5>
      <BarChart
        bars={data.spend_by_segment.map((s) => ({
          label: s.label,
          value: s.value,
          color: "var(--se)",
        }))}
        formatValue={(v) => `$${v.toFixed(0)}`}
      />

      <p className="demo-note">
        Customer segments are near-evenly sized and average order value barely separates
        them, which is the first thing worth knowing: the segmentation in this dataset
        carries little spending signal, so a recommender built on it has to lean on
        browsing and purchase history rather than the segment label.
      </p>
    </div>
  );
}
