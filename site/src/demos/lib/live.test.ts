/**
 * The alignment step decides whether a live series is usable. Getting it wrong
 * means a fabricated price reaches the factor scores, so it is tested even
 * though the proxy it feeds is optional.
 */

import { describe, expect, it } from "vitest";

import { alignToDates } from "../livePrices";

const series = (dates: string[], closes: number[]) => ({
  ticker: "TEST",
  dates,
  closes,
});

describe("alignToDates", () => {
  const axis = ["2024-01-02", "2024-01-03", "2024-01-04"];

  it("returns closes in the axis order", () => {
    const got = alignToDates(series(axis, [10, 11, 12]), axis);
    expect(got).toEqual([10, 11, 12]);
  });

  it("reorders a series whose dates arrive shuffled", () => {
    const shuffled = series(
      ["2024-01-04", "2024-01-02", "2024-01-03"],
      [12, 10, 11],
    );
    expect(alignToDates(shuffled, axis)).toEqual([10, 11, 12]);
  });

  it("ignores sessions outside the axis", () => {
    const wider = series(
      ["2023-12-29", ...axis, "2024-01-05"],
      [9, 10, 11, 12, 13],
    );
    expect(alignToDates(wider, axis)).toEqual([10, 11, 12]);
  });

  it("rejects a series missing a session rather than filling it", () => {
    // Forward-filling here would invent a price and change the factor scores.
    const gappy = series(["2024-01-02", "2024-01-04"], [10, 12]);
    expect(alignToDates(gappy, axis)).toBeNull();
  });

  it("rejects a series that starts after the axis does", () => {
    const late = series(["2024-01-03", "2024-01-04"], [11, 12]);
    expect(alignToDates(late, axis)).toBeNull();
  });

  it("rejects an empty series", () => {
    expect(alignToDates(series([], []), axis)).toBeNull();
  });

  it("accepts an empty axis trivially", () => {
    expect(alignToDates(series(axis, [10, 11, 12]), [])).toEqual([]);
  });
});
