import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DividendGrowthSection } from "./StockDetail";
import { fetchStockDividendGrowth } from "../api";

vi.mock("../api", () => ({
  fetchStockDividendGrowth: vi.fn(),
}));

// Recent-payment fixtures must stay within the last year of "now" for the
// component's own Date.now()-based recency check to keep passing.
const recentExDate = (monthsAgo) => {
  const d = new Date();
  d.setMonth(d.getMonth() - monthsAgo);
  return d.toISOString().slice(0, 10);
};

describe("DividendGrowthSection", () => {
  it("shows growth stats when the stock pays a dividend", async () => {
    fetchStockDividendGrowth.mockResolvedValue({
      ticker: "AAPL", streak_years: 12, cagr_pct: 8.0, cagr_years_used: 5,
      yoy_pct: 6.0, payout_ratio_pct: 15.0,
      annual: [{ year: 2022, dps: 0.9 }, { year: 2023, dps: 0.96 }],
      payments: [
        { ex_date: recentExDate(14), amount: 0.22 },
        { ex_date: recentExDate(2), amount: 0.23 },
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

  it("renders nothing when every payment amount is zero (never paid)", async () => {
    fetchStockDividendGrowth.mockResolvedValue({
      ticker: "ZERO", streak_years: 0, cagr_pct: null, cagr_years_used: 0,
      yoy_pct: null, payout_ratio_pct: null, annual: [],
      payments: [
        { ex_date: recentExDate(50), amount: 0 },
        { ex_date: recentExDate(2), amount: 0 },
      ],
    });
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <DividendGrowthSection ticker="ZERO" currency="USD" />
      </QueryClientProvider>
    );
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
    expect(screen.queryByText(/Dividend history/i)).toBeNull();
  });

  it("renders nothing when the last payment is over a year old", async () => {
    fetchStockDividendGrowth.mockResolvedValue({
      ticker: "STALE", streak_years: 5, cagr_pct: 4.0, cagr_years_used: 5,
      yoy_pct: 2.0, payout_ratio_pct: 20.0,
      annual: [{ year: 2022, dps: 0.9 }, { year: 2023, dps: 0.96 }],
      payments: [
        { ex_date: recentExDate(30), amount: 0.22 },
        { ex_date: recentExDate(18), amount: 0.23 },
      ],
    });
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <DividendGrowthSection ticker="STALE" currency="USD" />
      </QueryClientProvider>
    );
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
    expect(screen.queryByText(/Dividend history/i)).toBeNull();
  });
});
