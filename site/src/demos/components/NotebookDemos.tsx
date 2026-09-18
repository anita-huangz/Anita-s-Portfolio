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
  censoring_rate: number;
  precision: number;
  recall: number;
  by_contract: { label: string; rate: number; count: number }[];
  scores: { p: number; y: number }[];
  survival: {
    months: number[];
    overall: number[];
    lower: number[];
    upper: number[];
    by_contract: { label: string; count: number; survival: number[] }[];
    restricted_mean_60: number;
    logrank_chi2: number;
    concordance: number;
  };
  hazard_ratios: { name: string; hr: number; lower: number; upper: number }[];
  calibration: Record<
    "balanced" | "unweighted",
    {
      auc: number;
      mean_predicted: number;
      ece: number;
      skill: number;
      bins: { predicted: number; observed: number; count: number }[];
    }
  >;
  economics: {
    offer_cost: number;
    acceptance: number;
    margin: number;
    horizon: number;
    median_value: number;
    best_threshold: number;
    curve: { t: number; value: number; targeted: number }[];
    policies: Record<string, number>;
  };
}

const CONTRACT_COLOUR: Record<string, string> = {
  "Month-to-month": "var(--ds)",
  "One year": "var(--ai)",
  "Two year": "var(--se)",
};

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

      <h5 className="demo-h" style={{ marginTop: 22 }}>
        Survival — what the classifier above cannot see
      </h5>
      <p className="demo-hint" style={{ margin: "0 0 10px" }}>
        {pct(data.censoring_rate)} of these customers had not left when the
        data was cut. Their lifetime is not "no churn", it is <em>at least</em>{" "}
        their current tenure — and a classifier reads a one-month customer who
        stayed and a six-year customer who stayed as the same row.
      </p>
      <LineChart
        series={[
          {
            label: "All customers",
            color: "var(--muted)",
            points: data.survival.months.map((m, i) => ({
              x: m,
              y: data.survival.overall[i],
            })),
          },
          ...data.survival.by_contract.map((c) => ({
            label: c.label,
            color: CONTRACT_COLOUR[c.label] ?? "var(--ai)",
            points: data.survival.months.map((m, i) => ({
              x: m,
              y: c.survival[i],
            })),
          })),
        ]}
        formatY={(v) => pct(v)}
        formatX={(v) => `${Math.round(v)}m`}
        yLabel="Still a customer"
        height={240}
      />
      <div className="metric-row">
        <Stat
          label="Median lifetime"
          value="not reached"
          tone="var(--ds)"
        />
        <Stat
          label="Months retained of the next 60"
          value={data.survival.restricted_mean_60.toFixed(1)}
        />
        <Stat
          label="Concordance (survival)"
          term="auc"
          value={data.survival.concordance.toFixed(3)}
          tone="var(--se)"
        />
        <Stat label="ROC AUC (classifier)" term="auc" value={data.auc.toFixed(3)} />
      </div>
      <p className="demo-note">
        <strong>The median is undefined, and that is the right answer</strong> —
        more than half are still subscribed at the end of the window, so it has
        not happened yet. The restricted mean is the summary that is
        answerable. Ranking by the survival model beats the classifier{" "}
        ({data.survival.concordance.toFixed(3)} against {data.auc.toFixed(3)})
        because it can see <em>when</em> people left. Kaplan-Meier, the
        log-rank test (χ² = {data.survival.logrank_chi2.toLocaleString()}) and
        Cox regression are implemented from scratch and checked against
        statsmodels to 1e-8.
      </p>

      <h5 className="demo-h" style={{ marginTop: 18 }}>
        Hazard ratios — the multiplier on the monthly risk of leaving
      </h5>
      <BarChart
        bars={data.hazard_ratios.map((h) => ({
          label: h.name.replace(/_/g, " "),
          value: h.hr,
          note: `95% CI [${h.lower}, ${h.upper}]`,
          color: h.hr > 1 ? "var(--ds)" : "var(--se)",
        }))}
        formatValue={(v) => `${v.toFixed(2)}x`}
      />
      <p className="demo-note">
        Below 1 is safer, above 1 is riskier. Each step up in contract length
        multiplies the monthly risk by {data.hazard_ratios[0].hr} — a five-fold
        reduction. <strong>The proportional-hazards assumption fails for 16 of
        the 20 covariates</strong>, so these are averages over effects that
        change with tenure. Reported rather than buried: it is the caveat that
        belongs next to the table, not in a footnote.
      </p>

      <h5 className="demo-h" style={{ marginTop: 18 }}>
        Rebalancing destroys the probabilities and AUC never notices
      </h5>
      <div className="metric-row">
        <Stat
          label="AUC, balanced"
          value={data.calibration.balanced.auc.toFixed(4)}
        />
        <Stat
          label="AUC, unweighted"
          value={data.calibration.unweighted.auc.toFixed(4)}
        />
        <Stat
          label="Calibration error, balanced"
          value={data.calibration.balanced.ece.toFixed(3)}
          tone="var(--ds)"
        />
        <Stat
          label="Calibration error, unweighted"
          value={data.calibration.unweighted.ece.toFixed(3)}
          tone="var(--se)"
        />
      </div>
      <LineChart
        series={[
          {
            label: "Perfect",
            color: "var(--muted)",
            points: [
              { x: 0, y: 0 },
              { x: 1, y: 1 },
            ],
          },
          {
            label: "class_weight=balanced",
            color: "var(--ds)",
            points: data.calibration.balanced.bins.map((b) => ({
              x: b.predicted,
              y: b.observed,
            })),
          },
          {
            label: "unweighted",
            color: "var(--se)",
            points: data.calibration.unweighted.bins.map((b) => ({
              x: b.predicted,
              y: b.observed,
            })),
          },
        ]}
        formatY={pct}
        formatX={pct}
        yLabel="Actually churned"
        height={230}
      />
      <p className="demo-note">
        Rebalancing — which is what SMOTE does, and the original notebook used
        it — changed the ranking by <strong>0.0001 of AUC</strong> and made the
        probabilities about twice too large. Customers the balanced model
        scores at 0.45 churn 22% of the time. AUC cannot see it, because it
        only asks whether churners outrank non-churners and is unchanged if you
        square every probability. That stops being harmless the moment the
        score is multiplied by a dollar amount.
      </p>

      <h5 className="demo-h" style={{ marginTop: 18 }}>
        The decision: who to call, and whether to call at all
      </h5>
      <LineChart
        series={[
          {
            label: "Net value of the campaign",
            color: "var(--ai)",
            points: data.economics.curve.map((r) => ({ x: r.t, y: r.value })),
          },
        ]}
        formatY={(v) => `$${Math.round(v / 1000)}k`}
        formatX={(v) => v.toFixed(2)}
        yLabel="Expected value"
        height={210}
      />
      <p className="demo-note">
        At ${data.economics.offer_cost} an offer,{" "}
        {pct(data.economics.acceptance)} accepting and{" "}
        {pct(data.economics.margin)} margin, the best cut-off is{" "}
        <strong>{data.economics.best_threshold}</strong>, not 0.5.{" "}
        <strong>0.5 has no claim on being right</strong> — it is only optimal
        when the two errors cost the same, and contacting a happy customer
        costs one discount while losing an unhappy one costs their whole
        remaining value.
      </p>
      <div className="metric-row">
        {["by_expected_value", "by_probability", "everyone", "random"].map((k) => (
          <Stat
            key={k}
            label={k.replace(/_/g, " ")}
            value={`$${(data.economics.policies[k] / 1000).toFixed(1)}k`}
            tone={k === "by_expected_value" ? "var(--se)" : undefined}
          />
        ))}
      </div>
      <p className="demo-note">
        The same budget of 1,000 calls, spent three ways.{" "}
        <strong>Ranking by probability × value returns 33% more</strong> than
        ranking by probability alone, because the value term needs to know how
        long each customer <em>would</em> have stayed — the area under their
        own survival curve, which a classifier cannot produce. "Will churn" is
        the same label for a customer with eight months left and one with four
        years.
      </p>

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

      <h5 className="demo-h" style={{ marginTop: 18 }}>
        What the model leans on — permutation importance
      </h5>
      <BarChart
        bars={data.importances.map((f) => ({ label: f.feature, value: f.weight }))}
        formatValue={(v) => v.toFixed(3)}
      />
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface FakeNews {
  rows: number;
  fake_rate: number;
  templates: {
    column: string;
    distinct: number;
    skeletons: number;
    templated: boolean;
    example: string;
  }[];
  observed_auc: number;
  boosted_auc: number;
  permutation: {
    draws: number;
    null_mean: number;
    null_std: number;
    low: number;
    high: number;
    z: number;
    p: number;
    distinguishable: boolean;
    histogram: { x: number; n: number }[];
  };
  power: { minimum_auc: number; power: number; summary: string };
  learning_curve: { n: number; auc: number }[];
  learning_slope: number;
  features: {
    feature: string;
    r: number;
    p: number;
    threshold: number;
    reject: boolean;
  }[];
  expected_false_positives: number;
}

