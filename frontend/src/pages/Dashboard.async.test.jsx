import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Dashboard from "./Dashboard";
import { sourcePath } from "../test/sourcePath";

const api = vi.hoisted(() => ({
  fetchSummary: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchPerformance: vi.fn(),
  fetchBenchmarks: vi.fn(),
  fetchMovers: vi.fn(),
  fetchEarnings: vi.fn(),
  fetchInsiderBuys: vi.fn(),
  fetchDividends: vi.fn(),
  fetchCapabilities: vi.fn(),
  fetchRiskMetrics: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
  fetchAllocationTargetDrift: vi.fn(),
  fetchDividendForecast: vi.fn(),
}));
const activationMocks = vi.hoisted(() => ({
  recordPopulatedDashboard: vi.fn(() => true),
}));
const t212Mocks = vi.hoisted(() => ({ useT212Sync: vi.fn() }));

vi.mock("../api", () => api);
vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({ recordPopulatedDashboard: activationMocks.recordPopulatedDashboard }),
}));
vi.mock("@edition-manifest", () => ({
  fetchEditionDashboardSignals: async () => ({ taxReport: null }),
}));
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
  usePortfolio: () => ({ current: { id: "portfolio-1" } }),
}));
vi.mock("../hooks/useT212Sync", () => t212Mocks);
vi.mock("../components/DashboardGrid", () => ({
  default: ({ children }) => {
    // Mirror the real grid's fixed widget order.
    const order = ["attention", "performance", "composition", "insiderBuys", "concentration", "movers", "dividends"];
    return (
      <div>
        {order
          .filter((key) => children[key])
          .map((key) => <section key={key}>{children[key]}</section>)}
      </div>
    );
  },
}));
vi.mock("../components/PortfolioHero", () => ({
  default: () => <div>Healthy portfolio hero</div>,
}));
vi.mock("../components/PerformanceChart", () => ({
  default: () => <div>Healthy performance chart</div>,
}));
vi.mock("../components/Heatmap", () => ({ default: () => <div>Healthy heatmap</div> }));
vi.mock("../components/TickerLink", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  t212Mocks.useT212Sync.mockReturnValue({ connected: false, positionsQuery: {} });
  api.fetchSummary.mockResolvedValue({ total_value: 1000, total_pnl: 100 });
  api.fetchHoldings.mockResolvedValue([{ ticker: "MSFT", weight: 100, market_value: 1000 }]);
  api.fetchPerformance.mockResolvedValue([{ date: "2026-09-01", value: 1000 }]);
  api.fetchBenchmarks.mockResolvedValue({});
  api.fetchMovers
    .mockRejectedValueOnce({ response: { data: { detail: "Movers unavailable" } } })
    .mockResolvedValue({ gainers: [], losers: [] });
  api.fetchEarnings.mockResolvedValue([]);
  api.fetchInsiderBuys.mockResolvedValue([]);
  api.fetchDividends.mockResolvedValue([]);
  api.fetchCapabilities.mockResolvedValue({ capabilities: [] });
});

it("shows current T212 quantities from the snapshot while historical dashboard widgets stay separate", async () => {
  t212Mocks.useT212Sync.mockReturnValue({
    connected: true,
    positionsQuery: {
      data: { status: "fresh", currency: "USD", positions: [{ ticker: "AAPL", quantity: 3, market_value: null }] },
      isLoading: false, isError: false,
    },
  });
  renderPage();

  expect(await screen.findByRole("region", { name: "Trading 212 current positions" })).toHaveTextContent("3 shares");
  expect(screen.getByText(/historical performance uses imported transactions/i)).toBeInTheDocument();
  expect(screen.getByText("Healthy portfolio hero")).toBeInTheDocument();
});

it("keeps healthy dashboard widgets visible when Movers fails and retries only Movers", async () => {
  renderPage();

  expect(await screen.findByText("Healthy portfolio hero")).toBeInTheDocument();
  expect(await screen.findByText("Healthy performance chart")).toBeInTheDocument();
  const moversCard = screen.getByText("Top Movers").closest(".card");
  expect(within(moversCard).getByRole("alert")).toHaveTextContent("Movers unavailable");

  fireEvent.click(within(moversCard).getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchMovers).toHaveBeenCalledTimes(2));
  expect(api.fetchSummary).toHaveBeenCalledTimes(1);
  expect(api.fetchHoldings).toHaveBeenCalledTimes(1);
  expect(api.fetchPerformance).toHaveBeenCalledTimes(1);
});

