import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ConfirmProvider } from "../components/ui/ConfirmDialog";
import { ToastProvider } from "../components/ui/Toast";
import Watchlists from "./Watchlists";

const api = vi.hoisted(() => ({
  fetchWatchlists: vi.fn(),
  createWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  addWatchlistItem: vi.fn(),
  removeWatchlistItem: vi.fn(),
  searchTickers: vi.fn(),
  fetchAlerts: vi.fn(),
  createAlert: vi.fn(),
  updateAlert: vi.fn(),
  deleteAlert: vi.fn(),
  checkAlerts: vi.fn(),
  fetchCapabilities: vi.fn(),
  fetchDiscordWebhook: vi.fn(),
}));
vi.mock("../api", () => api);

const lists = [
  { id: "one", name: "Ideas", count: 2, items: [
    { id: "a", ticker: "AAPL", quote: { name: "Apple", change_percent: 2, market_cap: 10 } },
    { id: "b", ticker: "BETA", quote: { name: "Beta Corp", change_percent: -1, market_cap: 20 } },
  ] },
  { id: "two", name: "Second", count: 1, items: [
    { id: "m", ticker: "MSFT", quote: { name: "Microsoft", change_percent: 1, market_cap: 30 } },
  ] },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><ToastProvider><ConfirmProvider><Watchlists /></ConfirmProvider></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchWatchlists.mockResolvedValue(lists);
  api.fetchAlerts.mockResolvedValue([{ id: "alert-1", ticker: "AAPL", status: "active", enabled: true, direction: "above", target_price: 200 }]);
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["notification_integrations"] });
  api.fetchDiscordWebhook.mockResolvedValue({ connected: true });
  api.searchTickers.mockResolvedValue({ results: [] });
});

it("filters a list locally and exposes matching alert status", async () => {
  renderPage();
  expect((await screen.findAllByText("Active")).length).toBeGreaterThan(0);
  fireEvent.change(screen.getByRole("textbox", { name: "Search Ideas" }), { target: { value: "beta" } });
  expect(screen.queryByRole("link", { name: /AAPL Apple/i })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /BETA Beta Corp/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /MSFT Microsoft/i })).toBeInTheDocument();
});

it("optimistically removes one item and restores only that list on failure", async () => {
  let rejectRemoval;
  api.removeWatchlistItem.mockImplementation(() => new Promise((_resolve, reject) => { rejectRemoval = reject; }));
  renderPage();
  await screen.findByRole("link", { name: /AAPL Apple/i });

  fireEvent.click(screen.getByRole("button", { name: "Remove AAPL from Ideas" }));
  expect(await screen.findByRole("alertdialog")).toHaveTextContent("Remove AAPL from Ideas?");
  fireEvent.click(screen.getByRole("button", { name: "Remove ticker" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: /AAPL Apple/i })).not.toBeInTheDocument());
  expect(screen.getByRole("link", { name: /MSFT Microsoft/i })).toBeInTheDocument();

  rejectRemoval(new Error("network down"));
  expect(await screen.findByRole("link", { name: /AAPL Apple/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /MSFT Microsoft/i })).toBeInTheDocument();
});

it("disables alert creation with a reason and notifications deep link", async () => {
  api.fetchDiscordWebhook.mockResolvedValue({ connected: false });
  renderPage();
  expect((await screen.findAllByText(/Discord is not connected/i)).length).toBeGreaterThan(0);
  expect(screen.getAllByRole("link", { name: /notifications/i })[0]).toHaveAttribute("href", "/settings?section=notifications");
  expect(screen.getByRole("button", { name: "Create price alert for AAPL" })).toBeDisabled();
});
