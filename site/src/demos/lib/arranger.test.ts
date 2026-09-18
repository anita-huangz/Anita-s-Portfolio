/**
 * Cross-checks the browser arranger against the Python package that defines it.
 *
 * `piano-golden.json` is written by `scripts/generate_piano_results.py`, which
 * imports `arranger` from `llm-platform/piano-arrangement-lab` — so it
 * records what the reference implementation actually does across 120
 * combinations of progression, difficulty level and style.
 *
 * The comparison is exact on the notes. A voicing is a set of integers; there
 * is no floating-point reason for the two to differ, and if they do the demo
 * is showing something the project would not play. Costs are compared to 1e-9,
 * which allows only for the JSON round-trip.
 */

import { describe, expect, it } from "vitest";

import golden from "../../data/demos/piano-golden.json";
import {
  LEVELS,
  STYLES,
  arrange,
  arrangeGreedy,
  candidates,
  explain,
  parseChord,
  parseIntent,
  parseProgression,
  toMidi,
  voicingSpan,
} from "./arranger";

type Case = (typeof golden.cases)[number];

describe("the arranger port", () => {
  it("has cases to check", () => {
    expect(golden.cases.length).toBeGreaterThan(100);
  });

  for (const testCase of golden.cases as Case[]) {
    const label = `${testCase.name} / ${testCase.level} / ${testCase.style}`;

    describe(label, () => {
      it("chooses the same voicings as Python", () => {
        const ours = arrange(testCase.progression, testCase.level, testCase.style);
        expect(ours.steps.length).toBe(testCase.optimal.steps.length);
        ours.steps.forEach((step, i) => {
          const expected = testCase.optimal.steps[i];
          expect(step.chord.symbol).toBe(expected.chord);
          expect(step.voicing.left).toEqual(expected.left);
          expect(step.voicing.right).toEqual(expected.right);
        });
      });

      it("assigns the same costs", () => {
        const ours = arrange(testCase.progression, testCase.level, testCase.style);
        expect(ours.totalCost).toBeCloseTo(testCase.optimal.total_cost, 9);
        expect(ours.totalMotion).toBe(testCase.optimal.total_motion);
        expect(ours.maxSpan).toBe(testCase.optimal.max_span);
        ours.steps.forEach((step, i) => {
          expect(step.static).toBeCloseTo(testCase.optimal.steps[i].static, 9);
          expect(step.transition).toBeCloseTo(testCase.optimal.steps[i].transition, 9);
        });
      });

      it("reports the same rule violations and simplifications", () => {
        const ours = arrange(testCase.progression, testCase.level, testCase.style);
        ours.steps.forEach((step, i) => {
          const expected = testCase.optimal.steps[i];
          expect(step.violations.map((v) => v.rule)).toEqual(
            expected.violations.map((v) => v.rule),
          );
          expect(step.notes).toEqual(expected.notes);
        });
      });

      it("reproduces the greedy baseline too", () => {
        const ours = arrangeGreedy(testCase.progression, testCase.level, testCase.style);
        expect(ours.totalCost).toBeCloseTo(testCase.greedy.total_cost, 9);
        ours.steps.forEach((step, i) => {
          expect(step.voicing.right).toEqual(testCase.greedy.steps[i].right);
        });
      });
    });
  }
});

describe("the difficulty promise, in the browser", () => {
  for (const [levelName, level] of Object.entries(golden.levels)) {
    for (const styleName of Object.keys(STYLES)) {
      it(`${levelName} / ${styleName} never exceeds its own limits`, () => {
        for (const progression of Object.values(golden.progressions)) {
          const result = arrange(progression, levelName, styleName);
          for (const step of result.steps) {
            expect(step.voicing.right.length).toBeLessThanOrEqual(level.max_right_notes);
            expect(step.voicing.left.length).toBeLessThanOrEqual(level.max_left_notes);
            expect(voicingSpan(step.voicing)).toBeLessThanOrEqual(level.max_span);
          }
        }
      });
    }
  }
});

describe("the keyword parser port", () => {
  for (const expected of golden.intents) {
    it(`reads "${expected.text}" the same way Python does`, () => {
      const ours = parseIntent(expected.text);
      expect(ours.level).toBe(expected.level);
      expect(ours.style).toBe(expected.style);
      expect(ours.bpm).toBe(expected.bpm);
      expect(ours.unhandled).toBe(expected.unhandled);
    });
  }
});

