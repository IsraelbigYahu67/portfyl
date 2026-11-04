import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StockOverviewTab } from "./StockOverviewTab";

const api = vi.hoisted(() => ({
  fetchHistory: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchTransactionsPage: vi.fn(),
  fetchStockView: vi.fn(),
}));

vi.mock("../../api", () => api);
const state = vi.hoisted(() => ({ currency: "USD" }));
vi.mock("../../App", () => ({ useCurrency: () => state }));
vi.mock("../StockDetail", () => ({ StockOverview: () => <div>Overview KPIs</div> }));

const LONG_DESCRIPTION = "Apple designs consumer electronics, software and services. ".repeat(6).trim();

function renderTab(description = "Apple description") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockOverviewTab
          ticker="AAPL"
          overviewData={{ ticker: "AAPL", currency: "USD", description }}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  state.currency = "USD";
  api.fetchStockView.mockResolvedValue({ ttm: { revenue: 400e9, fcf: 100e9 } });
  api.fetchHistory.mockResolvedValue({ data: [{ date: "2024-01-01", close: 100 }, { date: "2024-12-31", close: 120 }] });
  api.fetchTransactionsPage.mockResolvedValue({
    items: [{ date: "2024-01-02", type: "buy", shares: 2, price: 100, currency: "USD", notes: "Starter lot" }],
  });
});

it("formats native average cost separately from selected-currency portfolio values", async () => {
  state.currency = "CZK";
  api.fetchHoldings.mockResolvedValue([{ ticker: "AAPL", shares: 10, currency: "USD", avg_cost: 180, market_value: 4_000, pnl: 400, pnl_percent: 11.11, weight: 12.5 }]);
  renderTab();

  const position = await screen.findByRole("region", { name: "Your position" });
  expect(within(position).getByText("$180.00")).toBeInTheDocument();
  expect(within(position).getByText(/4.*000,00.*Kč/)).toBeInTheDocument();
});

it("shows the complete owned position and exact latest transaction", async () => {
  api.fetchHoldings.mockResolvedValue([{
    ticker: "AAPL",
    shares: 10,
    avg_cost: 100,
    market_value: 1250,
    pnl: 250,
    pnl_percent: 25,
    weight: 12.5,
  }]);
  renderTab();

  const position = await screen.findByRole("region", { name: "Your position" });
  expect(within(position).getByText("10")).toBeInTheDocument();
  expect(within(position).getByText("$100.00")).toBeInTheDocument();
  expect(within(position).getByText("$1,250.00")).toBeInTheDocument();
  expect(within(position).getByText("$250.00")).toBeInTheDocument();
  expect(within(position).getByText("+25.00%")).toBeInTheDocument();
  expect(within(position).getByText("12.50%")).toBeInTheDocument();
  expect(within(position).getByText(/January 2, 2024 · buy · 2 shares at \$100\.00/)).toBeInTheDocument();
  expect(within(position).getByText("Note: Starter lot")).toBeInTheDocument();
  expect(api.fetchTransactionsPage).toHaveBeenCalledWith({ ticker: "AAPL", sort: "-date", limit: 1 });
});

it("About is clamped with a toggle", async () => {
  api.fetchHoldings.mockResolvedValue([]);
  renderTab(LONG_DESCRIPTION);
  const about = await screen.findByText(LONG_DESCRIPTION);
  expect(about).toHaveClass("line-clamp-3");

  fireEvent.click(screen.getByRole("button", { name: "Show more" }));
  expect(about).not.toHaveClass("line-clamp-3");
  fireEvent.click(screen.getByRole("button", { name: "Show less" }));
  expect(about).toHaveClass("line-clamp-3");
});

it("a short About needs no toggle", async () => {
  api.fetchHoldings.mockResolvedValue([]);
  renderTab();
  expect(await screen.findByText("Apple description")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Show more" })).not.toBeInTheDocument();
});

it("states truthfully when the researched symbol is not owned", async () => {
  api.fetchHoldings.mockResolvedValue([{ ticker: "MSFT", shares: 1 }]);
  renderTab();
  expect(await screen.findByText("You do not currently own AAPL")).toBeInTheDocument();
  expect(screen.getByText("Overview KPIs")).toBeInTheDocument();
});
