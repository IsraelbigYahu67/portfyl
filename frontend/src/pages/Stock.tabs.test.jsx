import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import Stock from "./Stock";

const api = vi.hoisted(() => ({
  fetchStockView: vi.fn(),
  fetchWatchlists: vi.fn(),
  addWatchlistItem: vi.fn(),
  removeWatchlistItem: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../components/stock/StockHeader", () => ({
  StockHeader: ({ data }) => <h1>{data.ticker} persistent header</h1>,
}));
vi.mock("../components/stock/StockOverviewTab", () => ({
  StockOverviewTab: () => <div>Overview content</div>,
}));
vi.mock("../components/stock/StockFinancialsTab", () => ({
  StockFinancialsTab: () => <div>Financials content</div>,
}));
vi.mock("../components/stock/StockValuationTab", () => ({
  StockValuationTab: () => <div>Valuation content</div>,
}));
vi.mock("../components/stock/StockOwnershipTab", () => ({
  StockOwnershipTab: () => <div>Ownership content</div>,
}));
vi.mock("../components/stock/StockFilingsTab", () => ({
  StockFilingsTab: () => <div>Filings content</div>,
}));

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

function renderStock(path) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <Routes>
          <Route path="/stock/:ticker" element={<Stock />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchStockView.mockResolvedValue({ ticker: "AAPL", name: "Apple", currency: "USD" });
  api.fetchWatchlists.mockResolvedValue([]);
});

it("canonicalizes missing and invalid tabs to overview while preserving other parameters", async () => {
  const first = renderStock("/stock/AAPL?from=watchlist");
  expect(await screen.findByText("Overview content")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("?from=watchlist&tab=overview"));
  first.unmount();

  renderStock("/stock/AAPL?tab=invalid&from=search");
  expect(await screen.findByText("Overview content")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("?tab=overview&from=search"));
});

it("uses one labelled panel, pushes tab selections, and keeps the header mounted", async () => {
  renderStock("/stock/AAPL?tab=financials&from=search");

  expect(await screen.findByText("Financials content")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "AAPL persistent header" })).toBeInTheDocument();
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  fireEvent.click(screen.getByRole("tab", { name: "Ownership" }));
  expect(await screen.findByText("Ownership content")).toBeInTheDocument();
  expect(screen.getByTestId("location")).toHaveTextContent("?tab=ownership&from=search");
  expect(screen.getByRole("heading", { name: "AAPL persistent header" })).toBeInTheDocument();
});

it("supports keyboard tab selection with wrapping focus", async () => {
  renderStock("/stock/AAPL?tab=overview");
  await screen.findByText("Overview content");
  const overview = screen.getByRole("tab", { name: "Overview" });
  overview.focus();
  fireEvent.keyDown(overview, { key: "ArrowLeft" });
  expect(screen.getByRole("tab", { name: "Filings" })).toHaveFocus();
  expect(await screen.findByText("Filings content")).toBeInTheDocument();
});