it("orders dashboard widgets by purpose and collapses insider activity", async () => {
  renderPage();

  await screen.findByText("Healthy performance chart");

  const order = ["Attention signals", "Portfolio Performance", "Insider activity (1Y)", "Top 10 Holdings", "Top Movers", "Earnings Calendar"];
  const nodes = order.map((label) => screen.getByText(label));
  for (let i = 1; i < nodes.length; i += 1) {
    expect(
      nodes[i - 1].compareDocumentPosition(nodes[i]) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  }
});

it("gives the heatmap an accessible data summary", async () => {
  api.fetchHoldings.mockResolvedValue([{ ticker: "MSFT", weight: 100, market_value: 1000 }]);
  renderPage();

  await screen.findByText("Healthy heatmap");
  expect(screen.getByRole("group", { name: "Heatmap holdings data" })).toHaveTextContent("MSFT");
});

it("records a populated dashboard once summary and holdings both load with real data", async () => {
  renderPage();
  await screen.findByText("Healthy performance chart");
  await waitFor(() => expect(activationMocks.recordPopulatedDashboard).toHaveBeenCalledTimes(1));
});

it("does not record a populated dashboard while summary is still loading", async () => {
  let resolveSummary;
  api.fetchSummary.mockReturnValueOnce(new Promise((resolve) => { resolveSummary = resolve; }));
  renderPage();
  await screen.findByText("Healthy performance chart");
  expect(activationMocks.recordPopulatedDashboard).not.toHaveBeenCalled();
  resolveSummary({ total_value: 1000, total_pnl: 100 });
  await waitFor(() => expect(activationMocks.recordPopulatedDashboard).toHaveBeenCalledTimes(1));
});

it("does not record a populated dashboard when summary fails to load", async () => {
  api.fetchSummary.mockRejectedValueOnce(new Error("boom"));
  renderPage();
  await waitFor(() => expect(api.fetchSummary).toHaveBeenCalled());
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(activationMocks.recordPopulatedDashboard).not.toHaveBeenCalled();
});

it("does not record a populated dashboard when holdings are empty", async () => {
  api.fetchHoldings.mockResolvedValue([]);
  renderPage();
  await waitFor(() => expect(api.fetchHoldings).toHaveBeenCalled());
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(activationMocks.recordPopulatedDashboard).not.toHaveBeenCalled();
});

it("keeps insider table headers and notes at least 12px in source (no text-[10px]/text-[11px])", async () => {
  const { readFile } = await import("node:fs/promises");
  const assetUrl = new URL("./Dashboard.jsx", import.meta.url);
  const pathname = sourcePath(assetUrl);
  const src = await readFile(pathname, "utf-8");
  expect(src).not.toMatch(/text-\[(8|9|10|11)px\]/);
});

it("shows where prices come from and when they were quoted instead of the request time", async () => {
  api.fetchSummary.mockResolvedValue({
    total_value: 1000,
    total_pnl: 100,
    holdings_count: 1,
    last_updated: "2026-10-09T20:00:00",
    prices_as_of: "2026-10-09T17:44:00Z",
    price_delay_minutes: 15,
    price_source: "Yahoo Finance",
    price_issues: [],
  });
  renderPage();

  expect(await screen.findByText(/^Prices from Yahoo Finance · delayed up to 15 min · last quote/)).toBeInTheDocument();
  expect(screen.queryByText(/^Updated /)).not.toBeInTheDocument();
});

it("raises a holding with no current price in Needs attention", async () => {
  api.fetchHoldings.mockResolvedValue([
    { ticker: "MSFT", weight: 100, market_value: 1000, price_status: "delayed" },
    { ticker: "GONE", weight: 0, market_value: 0, price_status: "missing" },
  ]);
  renderPage();

  expect(await screen.findByText("No current price: GONE")).toBeInTheDocument();
});

it("adds IRR, composition and dividend cards when the workspace has the analytics capabilities", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["portfolio_analytics", "dividend_analysis"] });
  api.fetchSummary.mockResolvedValue({ total_value: 1000, total_pnl: 100, total_pnl_percent: 11.1, total_invested: 900 });
  api.fetchRiskMetrics.mockResolvedValue({ lifetime: { xirr: 11.4 } });
  api.fetchSectorBreakdown.mockResolvedValue({
    total_value: 1000,
    asset_types: [{ name: "Stocks", value: 1000, weight: 100 }],
    sectors: [],
    countries: [],
  });
  api.fetchAllocationTargetDrift.mockResolvedValue({ groups: [{ group: "Stocks", target_pct: 90 }] });
  api.fetchDividendForecast.mockResolvedValue({
    year: 2026,
    months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((month) => ({ month, paid: 5, estimated: 5, entries: [] })),
  });
  renderPage();

  expect(await screen.findByText(/^IRR \+11\.40% · /)).toBeInTheDocument();
  expect(await screen.findByText("Portfolio composition")).toBeInTheDocument();
  expect(screen.getByText("90% · +10.0 pp")).toBeInTheDocument();
  const received = screen.getByText("Dividends received");
  const upcoming = screen.getByText("Upcoming payments");
  // Received sits to the left of upcoming (first in the two-column grid).
  expect(received.compareDocumentPosition(upcoming) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByText("Next 12 months")).toBeInTheDocument();
  expect(api.fetchRiskMetrics).toHaveBeenCalledWith("1y", null);
});

it("leaves paid widgets out and never calls their endpoints without the capabilities", async () => {
  renderPage();

  await screen.findByText("Healthy performance chart");
  expect(screen.queryByText("Portfolio composition")).not.toBeInTheDocument();
  expect(screen.queryByText("Upcoming payments")).not.toBeInTheDocument();
  expect(screen.getByText("Total profit")).toBeInTheDocument();
  expect(screen.getByText("Passive income")).toBeInTheDocument();
  expect(api.fetchRiskMetrics).not.toHaveBeenCalled();
  expect(api.fetchSectorBreakdown).not.toHaveBeenCalled();
  expect(api.fetchDividendForecast).not.toHaveBeenCalled();
});
