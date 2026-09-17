import { useMemo, useState } from "react";
import { Term } from "./Term";

interface Props {
  all: string[];
  sectors: Record<string, string[]>;
  selected: string[];
  onChange: (next: string[]) => void;
  /** Below this, scoring has too few names to rank meaningfully. */
  min?: number;
}

/**
 * Sector presets plus individual toggles. Presets do the work -- picking
 * sixty tickers one at a time is not a thing anyone wants to do.
 */
export function TickerPicker({ all, sectors, selected, onChange, min = 2 }: Props) {
  const [filter, setFilter] = useState("");
  const chosen = new Set(selected);

  const visible = useMemo(() => {
    const needle = filter.trim().toUpperCase();
    return needle ? all.filter((t) => t.startsWith(needle)) : all;
  }, [all, filter]);

  const toggle = (ticker: string) => {
    if (chosen.has(ticker)) {
      if (selected.length <= min) return; // keep the universe rankable
      onChange(selected.filter((t) => t !== ticker));
    } else {
      onChange([...selected, ticker]);
    }
  };

  return (
    <div className="picker">
      <div className="picker-presets">
        <span className="control-label"><Term id="universe">Universe</Term></span>
        {Object.entries(sectors).map(([name, members]) => {
          const full = members.every((t) => chosen.has(t));
          return (
            <button
              key={name}
              className="chip"
              aria-pressed={full}
              onClick={() =>
                onChange(
                  full
                    ? selected.filter((t) => !members.includes(t))
                    : [...new Set([...selected, ...members])],
                )
              }
            >
              {name}
            </button>
          );
        })}
        <button className="chip" onClick={() => onChange([...all])}>
          All {all.length}
        </button>
        <input
          className="picker-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter…"
          spellCheck={false}
          aria-label="Filter tickers"
        />
      </div>

      <div className="picker-grid">
        {visible.map((ticker) => (
          <button
            key={ticker}
            className="ticker"
            aria-pressed={chosen.has(ticker)}
            onClick={() => toggle(ticker)}
          >
            {ticker}
          </button>
        ))}
      </div>

      <div className="picker-count">
        {selected.length} selected
        {selected.length <= min && ` — minimum ${min}`}
      </div>
    </div>
  );
}
