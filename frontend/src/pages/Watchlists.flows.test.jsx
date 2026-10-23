import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { legacyColorClassesIn } from "../test/legacyClasses";
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
vi.mock("../hooks/useStockIntentPrefetch", () => ({ useStockIntentPrefetch: () => ({}) }));

const lists = [
  { id: "one", name: "Ideas", count: 2, items: [
    { id: "a", ticker: "AAPL", quote: { name: "Apple", change_percent: 2, market_cap: 10 } },
    { id: "b", ticker: "BETA", quote: { name: "Beta Corp", change_percent: -1, market_cap: 20 } },
  ] },
  { id: "two", name: "Second", count: 1, items: [
    { id: "m", ticker: "MSFT", quote: { name: "Microsoft", change_percent: 1, market_cap: 30 } },
  ] },
];

function RouteProbe() {
  const location = useLocation();
  const navigate = useNavigate();
  return <><output data-testid="location">{location.search}</output><button onClick={() => navigate(-1)}>Browser back</button></>;
}

function renderPage(path = "/watchlists") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}><ToastProvider><ConfirmProvider>
        <RouteProbe />
        <Routes>
          <Route path="/watchlists" element={<Watchlists />} />
          <Route path="/stock/:ticker" element={<h1>Stock research</h1>} />
        </Routes>
      </ConfirmProvider></ToastProvider></MemoryRouter>
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

it("keeps list search and sorting through stock navigation, back, and reload", async () => {
  const page = renderPage("/watchlists?from=research");
  await screen.findByRole("link", { name: /AAPL Apple/i });
  fireEvent.change(screen.getByRole("textbox", { name: "Search Ideas" }), { target: { value: "beta" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Sort Ideas" }), { target: { value: "change_desc" } });
  const savedSearch = screen.getByTestId("location").textContent;
  expect(savedSearch).toContain("from=research");
  fireEvent.click(screen.getByRole("link", { name: /BETA Beta Corp/i }));
  expect(screen.getByRole("heading", { name: "Stock research" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Browser back" }));
  expect(await screen.findByRole("textbox", { name: "Search Ideas" })).toHaveValue("beta");
  expect(screen.getByRole("combobox", { name: "Sort Ideas" })).toHaveValue("change_desc");
  expect(screen.queryByRole("link", { name: /AAPL Apple/i })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Search Second" })).toHaveValue("");
  page.unmount();
  renderPage(`/watchlists${savedSearch}`);
  expect(await screen.findByRole("textbox", { name: "Search Ideas" })).toHaveValue("beta");
  expect(screen.getByRole("combobox", { name: "Sort Ideas" })).toHaveValue("change_desc");
});

it.each(["fetchCapabilities", "fetchDiscordWebhook"])("blocks alert creation until %s resolves", async (request) => {
  let resolveStatus;
  api[request].mockImplementationOnce(() => new Promise((resolve) => { resolveStatus = resolve; }));
  renderPage();
  await screen.findByRole("link", { name: /AAPL Apple/i });
  expect(screen.getByRole("button", { name: "Create price alert for AAPL" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Alert ticker" }), { target: { value: "AAPL" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Target price" }), { target: { value: "200" } });
  expect(screen.getByRole("button", { name: "Add alert" })).toBeDisabled();
  expect(api.createAlert).not.toHaveBeenCalled();
  resolveStatus(request === "fetchCapabilities" ? { capabilities: ["notification_integrations"] } : { connected: true });
  await waitFor(() => expect(screen.getByRole("button", { name: "Create price alert for AAPL" })).toBeEnabled());
  expect(screen.getByRole("button", { name: "Add alert" })).toBeEnabled();
});

it("explains capability-denied alerts even when Discord is connected", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: [] });
  renderPage();
  expect((await screen.findAllByText(/notification integrations are not available/i)).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Create price alert for AAPL" })).toBeDisabled();
});

it("price alerts render after the watchlists", async () => {
  renderPage();
  const firstList = await screen.findByRole("link", { name: /AAPL Apple/i });
  const alertsTitle = screen.getByText("Price Alerts");
  expect(firstList.compareDocumentPosition(alertsTitle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

it("alert inputs and buttons use the shared Clay controls", async () => {
  renderPage();
  await screen.findByRole("link", { name: /AAPL Apple/i });
  expect(screen.getByRole("textbox", { name: "Alert ticker" })).toHaveClass("input");
  expect(screen.getByRole("spinbutton", { name: "Target price" })).toHaveClass("input");
  expect(screen.getByRole("button", { name: "Add alert" })).toHaveClass("btn-primary");
  expect(screen.getByRole("button", { name: "Create" })).toHaveClass("btn-primary");
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./Watchlists.jsx", import.meta.url))).toEqual([]);
});