describe("the solver, independently of the fixture", () => {
  it("is never worse than greedy", () => {
    for (const progression of Object.values(golden.progressions)) {
      for (const levelName of Object.keys(LEVELS)) {
        const optimal = arrange(progression, levelName);
        const greedy = arrangeGreedy(progression, levelName);
        expect(optimal.totalCost).toBeLessThanOrEqual(greedy.totalCost + 1e-9);
      }
    }
  });

  it("holds common tones where it can", () => {
    // C to Am shares C and E. A good arrangement keeps at least one in place.
    const result = arrange("C Am", "intermediate");
    const first = new Set(result.steps[0].voicing.pitches);
    const held = result.steps[1].voicing.pitches.filter((p) => first.has(p));
    expect(held.length).toBeGreaterThan(0);
  });

  it("catches parallel fifths", () => {
    const chord = parseChord("C");
    const before = { left: [], right: [60, 67], chord, pitches: [60, 67] };
    const after = { left: [], right: [62, 69], chord, pitches: [62, 69] };
    expect(explain(before, after).map((v) => v.rule)).toContain("parallel fifths");
  });

  it("refuses chords it cannot read", () => {
    expect(() => parseProgression("C H7")).toThrow();
    expect(() => arrange("", "beginner")).toThrow();
  });

  it("generates candidates for every chord in the corpus at every level", () => {
    for (const progression of Object.values(golden.progressions)) {
      for (const levelName of Object.keys(LEVELS)) {
        for (const chord of parseProgression(progression)) {
          expect(candidates(chord, LEVELS[levelName]).length).toBeGreaterThan(0);
        }
      }
    }
  });
});

describe("the browser MIDI writer", () => {
  /** Walk the file the way the format defines it. */
  function chunks(data: Uint8Array) {
    const view = new DataView(data.buffer);
    const out: { tag: string; body: Uint8Array }[] = [];
    const tagAt = (i: number) => String.fromCharCode(...data.slice(i, i + 4));
    const headerLength = view.getUint32(4);
    out.push({ tag: tagAt(0), body: data.slice(8, 8 + headerLength) });
    let pos = 8 + headerLength;
    while (pos < data.length) {
      const size = view.getUint32(pos + 4);
      out.push({ tag: tagAt(pos), body: data.slice(pos + 8, pos + 8 + size) });
      pos += 8 + size;
    }
    return out;
  }

  it("writes a header that declares its own length", () => {
    const data = toMidi(arrange("C Am F G7", "intermediate"));
    const [header, ...tracks] = chunks(data);
    expect(header.tag).toBe("MThd");
    const view = new DataView(header.body.buffer, header.body.byteOffset);
    expect(view.getUint16(0)).toBe(1); // format 1
    expect(view.getUint16(2)).toBe(3); // tempo + two hands
    expect(tracks.filter((t) => t.tag === "MTrk")).toHaveLength(3);
  });

  it("writes exactly the notes that were arranged", () => {
    const result = arrange("C Am F", "beginner");
    const data = toMidi(result);
    const written: number[] = [];
    for (const { tag, body } of chunks(data)) {
      if (tag !== "MTrk") continue;
      for (let i = 0; i < body.length - 2; i++) {
        // Note-on with a non-zero velocity, preceded by a complete delta.
        if (body[i] === 0x90 && body[i + 2] > 0) written.push(body[i + 1]);
      }
    }
    const expected = result.steps.flatMap((s) => s.voicing.pitches);
    expect(written.sort((a, b) => a - b)).toEqual(expected.sort((a, b) => a - b));
  });

  it("encodes the tempo as microseconds per beat", () => {
    const data = toMidi(arrange("C", "beginner"), 120);
    const tempoTrack = chunks(data)[1].body;
    // 00 FF 51 03 then three bytes.
    expect(tempoTrack[1]).toBe(0xff);
    expect(tempoTrack[2]).toBe(0x51);
    const value = (tempoTrack[4] << 16) | (tempoTrack[5] << 8) | tempoTrack[6];
    expect(value).toBe(500_000);
  });
});
