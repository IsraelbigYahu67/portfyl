import { describe, it, expect } from "vitest";
import { priceFreshnessLine, priceFreshnessTitle } from "./priceFreshness";

const opts = { locale: "en-US", timeZone: "UTC" };

describe("priceFreshnessLine", () => {
  it("names the source, the delay and the newest quote time", () => {
    const line = priceFreshnessLine(
      { holdings_count: 2, price_source: "Yahoo Finance", price_delay_minutes: 15, prices_as_of: "2026-10-09T17:44:00Z" },
      opts,
    );
    expect(line).toMatch(/^Prices from Yahoo Finance · delayed up to 15 min · last quote Oct 9, 5:44/);
  });

  it("omits the delay when quotes are real time", () => {
    const line = priceFreshnessLine(
      { holdings_count: 1, price_source: "Yahoo Finance", price_delay_minutes: 0, prices_as_of: "2026-10-09T17:44:00Z" },
      opts,
    );
    expect(line).not.toContain("delayed");
    expect(line).toContain("last quote Oct 9");
  });

  it("says when no quote time is known instead of pretending it is current", () => {
    const line = priceFreshnessLine(
      { holdings_count: 1, price_source: "Yahoo Finance", price_delay_minutes: null, prices_as_of: null },
      opts,
    );
    expect(line).toBe("Prices from Yahoo Finance · quote time unavailable");
  });

  it("renders nothing for an empty portfolio or an older backend", () => {
    expect(priceFreshnessLine({ holdings_count: 0, prices_as_of: null }, opts)).toBeNull();
    expect(priceFreshnessLine({ holdings_count: 3, last_updated: "2026-10-09T18:00:00" }, opts)).toBeNull();
    expect(priceFreshnessLine(undefined, opts)).toBeNull();
  });
});

describe("priceFreshnessTitle", () => {
  it("describes a holding's quote for a tooltip", () => {
    expect(
      priceFreshnessTitle(
        { price_status: "closed", price_source: "Yahoo Finance", price_as_of: "2026-10-08T22:00:00Z" },
        opts,
      ),
    ).toMatch(/^Yahoo Finance · market closed · last quote Oct 8, 10:00/);
  });

  it("explains a missing price", () => {
    expect(priceFreshnessTitle({ price_status: "missing", price_source: "Yahoo Finance" }, opts)).toBe(
      "Yahoo Finance · no current price; this holding is valued at 0",
    );
  });

  it("explains a stale price", () => {
    expect(
      priceFreshnessTitle(
        { price_status: "stale", price_source: "Yahoo Finance", price_as_of: "2026-09-01T20:00:00Z" },
        opts,
      ),
    ).toMatch(/^Yahoo Finance · price is out of date · last quote Sep 1/);
  });

  it("returns null when the row has no freshness data", () => {
    expect(priceFreshnessTitle({ ticker: "AAPL" }, opts)).toBeNull();
  });
});
