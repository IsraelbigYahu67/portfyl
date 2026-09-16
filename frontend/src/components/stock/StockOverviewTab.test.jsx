import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { StockOverviewTab } from "./StockOverviewTab";

const api = vi.hoisted(() => ({
  fetchHistory: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchTransactionsPage: vi.fn(),
}));

vi.mock("../../api", () => api);
vi.mock("../../App", () => ({ useCurrency: () => ({ currency: "USD" }) }));
vi.mock("../StockDetail", () => ({ StockOverview: () => <div>Overview KPIs</div> }));

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StockOverviewTab
          ticker="AAPL"
          overviewData={{ ticker: "AAPL", currency: "USD", description: "Apple description" }}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchHistory.mockResolvedValue({ data: [{ date: "2024-01-01", close: 100 }, { date: "2024-12-31", close: 120 }] });
  api.fetchTransactionsPage.mockResolvedValue({
    items: [{ date: "2024-01-02", type: "buy", shares: 2, price: 100, currency: "USD", notes: "Starter lot" }],
  });
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

it("states truthfully when the researched symbol is not owned", async () => {
  api.fetchHoldings.mockResolvedValue([{ ticker: "MSFT", shares: 1 }]);
  renderTab();
  expect(await screen.findByText("You do not currently own AAPL")).toBeInTheDocument();
  expect(screen.getByText("Overview KPIs")).toBeInTheDocument();
});
