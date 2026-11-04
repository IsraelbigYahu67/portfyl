import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StockOverview } from "./StockDetail";

vi.mock("../api", () => ({}));

function renderStats(data, props = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockOverview
          data={{ ticker: "AAPL", currency: "USD", ...data }}
          sectionIds={["quickStats"]}
          showHeader={false}
          showCustomizer={false}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("shows only market cap, TTM revenue, TTM free cash flow and dividend yield", () => {
  renderStats({
    market_cap: 3.5e12,
    price: 200,
    fifty_two_week_low: 150,
    fifty_two_week_high: 250,
    beta: 1.2,
    ratios: { pe: 30, ev_ebitda: 22, div_yield: 0.45 },
    ttm: { eps: 6.5, revenue: 400e9, fcf: 100e9 },
  });

  for (const label of ["Market Cap", "Revenue (TTM)", "Free Cash Flow (TTM)", "Div Yield"]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  expect(screen.getByText("0.45%")).toBeInTheDocument();
  for (const label of ["P/E (TTM)", "EPS (TTM)", "Beta", "EV/EBITDA", "52-Week Range"]) {
    expect(screen.queryByText(label)).not.toBeInTheDocument();
  }
});

it("shows a dash for TTM figures the data does not have", () => {
  renderStats({ market_cap: null, ratios: {}, ttm: {} });
  expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
});
