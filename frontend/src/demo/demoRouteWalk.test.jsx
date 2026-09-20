import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import DemoApp from "./DemoApp";
import { DemoDataProvider } from "./DemoDataContext";
import { demoPortfolio } from "./demoPortfolio";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";

const ROUTES = [
  ["/demo", "Overview"], ["/demo/allocation", "Allocation"], ["/demo/analytics", "Analytics"], ["/demo/dividends", "Dividends"],
  ...demoPortfolio.holdings.map((holding) => [`/demo/stock/${holding.symbol}`, holding.symbol]),
];
const forbidden = /\b(add transaction|alert|note|refresh|import|edit|delete|assistant|watchlist|settings|screener|tax report|options)\b/i;
const lazyRouteWait = { timeout: 5_000 };

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("public demo route walk", () => {
  it.each(ROUTES)("renders %s anonymously with the public-demo boundary", async (path, heading) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <AnalyticsProvider initialConsent="pending" adapterFactory={() => createMemoryAdapter()}>
          <DemoDataProvider><DemoApp /></DemoDataProvider>
        </AnalyticsProvider>
      </MemoryRouter>
    );

    expect(await screen.findByRole("heading", { name: heading }, lazyRouteWait)).toBeInTheDocument();
    expect(screen.getAllByText(/Synthetic demo/i).length).toBeGreaterThan(0);
    expect(screen.getByText(new RegExp(demoPortfolio.asOf))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute("href", expect.stringContaining("source=demo"));
    for (const control of [...screen.queryAllByRole("link"), ...screen.queryAllByRole("button")]) {
      expect(control.textContent).not.toMatch(forbidden);
    }
  }, 15_000);
});
