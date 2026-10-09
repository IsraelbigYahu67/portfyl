import { describe, it, expect } from "vitest";
import { derivePortfolioAlerts } from "./portfolioAlerts";

describe("derivePortfolioAlerts", () => {
  it("creates a concentration alert above 25 percent", () => {
    const alerts = derivePortfolioAlerts({ holdings: [{ ticker: "AAPL", weight: 25.1 }], today: "2026-09-13" });
    expect(alerts).toContainEqual(
      expect.objectContaining({ id: "concentration-AAPL", to: "/allocation", severity: "warning" })
    );
  });

  it("flags a missing price as critical and a stale price as a warning", () => {
    const alerts = derivePortfolioAlerts({
      holdings: [
        { ticker: "GONE", weight: 0, price_status: "missing" },
        { ticker: "OLD", weight: 5, price_status: "stale" },
        { ticker: "OK", weight: 5, price_status: "closed" },
      ],
      today: "2026-10-09",
    });
    expect(alerts).toEqual([
      expect.objectContaining({ id: "price-missing-GONE", severity: "critical", to: "/allocation" }),
      expect.objectContaining({ id: "price-stale-OLD", severity: "warning", to: "/allocation" }),
    ]);
    expect(alerts[0].detail).toContain("valued at 0");
  });

  it("does not flag a position at exactly 25 percent", () => {
    const alerts = derivePortfolioAlerts({ holdings: [{ ticker: "AAPL", weight: 25 }], today: "2026-09-13" });
    expect(alerts).toEqual([]);
  });

  it("includes dividend review, missing tax FX, and events in the next 14 days", () => {
    const alerts = derivePortfolioAlerts({
      dividends: [{ ticker: "BAD", income_status: "review", warnings: ["provider_fields_disagree"], ex_date: "2026-09-20" }],
      taxReport: { summary: { fx_complete: false } },
      earnings: [{ ticker: "MSFT", date: "2026-09-27" }],
      today: "2026-09-13",
    });
    expect(alerts.map((a) => a.id)).toEqual(
      expect.arrayContaining(["dividend-review-BAD", "tax-fx", "dividend-event-BAD", "earnings-MSFT"])
    );
  });

  it("excludes events outside the window and produces stable order", () => {
    const alerts = derivePortfolioAlerts({ earnings: [{ ticker: "LATE", date: "2026-09-28" }], today: "2026-09-13" });
    expect(alerts).toEqual([]);
  });

  it("orders critical before warning before info", () => {
    const alerts = derivePortfolioAlerts({
      holdings: [{ ticker: "AAPL", weight: 30 }],
      earnings: [{ ticker: "MSFT", date: "2026-09-14" }],
      today: "2026-09-13",
    });
    expect(alerts.map((a) => a.severity)).toEqual(["warning", "info"]);
  });
});
