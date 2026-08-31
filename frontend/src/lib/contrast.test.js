import { contrastRatio } from "./contrast";
import { NEU_TOKENS } from "../App";

const CARD_BG = "#F3E8DA"; // NEU_TOKENS.bg -- the cream ground text sits on

describe("contrastRatio", () => {
  it("matches the textbook WCAG example (black on white = 21:1)", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
  });
  it("is symmetric", () => {
    expect(contrastRatio("#3A352C", "#F3E8DA")).toBeCloseTo(contrastRatio("#F3E8DA", "#3A352C"), 5);
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
