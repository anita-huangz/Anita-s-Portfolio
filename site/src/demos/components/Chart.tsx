/**
 * Small SVG chart primitives.
 *
 * Deliberately not a charting library: these draw two shapes (a line series
 * and a scatter) with one shared y-axis, a recessive grid, a legend whenever
 * there are two or more series, and a hover readout. Anything needing more
 * than that should get a real library rather than growing this file.
 */

import { useId, useMemo, useState } from "react";

export interface Series {
  label: string;
  color: string;
  points: { x: number; y: number }[];
  /** Rendered dashed, for a comparison line that is not the real result. */
  dashed?: boolean;
}

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function bounds(series: Series[]): Bounds {
  const xs = series.flatMap((s) => s.points.map((p) => p.x));
  const ys = series.flatMap((s) => s.points.map((p) => p.y));
  if (xs.length === 0) return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  // A flat series would otherwise divide by zero when scaling.
  const pad = maxY === minY ? Math.abs(maxY) * 0.1 || 1 : 0;
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: minY - pad, maxY: maxY + pad };
}

function niceTicks(min: number, max: number, count = 5): number[] {
  const span = max - min;
  if (span <= 0) return [min];
  const rough = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? magnitude * 10;
  const ticks: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max; t += step) ticks.push(t);
  return ticks;
}

interface LineChartProps {
  series: Series[];
  height?: number;
  formatY?: (v: number) => string;
  formatX?: (v: number) => string;
  yLabel?: string;
}

