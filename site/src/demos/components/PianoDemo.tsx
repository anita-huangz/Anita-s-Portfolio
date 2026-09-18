import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type Arrangement,
  type Voicing,
  LEVELS,
  STYLES,
  arrange,
  arrangeGreedy,
  noteName,
  parseIntent,
  toMidi,
} from "../lib/arranger";
import { Term } from "./Term";

const PRESETS: { label: string; chords: string }[] = [
  { label: "I–V–vi–IV", chords: "C G Am F" },
  { label: "ii–V–I", chords: "Dm7 G7 Cmaj7" },
  { label: "Autumn Leaves", chords: "Cm7 F7 Bbmaj7 Ebmaj7 Am7b5 D7 Gm" },
  { label: "Coltrane changes", chords: "Cmaj7 Eb7 Abmaj7 B7 Emaj7 G7 Cmaj7" },
  { label: "12-bar blues", chords: "F7 Bb7 F7 C7 Bb7 F7" },
  { label: "Slash bass", chords: "C G/B Am Am/G F" },
  { label: "Extensions", chords: "Cmaj9 Dm11 G13 Cmaj7" },
];

const BLACK = new Set([1, 3, 6, 8, 10]);
const LOW = 36;   // C2
const HIGH = 88;  // E6

/** White-key index, so black keys can be positioned between their neighbours. */
function whiteIndex(pitch: number): number {
  let count = 0;
  for (let p = LOW; p < pitch; p++) if (!BLACK.has(((p % 12) + 12) % 12)) count++;
  return count;
}

const WHITE_COUNT = whiteIndex(HIGH + 1);

/**
 * An SVG piano with the sounding notes lit.
 *
 * Drawn rather than described because "can my hand do that" is a question
 * about shape, and a list of note names does not answer it.
 */
function Keyboard({ voicing, playing }: { voicing: Voicing | null; playing: boolean }) {
  const left = new Set(voicing?.left ?? []);
  const right = new Set(voicing?.right ?? []);
  const width = 100 / WHITE_COUNT;

  const whites = [];
  const blacks = [];
  for (let pitch = LOW; pitch <= HIGH; pitch++) {
    const pc = ((pitch % 12) + 12) % 12;
    const lit = left.has(pitch) ? "var(--ds)" : right.has(pitch) ? "var(--ai)" : null;
    if (!BLACK.has(pc)) {
      const x = whiteIndex(pitch) * width;
      whites.push(
        <rect
          key={pitch} x={`${x}%`} y="0" width={`${width}%`} height="100%"
          className={`key white${lit ? " lit" : ""}${playing && lit ? " playing" : ""}`}
          style={lit ? { fill: lit } : undefined}
        />,
      );
      if (pc === 0) {
        whites.push(
          <text key={`${pitch}-label`} x={`${x + width / 2}%`} y="94%"
                className="key-label">{noteName(pitch)}</text>,
        );
      }
    } else {
      const x = whiteIndex(pitch) * width - width * 0.3;
      blacks.push(
        <rect
          key={pitch} x={`${x}%`} y="0" width={`${width * 0.6}%`} height="62%"
          className={`key black${lit ? " lit" : ""}${playing && lit ? " playing" : ""}`}
          style={lit ? { fill: lit } : undefined}
        />,
      );
    }
  }

  return (
    <svg className="keyboard" viewBox="0 0 100 26" preserveAspectRatio="none"
         role="img" aria-label={
           voicing
             ? `Left hand ${voicing.left.map(noteName).join(", ") || "silent"}; ` +
               `right hand ${voicing.right.map(noteName).join(", ")}`
             : "No chord selected"
         }>
      {whites}
      {blacks}
    </svg>
  );
}

/**
 * Plays an arrangement through the Web Audio API.
 *
 * Three detuned sine partials per note with a struck envelope, which is a long
 * way from a piano and close enough to hear voice leading — the thing the
 * arrangement is actually about. Created on first play, because a browser will
 * not let an AudioContext start without a gesture.
 */
function usePlayer() {
  const context = useRef<AudioContext | null>(null);
  const stopAt = useRef<number>(0);

  const play = useCallback(
    (arrangement: Arrangement, bpm: number, beats: number, onStep: (i: number) => void) => {
      context.current ??= new AudioContext();
      const ctx = context.current;
      void ctx.resume();

      const seconds = (60 / bpm) * beats;
      const start = ctx.currentTime + 0.08;
      arrangement.steps.forEach((step, index) => {
        const at = start + index * seconds;
        for (const pitch of step.voicing.pitches) {
          const frequency = 440 * 2 ** ((pitch - 69) / 12);
          const gain = ctx.createGain();
          // A struck string: fast attack, exponential decay, never quite zero
          // because exponentialRampToValueAtTime rejects a zero target.
          gain.gain.setValueAtTime(0.0001, at);
          gain.gain.exponentialRampToValueAtTime(0.16, at + 0.012);
          gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds * 0.95);
          gain.connect(ctx.destination);
          for (const [multiple, level] of [[1, 1], [2, 0.32], [3, 0.12]] as const) {
            const osc = ctx.createOscillator();
            osc.type = "sine";
            osc.frequency.value = frequency * multiple;
            const partial = ctx.createGain();
            partial.gain.value = level;
            osc.connect(partial).connect(gain);
            osc.start(at);
            osc.stop(at + seconds);
          }
        }
        window.setTimeout(() => onStep(index), (at - ctx.currentTime) * 1000);
      });
      stopAt.current = window.setTimeout(
        () => onStep(-1),
        (start - ctx.currentTime + arrangement.steps.length * seconds) * 1000,
      );
    },
    [],
  );

  useEffect(() => () => window.clearTimeout(stopAt.current), []);
  return play;
}

