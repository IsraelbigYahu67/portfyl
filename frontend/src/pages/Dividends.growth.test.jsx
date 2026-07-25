import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dividends from "./Dividends";

vi.mock("../api", () => ({
  fetchDividends: () => Promise.resolve([]),
  fetchDividendForecast: () => Promise.resolve({ months: [], year: 2026, total_paid: 0, total_estimated: 0 }),
  fetchDividendGrowth: () => Promise.resolve([
    { ticker: "AAPL", name: "Apple Inc.", streak_years: 12, cagr_pct: 8.4,
      cagr_years_used: 5, yoy_pct: 6.1, payout_ratio_pct: 15.0 },
  ]),
}));

vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

describe("Dividends growth table", () => {
  it("renders a row per dividend-paying holding", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Dividends />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Dividend growth/i)).toBeInTheDocument();
    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(await screen.findByText(/12 yrs/i)).toBeInTheDocument();
  });
});
