import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Stock from "../../pages/Stock";

const api = vi.hoisted(() => ({
  fetchStockView: vi.fn(),
  fetchWatchlists: vi.fn(),
  addWatchlistItem: vi.fn(),
  removeWatchlistItem: vi.fn(),
  fetchHistory: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchTransactionsPage: vi.fn(),
}));

vi.mock("../../api", () => api);
vi.mock("../../App", () => ({ useCurrency: () => ({ currency: "USD" }) }));
vi.mock("../StockDetail", () => ({
  StockOverview: ({ data }) => <div>Rendered {data.ticker} view</div>,
}));

function renderStock(path = "/stock/AAPL?tab=overview") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path="/stock/:ticker" element={<Stock />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchStockView.mockImplementation((ticker, view) => Promise.resolve({ ticker, name: ticker, currency: "USD", view }));
  api.fetchWatchlists.mockResolvedValue([]);
  api.fetchHistory.mockResolvedValue({ data: [] });
  api.fetchHoldings.mockResolvedValue([]);
  api.fetchTransactionsPage.mockResolvedValue({ items: [] });
});

it("loads overview first and only the selected heavy view, retaining fresh cached tabs", async () => {
  renderStock();
  await waitFor(() => expect(api.fetchStockView).toHaveBeenCalledWith("AAPL", "overview"));
  await screen.findByRole("tab", { name: "Financials" });
  expect(api.fetchStockView).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByRole("tab", { name: "Financials" }));
  await waitFor(() => expect(api.fetchStockView).toHaveBeenCalledWith("AAPL", "financials"));
  expect(api.fetchStockView).not.toHaveBeenCalledWith("AAPL", "valuation");
  expect(api.fetchStockView).not.toHaveBeenCalledWith("AAPL", "ownership");

  fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
  fireEvent.click(screen.getByRole("tab", { name: "Financials" }));
  await waitFor(() => {
    expect(api.fetchStockView.mock.calls.filter(([, view]) => view === "financials")).toHaveLength(1);
  });
});

it("uses new view keys when the ticker changes", async () => {
  const first = renderStock("/stock/AAPL?tab=valuation");
  await waitFor(() => expect(api.fetchStockView).toHaveBeenCalledWith("AAPL", "valuation"));
  first.unmount();
  renderStock("/stock/MSFT?tab=valuation");
  await waitFor(() => expect(api.fetchStockView).toHaveBeenCalledWith("MSFT", "valuation"));
});