export function PianoDemo() {
  const [chords, setChords] = useState("Dm7 G7 Cmaj7 A7");
  const [level, setLevel] = useState("intermediate");
  const [style, setStyle] = useState("plain");
  const [bpm, setBpm] = useState(90);
  const [request, setRequest] = useState("");
  const [reading, setReading] = useState<string | null>(null);
  const [step, setStep] = useState(-1);
  const play = usePlayer();

  const { result, greedy, error } = useMemo(() => {
    try {
      return {
        result: arrange(chords, level, style),
        greedy: arrangeGreedy(chords, level, style),
        error: null as string | null,
      };
    } catch (exc) {
      return { result: null, greedy: null, error: (exc as Error).message };
    }
  }, [chords, level, style]);

  const apply = () => {
    const intent = parseIntent(request, { level, style, bpm });
    setLevel(intent.level);
    setStyle(intent.style);
    setBpm(intent.bpm);
    setReading(
      `read as ${intent.level}, ${intent.style}, ${intent.bpm} bpm` +
      (intent.unhandled ? ` — not understood: "${intent.unhandled}"` : ""),
    );
  };

  const download = () => {
    if (!result) return;
    const blob = new Blob([toMidi(result, bpm, 2)], { type: "audio/midi" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${chords.replace(/\s+/g, "-").slice(0, 40)}-${level}.mid`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const shown = step >= 0 && result ? result.steps[step]?.voicing ?? null : null;
  const saving = result && greedy && greedy.totalCost > 0
    ? (greedy.totalCost - result.totalCost) / greedy.totalCost
    : 0;

  return (
    <div className="demo">
      <div className="demo-controls">
        <label className="control" style={{ flex: 1, minWidth: 260 }}>
          <span className="control-label">Chords</span>
          <input
            className="demo-input" value={chords} spellCheck={false}
            onChange={(e) => setChords(e.target.value)}
            aria-label="Chord progression"
          />
        </label>
      </div>
      <div className="demo-controls">
        <div className="control" role="group" aria-label="Example progressions">
          <span className="control-label">Try</span>
          {PRESETS.map((p) => (
            <button
              key={p.label} className="chip" aria-pressed={chords === p.chords}
              onClick={() => setChords(p.chords)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="live-error">{error}</p>}

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Difficulty">
          <span className="control-label">Difficulty</span>
          {Object.keys(LEVELS).map((name) => (
            <button key={name} className="chip" aria-pressed={level === name}
                    onClick={() => setLevel(name)}>
              {name}
            </button>
          ))}
        </div>
        <div className="control" role="group" aria-label="Voicing style">
          <span className="control-label">Style</span>
          {Object.keys(STYLES).map((name) => (
            <button key={name} className="chip" aria-pressed={style === name}
                    onClick={() => setStyle(name)}>
              {name}
            </button>
          ))}
        </div>
      </div>

      <p className="demo-hint" style={{ marginTop: 4 }}>
        <strong>{LEVELS[level].name}</strong> — {LEVELS[level].description}{" "}
        The limits are enforced, not aimed at: no arrangement here ever exceeds
        its <Term id="hand-span">hand span</Term> or note count, and{" "}
        {level === "beginner"
          ? "a chord that needs an inversion is played in root position instead."
          : <><Term id="inversion">inversions</Term> are available, which is most of
            what lets the right hand stay still across a chord change.</>}
        {style !== "plain" && (
          <> <strong>{style}</strong> — {STYLES[style].description}
            {style === "jazzy" && (
              <> That is a <Term id="shell-voicing">shell voicing</Term>.</>
            )}
          </>
        )}
      </p>

      <div className="demo-controls">
        <label className="control" style={{ flex: 1, minWidth: 240 }}>
          <span className="control-label">Or just say what you want</span>
          <input
            className="demo-input" value={request} spellCheck={false}
            placeholder="an easy jazzy version, slow"
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && apply()}
            aria-label="Describe the arrangement you want"
          />
        </label>
        <button className="chip" onClick={apply} disabled={!request.trim()}>
          Apply
        </button>
      </div>
      {reading && <p className="demo-hint" style={{ marginTop: 2 }}>{reading}</p>}

      <div className="demo-controls">
        <button
          className="chip"
          onClick={() => result && play(result, bpm, 2, setStep)}
          disabled={!result}
        >
          ▶ Play
        </button>
        <button className="chip" onClick={download} disabled={!result}>
          Download MIDI
        </button>
        <div className="control" role="group" aria-label="Tempo">
          <span className="control-label">{bpm} bpm</span>
          <input
            type="range" min={50} max={180} step={2} value={bpm}
            aria-label="Tempo in beats per minute"
            onChange={(e) => setBpm(Number(e.target.value))}
          />
        </div>
      </div>

      <Keyboard voicing={shown ?? result?.steps[0]?.voicing ?? null} playing={step >= 0} />
      <p className="demo-hint" style={{ marginTop: 6 }}>
        <span style={{ color: "var(--ds)" }}>■</span> left hand{"  "}
        <span style={{ color: "var(--ai)" }}>■</span> right hand — press play to
        watch the voicing move, or hover a row below.
      </p>

      {result && (
        <>
          <div className="demo-table-wrap" style={{ marginTop: 10 }}>
            <table className="demo-table">
              <thead>
                <tr>
                  <th>Chord</th>
                  <th>Left hand</th>
                  <th>Right hand</th>
                  <th>Stretch</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {result.steps.map((s, i) => (
                  <tr
                    key={`${s.chord.symbol}-${i}`}
                    className={i === step ? "highlight" : undefined}
                    onMouseEnter={() => setStep(i)}
                  >
                    <td>{s.chord.symbol}</td>
                    <td className="mono">{s.voicing.left.map(noteName).join(" ")}</td>
                    <td className="mono">{s.voicing.right.map(noteName).join(" ")}</td>
                    <td>{Math.max(
                      s.voicing.right.length > 1
                        ? s.voicing.right[s.voicing.right.length - 1] - s.voicing.right[0] : 0,
                      s.voicing.left.length > 1
                        ? s.voicing.left[s.voicing.left.length - 1] - s.voicing.left[0] : 0,
                    )}</td>
                    <td>{s.cost.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="metric-row">
            <Stat label="Hand travel" value={`${result.totalMotion} semitones`} />
            <Stat label="Widest stretch" value={`${result.maxSpan} semitones`} />
            <Stat
              label="Paths evaluated"
              value={result.searched.toLocaleString()}
            />
            <Stat
              label="Better than greedy by"
              value={saving > 0.0001 ? `${(saving * 100).toFixed(1)}%` : "tie here"}
              tone={saving > 0.0001 ? "var(--se)" : undefined}
            />
          </div>

          <p className="demo-note" style={{ marginTop: 8 }}>
            A <Term id="chord-symbol">chord symbol</Term> names pitch
            classes, never octaves — "Cmaj7" is hundreds of ways two hands could
            play it, and the right one depends entirely on the chord before it. So this is a shortest path, not a
            lookup: every candidate voicing carries a cost for how awkward it is
            alone, every pair carries a cost for the{" "}
            <Term id="voice-leading">voice-leading</Term> rules broken between
            them and the distance the hands travel, and{" "}
            <Term id="viterbi">Viterbi</Term> finds the cheapest route through{" "}
            {result.searched.toLocaleString()} of them exactly.{" "}
            {saving > 0.0001 ? (
              <>Taking the best chord one at a time instead —{" "}
              <Term id="greedy">greedy</Term> — costs {(saving * 100).toFixed(1)}%
              more here, because it cannot accept a slightly worse voicing now to
              avoid a much worse one later.</>
            ) : (
              <>Greedy happens to tie on this progression; switch to a harder
              level or a longer progression and it stops tying.</>
            )}
          </p>

          {result.simplifications.length > 0 && (
            <p className="demo-note">
              <strong>Simplified for this level.</strong>{" "}
              {result.simplifications.map((s) => `${s.symbol}: ${s.note}`).join("; ")}.
              Playing a different chord without saying so would be the easy thing
              to do and the wrong one.
            </p>
          )}

          <p className="demo-note">
            {result.violations.length === 0 ? (
              <><strong>No voice-leading rules broken.</strong> No{" "}
              <Term id="parallel-fifths">parallel fifths</Term> or octaves, no
              voice crossings, no leap wider than a sixth in an inner part.</>
            ) : (
              <>
                <strong>
                  {result.violations.length} voice-leading{" "}
                  {result.violations.length === 1 ? "note" : "notes"}:
                </strong>{" "}
                {[...new Set(result.violations.map((v) => v.rule))].join(", ")}. The
                solver minimises total cost, not violation count — at this level it
                judged the alternative worse.
              </>
            )}
          </p>
        </>
      )}
    </div>
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
