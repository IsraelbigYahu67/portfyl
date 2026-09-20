import { readFile } from "node:fs/promises";
import path from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import Stock from "../../pages/Stock";

// Vite rewrites `new URL(relative, import.meta.url)` for a path inside the
// project root to a root-relative pathname rather than a file:// URL (see
// primitives.test.jsx / chartTheme.test.js for the same pattern), so resolve
// it against the Vitest process cwd (frontend/) instead of fileURLToPath.
async function readSource(relativePath) {
  const assetUrl = new URL(relativePath, import.meta.url);
  const pathname = path.resolve(decodeURIComponent(assetUrl.pathname).replace(/^\//, ""));
  return readFile(pathname, "utf-8");
}

const STOCK_AND_RESEARCH_FILES = [
  "../StockDetail.jsx",
  "./StockHeader.jsx",
  "./StockDataTab.jsx",
  "./StockFilingsTab.jsx",
  "./StockFinancialsTab.jsx",
  "./StockOverviewTab.jsx",
  "./StockOwnershipTab.jsx",
  "./StockValuationTab.jsx",
  "../../pages/Stock.jsx",
  "../../pages/Search.jsx",
  "../../pages/Screener.jsx",
  "../../pages/TaxReport.jsx",
];

describe("stock and research surfaces stay above the 12px readability floor", () => {
  it.each(STOCK_AND_RESEARCH_FILES)("%s has no text-[8-11px] utility", async (relativePath) => {
    const src = await readSource(relativePath);
    expect(src).not.toMatch(/text-\[(8|9|10|11)px\]/);
  });
});

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
