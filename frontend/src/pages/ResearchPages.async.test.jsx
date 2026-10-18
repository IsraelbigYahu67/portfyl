import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ConfirmProvider } from "../components/ui/ConfirmDialog";
import { ToastProvider } from "../components/ui/Toast";

import Search from "./Search";
import Watchlists from "./Watchlists";
import Settings from "./Settings";
import Stock from "./Stock";

const api = vi.hoisted(() => ({
  searchTickers: vi.fn(),
  fetchWatchlists: vi.fn(),
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  addWatchlistItem: vi.fn(),
  removeWatchlistItem: vi.fn(),
  fetchAlerts: vi.fn(),
  createAlert: vi.fn(),
  updateAlert: vi.fn(),
  deleteAlert: vi.fn(),
  checkAlerts: vi.fn(),
  fetchCapabilities: vi.fn(),
  fetchDiscordWebhook: vi.fn(),
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  connectT212: vi.fn(),
  disconnectT212: vi.fn(),
  syncT212: vi.fn(),
  retryT212History: vi.fn(),
  setT212AutoSync: vi.fn(),
  fetchStockView: vi.fn(),
  fetchHistory: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchTransactionsPage: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  usePortfolio: () => ({ current: { id: "portfolio-1", name: "Research portfolio" } }),
  useCurrency: () => ({ currency: "USD" }),
}));
vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({
    recordPortfolioCreated: () => false,
    recordPortfolioDataImported: () => false,
    recordPopulatedDashboard: () => false,
  }),
}));
vi.mock("../components/DiscordSettings", () => ({ default: () => null }));
vi.mock("../components/SyncScheduleSettings", () => ({ default: () => null }));
vi.mock("../components/DataPrivacySettings", () => ({ default: () => null }));
vi.mock("../components/settings/IBKRConnectionCard", () => ({ default: () => null }));
vi.mock("../components/settings/EtoroConnectionCard", () => ({ default: () => null }));
vi.mock("../components/StockDetail", () => ({
  StockOverview: ({ data }) => <div>Overview for {data.ticker}</div>,
}));

function renderPage(Page, path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider><ConfirmProvider>
          <Routes>
            <Route path="*" element={<Page />} />
            <Route path="/stock/:ticker" element={<Page />} />
          </Routes>
        </ConfirmProvider></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.searchTickers.mockResolvedValue({ results: [] });
  api.fetchWatchlists.mockResolvedValue([]);
  api.fetchAlerts.mockResolvedValue([]);
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["notification_integrations"] });
  api.fetchDiscordWebhook.mockResolvedValue({ connected: true });
  api.fetchT212Status.mockResolvedValue({ connected: false });
  api.fetchStockView.mockResolvedValue({ ticker: "AAPL", currency: "USD" });
  api.fetchHistory.mockResolvedValue({ data: [] });
  api.fetchHoldings.mockResolvedValue([]);
  api.fetchTransactionsPage.mockResolvedValue({ items: [] });
});

it("distinguishes Search's prompt and empty results from request failure, then retries", async () => {
  api.searchTickers
    .mockRejectedValueOnce({ response: { data: { detail: "Search provider unavailable" } } })
    .mockResolvedValue({ results: [] });
  renderPage(Search);
  expect(screen.getByText(/start typing/i)).toBeInTheDocument();

  fireEvent.change(screen.getByPlaceholderText(/search by ticker/i), { target: { value: "AAPL" } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Search provider unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.searchTickers).toHaveBeenCalledTimes(2));
  expect(await screen.findByText(/no matches for/i)).toBeInTheDocument();
});

it("distinguishes no watchlists from a load failure and retries", async () => {
  api.fetchWatchlists
    .mockRejectedValueOnce({ response: { data: { detail: "Watchlists unavailable" } } })
    .mockResolvedValue([]);
  renderPage(Watchlists);

  expect(await screen.findByRole("alert")).toHaveTextContent("Watchlists unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchWatchlists).toHaveBeenCalledTimes(2));
  expect(await screen.findByRole("heading", { name: /track a stock you are researching/i })).toBeInTheDocument();
});

it("distinguishes a disconnected broker from status failure and retries", async () => {
  api.fetchT212Status
    .mockRejectedValueOnce({ response: { data: { detail: "Connection status unavailable" } } })
    .mockResolvedValue({ connected: false });
  renderPage(Settings);

  expect(await screen.findByRole("alert")).toHaveTextContent("Connection status unavailable");
  expect(screen.queryByText("Not connected")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchT212Status).toHaveBeenCalledTimes(2));
  expect(await screen.findByText("Not connected")).toBeInTheDocument();
});

it("shows a safe Stock provider error with Retry and recovers", async () => {
  api.fetchStockView
    .mockRejectedValueOnce({ response: { data: { detail: { private: "raw object" } } } })
    .mockResolvedValue({ ticker: "AAPL" });
  renderPage(Stock, "/stock/AAPL");

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("We couldn't load this data.");
  expect(alert).not.toHaveTextContent("raw object");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchStockView).toHaveBeenCalledTimes(2));
  expect((await screen.findAllByText("Overview for AAPL")).length).toBeGreaterThan(0);
});