export function LineChart({
  series,
  height = 260,
  formatY = (v) => v.toFixed(0),
  formatX = (v) => String(v),
  yLabel,
}: LineChartProps) {
  const clipId = useId();
  const [hoverX, setHoverX] = useState<number | null>(null);

  const width = 720;
  const pad = { top: 12, right: 16, bottom: 28, left: 58 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const b = useMemo(() => bounds(series), [series]);
  const sx = (x: number) => pad.left + ((x - b.minX) / (b.maxX - b.minX || 1)) * plotW;
  const sy = (y: number) => pad.top + plotH - ((y - b.minY) / (b.maxY - b.minY || 1)) * plotH;

  const yTicks = niceTicks(b.minY, b.maxY);
  const xTicks = niceTicks(b.minX, b.maxX, 5);

  const hovered = useMemo(() => {
    if (hoverX === null) return null;
    const dataX = b.minX + ((hoverX - pad.left) / plotW) * (b.maxX - b.minX);
    return series.map((s) => {
      let best = s.points[0];
      for (const p of s.points) {
        if (Math.abs(p.x - dataX) < Math.abs(best.x - dataX)) best = p;
      }
      return { label: s.label, color: s.color, point: best };
    });
  }, [hoverX, series, b, plotW]);

  return (
    <div className="chart">
      {series.length > 1 && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.label} className="legend-item">
              <span
                className="swatch"
                style={{
                  background: s.dashed ? "transparent" : s.color,
                  borderColor: s.color,
                  borderStyle: s.dashed ? "dashed" : "solid",
                }}
              />
              {s.label}
            </span>
          ))}
        </div>
      )}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="chart-svg"
        role="img"
        aria-label={yLabel ?? "chart"}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setHoverX(((e.clientX - rect.left) / rect.width) * width);
        }}
        onMouseLeave={() => setHoverX(null)}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={pad.left} y={pad.top} width={plotW} height={plotH} />
          </clipPath>
        </defs>

        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={pad.left} x2={width - pad.right} y1={sy(t)} y2={sy(t)}
              className="gridline"
            />
            <text x={pad.left - 8} y={sy(t)} dy="0.32em" className="tick" textAnchor="end">
              {formatY(t)}
            </text>
          </g>
        ))}

        {xTicks.map((t) => (
          <text key={t} x={sx(t)} y={height - 8} className="tick" textAnchor="middle">
            {formatX(t)}
          </text>
        ))}

        <g clipPath={`url(#${clipId})`}>
          {series.map((s) => (
            <polyline
              key={s.label}
              className="series-line"
              stroke={s.color}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              points={s.points.map((p) => `${sx(p.x)},${sy(p.y)}`).join(" ")}
            />
          ))}
        </g>

        {hoverX !== null && hovered && (
          <g>
            <line
              x1={hoverX} x2={hoverX} y1={pad.top} y2={pad.top + plotH}
              className="crosshair"
            />
            {hovered.map((h) => (
              <circle
                key={h.label}
                cx={sx(h.point.x)} cy={sy(h.point.y)} r={4}
                fill={h.color} className="marker"
              />
            ))}
          </g>
        )}
      </svg>

      {hovered && (
        <div className="readout">
          <span className="readout-x">{formatX(hovered[0].point.x)}</span>
          {hovered.map((h) => (
            <span key={h.label}>
              <span className="swatch" style={{ background: h.color, borderColor: h.color }} />
              {h.label} <strong>{formatY(h.point.y)}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export interface ScatterGroup {
  label: string;
  color: string;
  points: { x: number; y: number; note?: string }[];
}

interface ScatterProps {
  groups: ScatterGroup[];
  height?: number;
  xLabel: string;
  yLabel: string;
  formatX?: (v: number) => string;
  formatY?: (v: number) => string;
}

export function ScatterChart({
  groups,
  height = 300,
  xLabel,
  yLabel,
  formatX = (v) => v.toFixed(0),
  formatY = (v) => v.toFixed(0),
}: ScatterProps) {
  const [hover, setHover] = useState<{ g: string; x: number; y: number; note?: string } | null>(
    null,
  );

  const width = 720;
  const pad = { top: 12, right: 16, bottom: 44, left: 62 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const series: Series[] = groups.map((g) => ({ label: g.label, color: g.color, points: g.points }));
  const b = bounds(series);
  const sx = (x: number) => pad.left + ((x - b.minX) / (b.maxX - b.minX || 1)) * plotW;
  const sy = (y: number) => pad.top + plotH - ((y - b.minY) / (b.maxY - b.minY || 1)) * plotH;

  return (
    <div className="chart">
      <div className="legend">
        {groups.map((g) => (
          <span key={g.label} className="legend-item">
            <span className="swatch" style={{ background: g.color, borderColor: g.color }} />
            {g.label}
          </span>
        ))}
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" role="img" aria-label={yLabel}>
        {niceTicks(b.minY, b.maxY).map((t) => (
          <g key={`y${t}`}>
            <line x1={pad.left} x2={width - pad.right} y1={sy(t)} y2={sy(t)} className="gridline" />
            <text x={pad.left - 8} y={sy(t)} dy="0.32em" className="tick" textAnchor="end">
              {formatY(t)}
            </text>
          </g>
        ))}
        {niceTicks(b.minX, b.maxX).map((t) => (
          <text key={`x${t}`} x={sx(t)} y={height - 22} className="tick" textAnchor="middle">
            {formatX(t)}
          </text>
        ))}

        {/* Zero lines: the quadrant a point lands in is the whole story here. */}
        {b.minY < 0 && b.maxY > 0 && (
          <line x1={pad.left} x2={width - pad.right} y1={sy(0)} y2={sy(0)} className="zeroline" />
        )}
        {b.minX < 0 && b.maxX > 0 && (
          <line x1={sx(0)} x2={sx(0)} y1={pad.top} y2={pad.top + plotH} className="zeroline" />
        )}

        {groups.map((g) =>
          g.points.map((p, i) => (
            <circle
              key={`${g.label}-${i}`}
              cx={sx(p.x)} cy={sy(p.y)} r={5}
              fill={g.color} fillOpacity={0.75}
              className="dot"
              onMouseEnter={() => setHover({ g: g.label, x: p.x, y: p.y, note: p.note })}
              onMouseLeave={() => setHover(null)}
            />
          )),
        )}

        <text x={pad.left + plotW / 2} y={height - 4} className="axis-label" textAnchor="middle">
          {xLabel}
        </text>
        <text
          x={-(pad.top + plotH / 2)} y={14}
          className="axis-label" textAnchor="middle" transform="rotate(-90)"
        >
          {yLabel}
        </text>
      </svg>

      <div className="readout">
        {hover ? (
          <>
            <strong>{hover.g}</strong>
            {hover.note && <span>{hover.note}</span>}
            <span>{xLabel}: <strong>{formatX(hover.x)}</strong></span>
            <span>{yLabel}: <strong>{formatY(hover.y)}</strong></span>
          </>
        ) : (
          <span className="muted">Hover a point for its values.</span>
        )}
      </div>
    </div>
  );
}