export function FakeNewsDemo() {
  const data = useDemoData<FakeNews>(() => import("../../data/demos/nb-fakenews.json"));
  const [target, setTarget] = useState(0.55);
  if (!data) return <Loading label="Loading fake-news results…" />;

  const perm = data.permutation;
  const insideNull =
    data.observed_auc >= perm.low && data.observed_auc <= perm.high;

  // How many articles it would take to detect an effect of the size the reader
  // dials in. The detectable AUC scales as 1/sqrt(n) under the Hanley-McNeil
  // variance the package uses, so the required n scales as the square.
  const detectable = data.power.minimum_auc;
  const rowsNeeded = Math.ceil(
    data.rows * ((detectable - 0.5) / Math.max(target - 0.5, 1e-6)) ** 2,
  );

  const templated = data.templates.filter((t) => t.templated);
  const rejected = data.features.filter((f) => f.reject);
  const binWidth =
    perm.histogram.length > 1 ? perm.histogram[1].x - perm.histogram[0].x : 0.01;

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Articles" value={data.rows.toLocaleString()} />
        <Stat label="Labelled fake" value={pct(data.fake_rate)} />
        <Stat
          label="AUC achieved"
          term="auc"
          value={data.observed_auc.toFixed(4)}
          tone={insideNull ? "var(--ds)" : "var(--se)"}
        />
        <Stat
          label="Permutation p"
          term="p-value"
          value={perm.p.toFixed(4)}
          tone={perm.distinguishable ? "var(--se)" : "var(--ds)"}
        />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        <strong>There is no signal here, and that is the finding.</strong> The
        classifier reaches AUC {data.observed_auc.toFixed(4)}. Shuffling the
        labels {perm.draws} times and refitting from scratch gives{" "}
        {perm.null_mean.toFixed(4)} ± {perm.null_std.toFixed(4)} — a model
        trained on <em>deliberately meaningless</em> labels scores the same. The
        real result sits {perm.z.toFixed(2)} standard deviations out, p ={" "}
        {perm.p.toFixed(4)}. Gradient boosting does not rescue it
        ({data.boosted_auc.toFixed(4)}).
      </p>

      <h5 className="demo-h">
        Observed against the <Term id="permutation-test">permutation null</Term>
      </h5>
      <BarChart
        maxBars={perm.histogram.length}
        bars={perm.histogram.map((b) => ({
          label: b.x.toFixed(3),
          value: b.n,
          color:
            Math.abs(b.x - data.observed_auc) <= binWidth
              ? "var(--ds)"
              : "var(--muted)",
          note: `${b.n} of ${perm.draws} shuffles scored near AUC ${b.x.toFixed(3)}`,
        }))}
        formatValue={(v) => `${v}`}
      />
      <p className="demo-hint">
        Each bar is one bin of the {perm.draws} shuffled refits; the highlighted
        bars bracket the real result. It is inside the crowd, not beyond it. The
        middle 95% of the null runs from {perm.low.toFixed(4)} to{" "}
        {perm.high.toFixed(4)}, and {data.observed_auc.toFixed(4)} is within it.
      </p>

      <div className="range" style={{ marginTop: 18 }}>
        <span className="control-label">
          Suppose the true AUC were <strong>{target.toFixed(2)}</strong> — could
          this study have found it?
        </span>
        <input
          type="range" min={0.51} max={0.8} step={0.01} value={target}
          aria-label="Hypothetical true AUC"
          onChange={(e) => setTarget(Number(e.target.value))}
        />
      </div>
      <div className="metric-row">
        <Stat
          label={`Detectable at n = ${data.rows.toLocaleString()}`}
          term="statistical-power"
          value={`AUC ≥ ${detectable.toFixed(3)}`}
        />
        <Stat
          label={`Articles needed for AUC ${target.toFixed(2)}`}
          value={
            target >= detectable
              ? `${data.rows.toLocaleString()} is enough`
              : `~${rowsNeeded.toLocaleString()}`
          }
          tone={target >= detectable ? "var(--se)" : "var(--ds)"}
        />
        <Stat label="Power" value={pct(data.power.power)} />
      </div>
      <p className="demo-hint">
        {data.power.summary}. "No signal found" and "not enough data to find
        one" are different claims, and only a power calculation separates them.
        An effect smaller than AUC {detectable.toFixed(3)} could be real and
        still invisible here — so the conclusion is bounded, not absolute.
      </p>

      <div className="demo-split" style={{ marginTop: 18 }}>
        <div>
          <h5 className="demo-h">
            <Term id="learning-curve">Learning curve</Term> — more data does not help
          </h5>
          <LineChart
            height={220}
            series={[
              {
                label: "Cross-validated AUC",
                color: "var(--ds)",
                points: data.learning_curve.map((p) => ({ x: p.n, y: p.auc })),
              },
              {
                label: "Coin flip",
                color: "var(--muted)",
                dashed: true,
                points: [
                  { x: data.learning_curve[0].n, y: 0.5 },
                  {
                    x: data.learning_curve[data.learning_curve.length - 1].n,
                    y: 0.5,
                  },
                ],
              },
            ]}
            formatX={(v) => v.toLocaleString()}
            formatY={(v) => v.toFixed(3)}
            yLabel="AUC"
          />
          <p className="demo-hint">
            {data.learning_slope >= 0 ? "+" : ""}
            {data.learning_slope.toFixed(4)} AUC per extra thousand articles. A
            model starved of data climbs as you feed it; this one is flat, which
            points at the data rather than the sample size.
          </p>
        </div>
        <div>
          <h5 className="demo-h">Every feature, tested individually</h5>
          <BarChart
            maxBars={data.features.length}
            bars={data.features.map((f) => ({
              label: f.feature,
              value: f.r,
              color: f.reject ? "var(--ds)" : "var(--muted)",
              note: `r = ${f.r.toFixed(4)}, p = ${f.p.toFixed(3)} against a threshold of ${f.threshold.toFixed(4)}`,
            }))}
            formatValue={(v) => v.toFixed(4)}
          />
          <p className="demo-hint">
            Correlation with the label for all {data.features.length} features,
            each judged against a{" "}
            <Term id="benjamini-hochberg">Benjamini-Hochberg</Term> threshold.{" "}
            {rejected.length === 0
              ? "None survive"
              : `${rejected.length} survive`}
            . Testing this many at 5% would throw up{" "}
            {data.expected_false_positives.toFixed(2)} false positives by chance,
            so one "significant" feature here would mean nothing on its own.
          </p>
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 22 }}>
        Why — the text is generated
      </h5>
      <div className="demo-table-wrap">
        <table className="demo-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Distinct values</th>
              <th>Distinct templates</th>
              <th>Example</th>
            </tr>
          </thead>
          <tbody>
            {data.templates.map((t) => (
              <tr key={t.column} className={t.templated ? "highlight" : undefined}>
                <td>{t.column}</td>
                <td>{t.distinct.toLocaleString()}</td>
                <td style={t.templated ? { color: "var(--ds)" } : undefined}>
                  {t.skeletons.toLocaleString()}
                </td>
                <td className="mono">{t.example}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="demo-note">
        {templated.length > 0 ? (
          <>
            <strong>
              {templated.map((t) => t.column).join(" and ")} collapse
              {templated.length === 1 ? "s" : ""} to{" "}
              {templated.map((t) => t.skeletons).join(" and ")} template
              {templated.length === 1 && templated[0].skeletons === 1 ? "" : "s"}
            </strong>{" "}
            once the digits are stripped out — {data.rows.toLocaleString()}{" "}
            "distinct" values are one sentence with a counter in it.
          </>
        ) : (
          <>The text columns show no obvious templating.</>
        )}{" "}
        There is no language here to learn from, and the labels were assigned
        independently of it. So the output of this project is not a classifier;
        it is a demonstration that the dataset cannot support one, backed by a
        permutation test, a power bound and a learning curve. Each of those is
        also run against a planted synthetic effect in the package's tests, so
        the method is shown to find signal when signal is there.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface Threats {
  rows: number;
  shown: number;
  columns: number;
  projection: {
    real: { x: number; y: number; c: number }[];
    shuffled: { x: number; y: number; c: number }[];
  };
  uniformity: { column: string; d: number; p: number }[];
  all_uniform: boolean;
  balance: { column: string; categories: number; chi2: number; p: number }[];
  balance_expected_false_positives: number;
  balance_consistent_with_chance: boolean;
  strongest_association: { pair: string; v: number };
  strongest_correlation: number;
  independent: boolean;
  silhouette: {
    observed: number;
    null_mean: number;
    null_std: number;
    z: number;
    p: number;
    draws: number;
    better_than_noise: boolean;
  };
  stability: { mean_ari: number; low: number; high: number; stable: boolean };
  gap: { k: number; gap: number; s_k: number }[];
  best_k: number;
  says_no_clusters: boolean;
  agreement: {
    flagged_a: number;
    flagged_b: number;
    overlap: number;
    expected: number;
    jaccard: number;
    excess: number;
    agree: boolean;
  };
  tails: { column: string; percentile: number; just_a_tail: boolean }[];
}

const CLUSTER_COLORS = ["var(--ai)", "var(--ds)", "var(--se)", "var(--dv4)"];

export function ThreatsDemo() {
  const data = useDemoData<Threats>(() => import("../../data/demos/nb-threats.json"));
  const [side, setSide] = useState<"both" | "real" | "shuffled">("both");
  if (!data) return <Loading label="Loading threat results…" />;

  const sil = data.silhouette;
  const gap = data.gap;

  /** k-means output on one of the two panels, coloured by assigned cluster. */
  const groups = (
    points: { x: number; y: number; c: number }[],
    prefix: string,
  ): ScatterGroup[] =>
    [0, 1, 2, 3].map((c) => ({
      label: `${prefix} cluster ${c + 1}`,
      color: CLUSTER_COLORS[c],
      points: points.filter((p) => p.c === c),
    }));

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Incidents" value={data.rows.toLocaleString()} />
        <Stat label="Encoded columns" value={String(data.columns)} />
        <Stat
          label="Silhouette"
          term="silhouette"
          value={sil.observed.toFixed(4)}
          tone={sil.better_than_noise ? "var(--se)" : "var(--ds)"}
        />
        <Stat
          label="Same on shuffled data"
          term="null-model"
          value={`${sil.null_mean.toFixed(4)} ± ${sil.null_std.toFixed(4)}`}
        />
        <Stat
          label="Clusters supported"
          term="gap-statistic"
          value={data.says_no_clusters ? "none (k = 1)" : `k = ${data.best_k}`}
          tone={data.says_no_clusters ? "var(--ds)" : "var(--se)"}
        />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        <strong>Both pictures below are the same picture.</strong> The left is
        the real data; the right is the same table with every column
        independently shuffled, which destroys any relationship between columns
        while keeping each column's distribution intact. k-means draws four
        tidy regions on each, because k-means always draws four tidy regions.
        The real silhouette is {sil.observed.toFixed(4)} against{" "}
        {sil.null_mean.toFixed(4)} on noise (p = {sil.p.toFixed(3)}, {sil.draws}{" "}
        draws) — it is, if anything, slightly worse.
      </p>

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Which projection to show">
          <span className="control-label">Show</span>
          {(["both", "real", "shuffled"] as const).map((m) => (
            <button
              key={m} className="chip" aria-pressed={side === m}
              onClick={() => setSide(m)}
            >
              {m === "both" ? "Side by side" : m === "real" ? "Real data" : "Shuffled"}
            </button>
          ))}
        </div>
      </div>

      <div className={side === "both" ? "demo-split" : undefined}>
        {side !== "shuffled" && (
          <div>
            <h5 className="demo-h">
              Real data — <Term id="pca">PCA</Term> projection, k-means colours
            </h5>
            <ScatterChart
              height={280}
              groups={groups(data.projection.real, "Real")}
              xLabel="Component 1"
              yLabel="Component 2"
              formatX={(v) => v.toFixed(1)}
              formatY={(v) => v.toFixed(1)}
            />
          </div>
        )}
        {side !== "real" && (
          <div>
            <h5 className="demo-h">Columns shuffled — structure destroyed</h5>
            <ScatterChart
              height={280}
              groups={groups(data.projection.shuffled, "Shuffled")}
              xLabel="Component 1"
              yLabel="Component 2"
              formatX={(v) => v.toFixed(1)}
              formatY={(v) => v.toFixed(1)}
            />
          </div>
        )}
      </div>
      <p className="demo-hint">
        {data.shown.toLocaleString()} of {data.rows.toLocaleString()} incidents
        drawn, sampled once so both panels are comparable.
      </p>

      <div className="demo-split" style={{ marginTop: 20 }}>
        <div>
          <h5 className="demo-h">
            <Term id="gap-statistic">Gap statistic</Term> — how many groups exist
          </h5>
          <LineChart
            height={220}
            series={[
              {
                label: "Gap",
                color: "var(--ds)",
                points: gap.map((g) => ({ x: g.k, y: g.gap })),
              },
            ]}
            formatX={(v) => `k=${v}`}
            formatY={(v) => v.toFixed(2)}
            yLabel="Gap over uniform reference"
          />
          <p className="demo-hint">
            The gap never rises, so Tibshirani's rule returns{" "}
            <strong>k = {data.best_k}</strong> — no clusters. This is the reason
            to use it over an elbow or silhouette plot, both of which are
            undefined at k = 1 and so structurally unable to report "there are
            no groups".
          </p>
        </div>
        <div>
          <h5 className="demo-h">
            <Term id="ari">Stability</Term> — do the groups survive resampling?
          </h5>
          <div className="metric-row" style={{ marginTop: 0 }}>
            <Stat
              label="Mean ARI across bootstraps"
              value={data.stability.mean_ari.toFixed(3)}
              tone={data.stability.stable ? "var(--se)" : "var(--ds)"}
            />
            <Stat
              label="95% range"
              term="confidence-interval"
              value={`${data.stability.low.toFixed(2)} – ${data.stability.high.toFixed(2)}`}
            />
          </div>
          <p className="demo-hint">
            Re-cluster a resampled copy of the data and compare the labels to
            the original. 1.0 would mean the same groups every time. At{" "}
            {data.stability.mean_ari.toFixed(3)}, with a range running from{" "}
            {data.stability.low.toFixed(2)} to {data.stability.high.toFixed(2)},
            the boundaries move whenever the data does — they are fitted to
            noise, not to structure.
          </p>
          <h5 className="demo-h" style={{ marginTop: 16 }}>
            Two outlier detectors, compared
          </h5>
          <div className="metric-row" style={{ marginTop: 0 }}>
            <Stat
              label="Both flagged"
              value={`${data.agreement.overlap} rows`}
            />
            <Stat
              label="Expected by chance"
              value={data.agreement.expected.toFixed(1)}
            />
            <Stat
              label="Excess over chance"
              value={`${data.agreement.excess.toFixed(1)}×`}
              tone={data.agreement.agree ? "var(--se)" : "var(--ds)"}
            />
          </div>
          <p className="demo-hint">
            Isolation Forest and Local Outlier Factor overlap{" "}
            {data.agreement.excess.toFixed(1)}× more than two unrelated
            detectors would. That rules out one of them being broken — it does
            not mean the flagged rows are anomalous. Both rank distance from the
            centre of the same cloud, so they agree on pure noise too.
          </p>
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 22 }}>
        Before clustering anything — is there structure to find?
      </h5>
      <div className="demo-table-wrap">
        <table className="demo-table">
          <thead>
            <tr>
              <th>Numeric column</th>
              <th><Term id="ks-test">Uniformity</Term> D</th>
              <th>p</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {data.uniformity.map((u) => (
              <tr key={u.column}>
                <td>{u.column}</td>
                <td>{u.d.toFixed(4)}</td>
                <td>{u.p.toFixed(3)}</td>
                <td className="dim">
                  {u.p > 0.05 ? "flat — cannot rule out a generator" : "not flat"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="demo-note">
        <strong>
          {data.all_uniform
            ? "Every numeric column is statistically flat across its range"
            : "Some columns are not flat"}
          , and the categorical ones are balanced
        </strong>{" "}
        ({data.balance.length} tested, {data.balance_expected_false_positives.toFixed(2)}{" "}
        rejections expected by chance alone, which is what was found). The
        strongest link between any two categorical columns is{" "}
        <Term id="cramers-v">Cramér's V</Term> ={" "}
        {data.strongest_association.v.toFixed(3)} (
        {data.strongest_association.pair}), and the strongest numeric
        correlation is {data.strongest_correlation.toFixed(4)}. Every column is
        independent of every other.
      </p>
      <p className="demo-note">
        That is the finding: this file was generated by drawing each column
        independently at random, so there is no structure for{" "}
        <Term id="clustering">clustering</Term> or{" "}
        <Term id="anomaly">anomaly detection</Term> to recover, and the tidy four-region scatter that a
        notebook would have shipped is an artefact of the algorithm. The point
        of the analysis is the null comparison that makes this visible — and
        the package's tests plant a real three-cluster structure to confirm the
        same machinery detects it (silhouette 0.807 against a null of 0.095)
        when it is there.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //

interface RankingScore {
  name: string;
  recall: number;
  precision: number;
  map: number;
  mrr: number;
  ndcg: number;
}

interface Recommend {
  customers: number;
  products: number;
  subcategories: number;
  cutoffs: number[];
  evaluated: number;
  excluded: number;
  by_k: Record<string, RankingScore[]>;
  browsing_leak: number;
  browsing_deterministic: boolean;
  similar_category_share: number;
  similar_category_chance: number;
  probability_correlations: { feature: string; r: number }[];
  popularity: { label: string; count: number }[];
}

type Metric = "recall" | "precision" | "map" | "mrr" | "ndcg";

const METRIC_LABEL: Record<Metric, string> = {
  recall: "Recall@k",
  precision: "Precision@k",
  map: "MAP",
  mrr: "MRR",
  ndcg: "NDCG",
};

const METRIC_TERM: Record<Metric, string> = {
  recall: "recall-at-k",
  precision: "precision-at-k",
  map: "map",
  mrr: "mrr",
  ndcg: "ndcg",
};

export function RecommendDemo() {
  const data = useDemoData<Recommend>(() => import("../../data/demos/nb-recommend.json"));
  const [k, setK] = useState(5);
  const [metric, setMetric] = useState<Metric>("recall");
  if (!data) return <Loading label="Loading recommendation results…" />;

  const scores = data.by_k[String(k)] ?? [];
  const oracle = scores.find((s) => s.name.includes("oracle"));
  const honest = scores.filter((s) => !s.name.includes("oracle"));
  const best = honest.reduce(
    (a, b) => (b[metric] > a[metric] ? b : a),
    honest[0],
  );
  const random = honest.find((s) => s.name === "random");

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Customers" value={data.customers.toLocaleString()} />
        <Stat label="Products" value={data.products.toLocaleString()} />
        <Stat
          label="Evaluated"
          term="leave-one-out"
          value={data.evaluated.toLocaleString()}
        />
        <Stat
          label="Excluded — only one purchase"
          value={data.excluded.toLocaleString()}
          tone="var(--ds)"
        />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        Every recommender below is scored the same way: hide one of a customer's
        purchases, rank the catalogue from what remains, and check whether the
        hidden item comes back in the top k. {data.excluded.toLocaleString()} of{" "}
        {data.customers.toLocaleString()} customers have only one purchase, so
        there is nothing to hold out and they are dropped — counting them would
        have quietly overstated the sample.
      </p>

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Cut-off k">
          <span className="control-label">Recommend the top</span>
          {data.cutoffs.map((c) => (
            <button
              key={c} className="chip" aria-pressed={k === c}
              onClick={() => setK(c)}
            >
              {c}
            </button>
          ))}
        </div>
        <div className="control" role="group" aria-label="Metric to rank by">
          <span className="control-label">Rank by</span>
          {(Object.keys(METRIC_LABEL) as Metric[]).map((m) => (
            <button
              key={m} className="chip" aria-pressed={metric === m}
              onClick={() => setMetric(m)}
            >
              {METRIC_LABEL[m]}
            </button>
          ))}
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 16 }}>
        <Term id={METRIC_TERM[metric]}>{METRIC_LABEL[metric]}</Term> at k = {k}
      </h5>
      <BarChart
        maxBars={scores.length}
        bars={scores.map((s) => ({
          label: s.name,
          value: s[metric],
          color: s.name.includes("oracle")
            ? "var(--ds)"
            : s === best
              ? "var(--se)"
              : "var(--muted)",
          note: `${s.name}: recall ${pct(s.recall)}, MAP ${s.map.toFixed(3)}, NDCG ${s.ndcg.toFixed(3)}`,
        }))}
        formatValue={(v) => v.toFixed(4)}
      />

      <div className="demo-table-wrap" style={{ marginTop: 14 }}>
        <table className="demo-table">
          <thead>
            <tr>
              <th>Recommender</th>
              <th><Term id="recall-at-k">Recall</Term></th>
              <th><Term id="precision-at-k">Precision</Term></th>
              <th><Term id="map">MAP</Term></th>
              <th><Term id="mrr">MRR</Term></th>
              <th><Term id="ndcg">NDCG</Term></th>
            </tr>
          </thead>
          <tbody>
            {scores.map((s) => (
              <tr
                key={s.name}
                className={s.name.includes("oracle") ? "highlight" : undefined}
              >
                <td>{s.name}</td>
                <td>{pct(s.recall)}</td>
                <td>{pct(s.precision)}</td>
                <td>{s.map.toFixed(4)}</td>
                <td>{s.mrr.toFixed(4)}</td>
                <td>{s.ndcg.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="demo-note">
        <strong>
          Nothing beats picking at random by a margin worth having.
        </strong>{" "}
        At k = {k}, random ranking scores {random ? pct(random.recall) : "—"} recall
        and the best non-cheating method reaches {pct(best.recall)}. "Same
        category" — the recommendation anyone would write first — does{" "}
        <em>worse</em> than random, because these customers do not repeat within
        a category. Switch the cut-off and the metric above: the ordering barely
        changes, which is what no signal looks like from every angle.
      </p>

      {oracle && (
        <p className="demo-note">
          <strong>The {pct(oracle.recall)} row is a ruler, not a result.</strong>{" "}
          The <Term id="oracle">oracle</Term> is allowed to read the customer's
          browsing history, and it scores a perfect{" "}
          {oracle.recall.toFixed(2)} recall — because in{" "}
          {pct(data.browsing_leak)} of rows the browsing column{" "}
          {data.browsing_deterministic ? "exactly contains" : "overlaps"} the
          purchase. Any model given that column would look brilliant and would
          have learned nothing. Finding the leak is the reason to build an
          oracle at all.
        </p>
      )}

      <div className="demo-split" style={{ marginTop: 18 }}>
        <div>
          <h5 className="demo-h">The "similar products" column is circular</h5>
          <div className="metric-row" style={{ marginTop: 0 }}>
            <Stat
              label="Same-category share of similar lists"
              value={pct(data.similar_category_share)}
              tone="var(--ds)"
            />
            <Stat
              label="If drawn at random"
              value={pct(data.similar_category_chance)}
            />
          </div>
          <p className="demo-hint">
            Every "similar product" shares its category, where chance would give{" "}
            {pct(data.similar_category_chance)}. The column was generated from
            the category, so a recommender built on it is reading the category
            back out — and that is why it scores below random once the customer
            is not buying within a category.
          </p>
        </div>
        <div>
          <h5 className="demo-h">
            What the recommendation probability correlates with
          </h5>
          <BarChart
            maxBars={data.probability_correlations.length}
            bars={data.probability_correlations.map((c) => ({
              label: c.feature,
              value: c.r,
              color: "var(--muted)",
            }))}
            formatValue={(v) => v.toFixed(4)}
          />
          <p className="demo-hint">
            The notebook's regression target correlates with nothing in the
            table — the largest is{" "}
            {Math.max(
              ...data.probability_correlations.map((c) => Math.abs(c.r)),
            ).toFixed(4)}
            . A model predicting it is fitting noise, and any R² reported for
            that is a measure of how much noise a flexible model can absorb.
          </p>
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 20 }}>
        Catalogue composition — the popularity baseline
      </h5>
      <BarChart
        maxBars={12}
        bars={data.popularity.map((p) => ({
          label: p.label,
          value: p.count,
          color: "var(--ai)",
        }))}
        formatValue={(v) => v.toLocaleString()}
      />
      <p className="demo-hint">
        {data.subcategories} subcategories across {data.products.toLocaleString()}{" "}
        products, near-evenly split — so even "recommend the most common thing"
        has almost nothing to exploit.
      </p>
    </div>
  );
}
