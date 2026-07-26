import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DividendGrowthSection } from "./StockDetail";

vi.mock("../api", () => ({
  fetchStockDividendGrowth: () => Promise.resolve({
    ticker: "AAPL", streak_years: 12, cagr_pct: 8.0, cagr_years_used: 5,
    yoy_pct: 6.0, payout_ratio_pct: 15.0,
    annual: [{ year: 2022, dps: 0.9 }, { year: 2023, dps: 0.96 }],
    payments: [
      { ex_date: "2022-02-10", amount: 0.22 },
      { ex_date: "2023-02-10", amount: 0.23 },
    ],
  }),
}));

describe("DividendGrowthSection", () => {
  it("shows growth stats when the stock pays a dividend", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <DividendGrowthSection ticker="AAPL" currency="USD" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Dividend history/i)).toBeInTheDocument();
    expect(await screen.findByText(/12 yrs/i)).toBeInTheDocument();
  });
});
