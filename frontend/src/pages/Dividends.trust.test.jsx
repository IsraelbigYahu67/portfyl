import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";

import Dividends from "./Dividends";


const api = vi.hoisted(() => ({
  fetchDividends: vi.fn(),
  fetchDividendForecast: vi.fn(),
  fetchDividendGrowth: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

function dividend(patch = {}) {
  return {
    ticker: "MSFT",
    name: "Microsoft",
    shares: 10.5,
    currency: "USD",
    dividend_rate: 3.32,
    dividend_yield: 0.72,
    annual_income: 34.86,
    ex_date: "2099-08-20",
    pay_date: "2099-09-10",
    date_status: "complete",
    income_status: "estimated",
    warnings: [],
    source: "yahoo_finance",
    as_of: "2026-09-13T10:30:00Z",
    ...patch,
  };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Dividends />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.fetchDividends.mockReset().mockResolvedValue([]);
  api.fetchDividendForecast.mockReset().mockResolvedValue({
    months: [],
    year: 2026,
    total_paid: 0,
    total_estimated: 0,
  });
  api.fetchDividendGrowth.mockReset().mockResolvedValue([]);
});

it("does not call inconsistent or undated events upcoming", async () => {
  api.fetchDividends.mockResolvedValue([
    dividend({
      ticker: "BAD",
      date_status: "inconsistent",
      ex_date: "2099-10-01",
      pay_date: null,
    }),
    dividend({ ticker: "OK", date_status: "complete", ex_date: "2099-10-01" }),
    dividend({ ticker: "NONE", date_status: "unavailable", ex_date: null, pay_date: null }),
  ]);

  renderPage();

  const knownDates = await screen.findByRole("heading", { name: /known upcoming dates/i });
  expect(knownDates.closest("section")).toHaveTextContent("OK");
  expect(knownDates.closest("section")).not.toHaveTextContent("BAD");
  expect(knownDates.closest("section")).not.toHaveTextContent("NONE");
  expect(screen.getByText("BAD").closest("section")).toHaveTextContent(/needs review/i);
  expect(screen.getByText("NONE").closest("section")).toHaveTextContent(/date unavailable/i);
});

it("shows review instead of suspect annual income and names provenance", async () => {
  api.fetchDividends.mockResolvedValue([
    dividend({
      ticker: "RISK",
      income_status: "review",
      annual_income: null,
      warnings: ["implausible_implied_yield"],
    }),
  ]);

  renderPage();

  expect(await screen.findByText(/review estimate/i)).toBeInTheDocument();
  expect(screen.getByText(/Yahoo Finance/i)).toBeInTheDocument();
  expect(screen.getByText(/not guaranteed payments/i)).toBeInTheDocument();
  expect(screen.getByText(/Estimated annual income/i)).toBeInTheDocument();
});

it("does not present a failed dividend request as an empty portfolio", async () => {
  api.fetchDividends.mockRejectedValue(new Error("provider unavailable"));

  renderPage();

  expect(await screen.findByRole("alert")).toHaveTextContent(/could not load dividend data/i);
  expect(screen.queryByText(/no holdings found/i)).not.toBeInTheDocument();
});
