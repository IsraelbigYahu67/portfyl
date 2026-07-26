import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DividendGrowthSection } from "./StockDetail";
import { fetchStockDividendGrowth } from "../api";

vi.mock("../api", () => ({
  fetchStockDividendGrowth: vi.fn(),
}));

describe("DividendGrowthSection", () => {
  it("shows growth stats when the stock pays a dividend", async () => {
    fetchStockDividendGrowth.mockResolvedValue({
      ticker: "AAPL", streak_years: 12, cagr_pct: 8.0, cagr_years_used: 5,
      yoy_pct: 6.0, payout_ratio_pct: 15.0,
      annual: [{ year: 2022, dps: 0.9 }, { year: 2023, dps: 0.96 }],
      payments: [
        { ex_date: "2022-02-10", amount: 0.22 },
        { ex_date: "2023-02-10", amount: 0.23 },
      ],
    });
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <DividendGrowthSection ticker="AAPL" currency="USD" />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Dividend history/i)).toBeInTheDocument();
    expect(await screen.findByText(/12 yrs/i)).toBeInTheDocument();
  });

  it("renders nothing when the stock pays no dividend", async () => {
    // payments empty -> component returns null, nothing rendered
    fetchStockDividendGrowth.mockResolvedValue({
      ticker: "NONE", streak_years: 0, cagr_pct: null, cagr_years_used: 0,
      yoy_pct: null, payout_ratio_pct: null, annual: [], payments: [],
    });
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <DividendGrowthSection ticker="NONE" currency="USD" />
      </QueryClientProvider>
    );
    // give the query a tick to resolve, then assert nothing rendered
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
    expect(screen.queryByText(/Dividend history/i)).toBeNull();
  });
});
