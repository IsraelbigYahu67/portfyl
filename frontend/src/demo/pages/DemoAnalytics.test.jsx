import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import DemoAnalytics from "./DemoAnalytics";
import { DemoDataProvider } from "../DemoDataContext";

vi.mock("../../api", () => new Proxy({}, {
  get() {
    throw new Error("The public demo must not import the API client");
  },
}));

afterEach(() => vi.unstubAllGlobals());

describe("DemoAnalytics", () => {
  it("derives finite synthetic performance metrics locally", () => {
    const fetch = vi.fn(() => {
      throw new Error("The public demo must not fetch data");
    });
    vi.stubGlobal("fetch", fetch);

    render(<MemoryRouter><DemoDataProvider><DemoAnalytics /></DemoDataProvider></MemoryRouter>);

    for (const label of [
      "Total return", "Annualized return", "Volatility", "Sharpe ratio",
      "Maximum drawdown", "Best month", "Worst month", "Portfolio vs S&P 500",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText(/^\+\d+\.\d{2}%$/).length).toBeGreaterThan(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});
