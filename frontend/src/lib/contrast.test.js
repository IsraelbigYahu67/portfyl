import { contrastRatio, parseColor } from "./contrast";
import { NEU_TOKENS } from "../App";
import { THEME_CONTRAST_PAIRS } from "./themeTokens";

const CARD_BG = "#F3E8DA"; // NEU_TOKENS.bg -- the cream ground text sits on

describe("contrastRatio", () => {
  it("matches the textbook WCAG example (black on white = 21:1)", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
  });
  it("is symmetric", () => {
    expect(contrastRatio("#3A352C", "#F3E8DA")).toBeCloseTo(contrastRatio("#F3E8DA", "#3A352C"), 5);
  });
  it("resolves an opaque rgba() foreground the same as its equivalent hex", () => {
    expect(contrastRatio("rgba(58,53,44,1)", "#FFFFFF")).toBeCloseTo(contrastRatio("#3A352C", "#FFFFFF"), 5);
  });
  it("composites a translucent rgba() foreground over a supplied opaque backdrop before computing luminance", () => {
    const composited = contrastRatio("rgba(0,0,0,0.5)", "#FFFFFF", "#FFFFFF");
    expect(composited).toBeGreaterThan(1);
    expect(composited).toBeLessThan(21);
    expect(parseColor("rgba(0,0,0,0.5)", "#FFFFFF")).toEqual({ r: 128, g: 128, b: 128 });
  });
  it("rejects unsupported CSS variables with a clear error", () => {
    expect(() => contrastRatio("var(--ink)", "#FFFFFF")).toThrow(/unsupported color/i);
  });
});

describe("theme contrast matrix", () => {
  it("every text pair declares at least a 4.5:1 minimum", () => {
    const textPairs = THEME_CONTRAST_PAIRS.filter((pair) => pair.kind === "text");
    expect(textPairs.length).toBeGreaterThan(0);
    textPairs.forEach((pair) => expect(pair.minimum).toBeGreaterThanOrEqual(4.5));
  });
  it("every non-text pair declares at least a 3:1 minimum", () => {
    const nonTextPairs = THEME_CONTRAST_PAIRS.filter((pair) => pair.kind === "nonText");
    expect(nonTextPairs.length).toBeGreaterThan(0);
    nonTextPairs.forEach((pair) => expect(pair.minimum).toBeGreaterThanOrEqual(3));
  });
  it.each(THEME_CONTRAST_PAIRS)("$theme $name meets contrast", ({ foreground, background, minimum }) => {
    expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(minimum);
  });
});

describe("Premium theme contrast against the cream card", () => {
  it("ink clears AAA body text (7:1)", () => {
    expect(contrastRatio(NEU_TOKENS.ink, CARD_BG)).toBeGreaterThanOrEqual(7);
  });
  it("muted clears AA body text (4.5:1)", () => {
    expect(contrastRatio(NEU_TOKENS.muted, CARD_BG)).toBeGreaterThanOrEqual(4.5);
  });
  // brand/gain/loss render as bold small-caps pills, deltas and icons (not
  // paragraph text), so the applicable bar is WCAG's large-text/UI-component
  // threshold (3:1, SC 1.4.11) rather than normal body text's 4.5:1.
  it("brand clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.brand, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("gain clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.gain, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("loss clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.loss, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("white button labels on --brand clear AA body text (4.5:1)", () => {
    expect(contrastRatio("#FFFFFF", NEU_TOKENS.brand)).toBeGreaterThanOrEqual(4.5);
  });
});
