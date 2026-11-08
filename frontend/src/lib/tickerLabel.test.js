import { describe, expect, it } from "vitest";
import { shortTickerLabels, splitTicker } from "./tickerLabel";

const label = (names, name) => shortTickerLabels(names).get(name);

describe("splitTicker", () => {
  it("splits known exchange suffixes, one letter or more", () => {
    expect(splitTicker("VWCE.DE")).toEqual({ base: "VWCE", suffix: "DE" });
    expect(splitTicker("CEZ.PR")).toEqual({ base: "CEZ", suffix: "PR" });
    expect(splitTicker("NOVO-B.CO")).toEqual({ base: "NOVO-B", suffix: "CO" });
    expect(splitTicker("VOD.L")).toEqual({ base: "VOD", suffix: "L" });
    expect(splitTicker("0700.HK")).toEqual({ base: "0700", suffix: "HK" });
    expect(splitTicker("shop.to")).toEqual({ base: "shop", suffix: "TO" });
  });

  it("leaves share classes and plain tickers alone", () => {
    expect(splitTicker("BRK.B")).toBeNull();
    expect(splitTicker("BF.B")).toBeNull();
    expect(splitTicker("AAPL")).toBeNull();
    expect(splitTicker("Other")).toBeNull();
    expect(splitTicker(".DE")).toBeNull();
    expect(splitTicker("ABC.")).toBeNull();
  });
});

describe("shortTickerLabels", () => {
  it("drops the exchange suffix when the short ticker is unique", () => {
    const names = ["VWCE.DE", "AAPL", "NOVO-B.CO", "BRK.B", "CEZ.PR", "VOD.L", "Other"];
    expect(label(names, "VWCE.DE")).toBe("VWCE");
    expect(label(names, "NOVO-B.CO")).toBe("NOVO-B");
    expect(label(names, "CEZ.PR")).toBe("CEZ");
    expect(label(names, "VOD.L")).toBe("VOD");
    expect(label(names, "AAPL")).toBe("AAPL");
    expect(label(names, "BRK.B")).toBe("BRK.B");
    expect(label(names, "Other")).toBe("Other");
  });

  it("keeps the full ticker for every entry when the same ticker is on several exchanges", () => {
    const names = ["VWCE.DE", "VWCE.MI", "AAPL", "CEZ.PR"];
    expect(label(names, "VWCE.DE")).toBe("VWCE.DE");
    expect(label(names, "VWCE.MI")).toBe("VWCE.MI");
    expect(label(names, "CEZ.PR")).toBe("CEZ");
  });

  it("also keeps the full ticker next to a plain one with the same base", () => {
    const names = ["VWCE", "VWCE.DE"];
    expect(label(names, "VWCE.DE")).toBe("VWCE.DE");
    expect(label(names, "VWCE")).toBe("VWCE");
  });

  it("copes with empty input", () => {
    expect(shortTickerLabels(undefined).size).toBe(0);
  });
});
