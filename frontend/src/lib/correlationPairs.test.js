import { describe, it, expect } from "vitest";
import { topAbsoluteCorrelationPairs, correlationColor } from "./correlationPairs";

describe("topAbsoluteCorrelationPairs", () => {
  const tickers = ["A", "B", "C"];
  const matrix = [
    [1, 0.9, -0.2],
    [0.9, 1, 0.1],
    [-0.2, 0.1, 1],
  ];

  it("excludes the diagonal (self-correlation)", () => {
    const pairs = topAbsoluteCorrelationPairs(tickers, matrix, 10);
    expect(pairs.some((p) => p.a === p.b)).toBe(false);
  });

  it("does not duplicate a pair in both orders", () => {
    const pairs = topAbsoluteCorrelationPairs(tickers, matrix, 10);
    expect(pairs).toHaveLength(3); // 3 choose 2
  });

  it("sorts by absolute value descending", () => {
    const pairs = topAbsoluteCorrelationPairs(tickers, matrix, 10);
    expect(pairs[0]).toMatchObject({ a: "A", b: "B", value: 0.9 });
  });

  it("surfaces strong negative correlations as high as positive ones", () => {
    const pairs = topAbsoluteCorrelationPairs(tickers, matrix, 10);
    expect(pairs[1]).toMatchObject({ a: "A", b: "C", value: -0.2 });
  });

  it("caps the result at n pairs", () => {
    const pairs = topAbsoluteCorrelationPairs(tickers, matrix, 2);
    expect(pairs).toHaveLength(2);
  });

  it("returns an empty array for fewer than 2 tickers", () => {
    expect(topAbsoluteCorrelationPairs(["A"], [[1]], 10)).toEqual([]);
  });

  it("returns an empty array for missing input", () => {
    expect(topAbsoluteCorrelationPairs(undefined, undefined, 10)).toEqual([]);
    expect(topAbsoluteCorrelationPairs(["A", "B"], undefined, 10)).toEqual([]);
  });
});

describe("correlationColor", () => {
  it("scales copper with positive correlation", () => {
    expect(correlationColor(0.63)).toContain("var(--chart-2) 50%");
    expect(correlationColor(0.63)).toContain("var(--surface-card)");
  });

  it("uses the second hue for negative correlation", () => {
    expect(correlationColor(-0.2)).toContain("var(--chart-4) 26%");
  });

  it("is the faintest tint at zero and the strongest at 1", () => {
    expect(correlationColor(0)).toContain("var(--chart-2) 15%");
    expect(correlationColor(1)).toContain("var(--chart-2) 70%");
  });
});
