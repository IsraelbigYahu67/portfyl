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
  fetchHeatmap: vi.fn(),
}));
const activationMocks = vi.hoisted(() => ({
  recordPopulatedDashboard: vi.fn(() => true),
}));
const t212Mocks = vi.hoisted(() => ({ useT212Sync: vi.fn() }));
const editionMocks = vi.hoisted(() => ({ fetchEditionPlanCapabilities: vi.fn() }));

vi.mock("../api", () => api);
vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({ recordPopulatedDashboard: activationMocks.recordPopulatedDashboard }),
}));
vi.mock("@edition-manifest", () => ({
  fetchEditionDashboardSignals: async () => ({ taxReport: null }),
  fetchEditionPlanCapabilities: editionMocks.fetchEditionPlanCapabilities,
}));
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
  usePortfolio: () => ({ current: { id: "portfolio-1" } }),
}));
vi.mock("../hooks/useT212Sync", () => t212Mocks);
vi.mock("../components/DashboardGrid", () => ({
  default: ({ children }) => {
    // Mirror the real grid's fixed widget order.
    const order = ["attention", "performance", "composition", "concentration", "movers", "dividends"];
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
// Like the real Heatmap, the stand-in owns its query, so a rendered heatmap
// is what triggers the (Investor-only) request.
vi.mock("../components/Heatmap", async () => {
  const { useQuery } = await import("@tanstack/react-query");
  return {
    default: () => {
      useQuery({ queryKey: ["heatmap", "1d"], queryFn: () => api.fetchHeatmap("1d") });
      return <div>Healthy heatmap</div>;
    },
  };
});
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
  api.fetchHeatmap.mockResolvedValue([]);
  api.fetchInsiderBuys.mockResolvedValue([]);
  api.fetchDividends.mockResolvedValue([]);
  api.fetchCapabilities.mockResolvedValue({ capabilities: [] });
  editionMocks.fetchEditionPlanCapabilities.mockResolvedValue(null);
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
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["standard_research"] });
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

const insiderBuy = (i, overrides = {}) => ({
  ticker: `T${i}`,
  insider: `Person ${i}`,
  position: "Director",
  shares: 100,
  value: 1000 * (i + 1),
  buy_price: 10,
  current_price: 12,
  pnl: 200,
  pnl_pct: 20,
  date: `2026-09-${String(10 + i).padStart(2, "0")}`,
  currency: "USD",
  ...overrides,
});

it("orders dashboard widgets by purpose", async () => {
  renderPage();

  await screen.findByText("Healthy performance chart");

  const order = ["Attention signals", "Portfolio Performance", "Top 10 Holdings", "Heatmap", "Top Movers", "Earnings Calendar"];
  const nodes = order.map((label) => screen.getByText(label));
  for (let i = 1; i < nodes.length; i += 1) {
    expect(
      nodes[i - 1].compareDocumentPosition(nodes[i]) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  }
});

it("keeps Top 10 Holdings and never calls insider buys without advanced research", async () => {
  renderPage();

  expect(await screen.findByText("Top 10 Holdings")).toBeInTheDocument();
  expect(screen.queryByText("Recent insider buys")).not.toBeInTheDocument();
  expect(api.fetchInsiderBuys).not.toHaveBeenCalled();
});

it("keeps Top 10 Holdings when the edition offers advanced research but the plan does not", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["portfolio_analytics", "advanced_research"] });
  editionMocks.fetchEditionPlanCapabilities.mockResolvedValue(["portfolio_analytics"]);
  renderPage();

  expect(await screen.findByText("Top 10 Holdings")).toBeInTheDocument();
  expect(screen.queryByText("Recent insider buys")).not.toBeInTheDocument();
  expect(api.fetchInsiderBuys).not.toHaveBeenCalled();
  await waitFor(() => expect(api.fetchRiskMetrics).toHaveBeenCalled());
});

it("requests no paid endpoint while the plan is still loading", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["portfolio_analytics", "advanced_research"] });
  editionMocks.fetchEditionPlanCapabilities.mockReturnValue(new Promise(() => {}));
  renderPage();

  expect(await screen.findByText("Recent insider buys")).toBeInTheDocument();
  await screen.findByText("Healthy performance chart");
  expect(api.fetchInsiderBuys).not.toHaveBeenCalled();
  expect(api.fetchRiskMetrics).not.toHaveBeenCalled();
});

it("fails closed to the free widgets when the plan cannot be loaded", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["advanced_research"] });
  editionMocks.fetchEditionPlanCapabilities.mockRejectedValue(new Error("offline"));
  renderPage();

  expect(await screen.findByText("Top 10 Holdings")).toBeInTheDocument();
  expect(api.fetchInsiderBuys).not.toHaveBeenCalled();
});

it("shows a P&L that rounds to zero as a neutral 0.0%, not a red -0.0%", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["advanced_research"] });
  api.fetchInsiderBuys.mockResolvedValue([insiderBuy(0, { pnl: -4.03, pnl_pct: -0.04 })]);
  renderPage();

  const card = (await screen.findByText("Recent insider buys")).closest(".card");
  const pct = await within(card).findByText("0.0%");
  expect(pct).toHaveClass("text-muted");
  expect(within(card).queryByText("-0.0%")).not.toBeInTheDocument();
});

it("replaces Top 10 Holdings with recent insider buys that open the full table in a dialog", async () => {
  api.fetchCapabilities.mockResolvedValue({ capabilities: ["advanced_research"] });
  api.fetchInsiderBuys.mockResolvedValue(Array.from({ length: 10 }, (_, i) => insiderBuy(i)));
  renderPage();

  const card = (await screen.findByText("Recent insider buys")).closest(".card");
  expect(screen.queryByText("Top 10 Holdings")).not.toBeInTheDocument();
  // Compact (jsdom has no layout, so the unmeasured fallback row count):
  // newest first, no shares / buy-price columns.
  await within(card).findByText("T9");
  expect(within(card).queryByText("T1")).not.toBeInTheDocument();
  expect(within(card).queryByText("Buy Price")).not.toBeInTheDocument();
  expect(within(card).getByText("8 of 10 buys · view all")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(within(card).getByRole("button", { name: "Expand insider buys" }));

  const dialog = screen.getByRole("dialog", { name: "Insider buys" });
  expect(within(dialog).getByText("Buy Price")).toBeInTheDocument();
  expect(within(dialog).getByText("T0")).toBeInTheDocument();
  // The page stays put underneath.
  expect(screen.getByText("Healthy performance chart")).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

  fireEvent.click(within(card).getByRole("button", { name: "8 of 10 buys · view all" }));
  fireEvent.keyDown(document, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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

describe("Investor-only widgets (standard_research)", () => {
  const investorEndpoints = () => [api.fetchMovers, api.fetchEarnings, api.fetchHeatmap];

  it("on the Free plan requests no movers, earnings or heatmap and raises no upgrade prompt", async () => {
    // The edition offers standard_research, the workspace's plan does not.
    api.fetchCapabilities.mockResolvedValue({ capabilities: ["standard_research", "portfolio_analytics"] });
    editionMocks.fetchEditionPlanCapabilities.mockResolvedValue([]);
    const denied = vi.fn();
    window.addEventListener("portfyl:entitlement-denied", denied);
    try {
      renderPage();

      await screen.findByText("Healthy performance chart");
      expect(await screen.findAllByText("Dostupné od plánu Investor")).toHaveLength(3);
      for (const link of screen.getAllByRole("link", { name: "Porovnat plány" })) {
        expect(link).toHaveAttribute("href", "/pricing");
      }
      expect(screen.queryByText("Healthy heatmap")).not.toBeInTheDocument();
      investorEndpoints().forEach((endpoint) => expect(endpoint).not.toHaveBeenCalled());
      expect(denied).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("portfyl:entitlement-denied", denied);
    }
  });

  it("on the Investor plan requests movers, earnings and the heatmap", async () => {
    api.fetchCapabilities.mockResolvedValue({ capabilities: ["standard_research"] });
    editionMocks.fetchEditionPlanCapabilities.mockResolvedValue(["standard_research"]);
    renderPage();

    expect(await screen.findByText("Healthy heatmap")).toBeInTheDocument();
    await waitFor(() => investorEndpoints().forEach((endpoint) => expect(endpoint).toHaveBeenCalled()));
    expect(screen.queryByText("Dostupné od plánu Investor")).not.toBeInTheDocument();
  });

  it("requests none of them while the plan is still loading", async () => {
    api.fetchCapabilities.mockResolvedValue({ capabilities: ["standard_research"] });
    editionMocks.fetchEditionPlanCapabilities.mockReturnValue(new Promise(() => {}));
    renderPage();

    await screen.findByText("Healthy performance chart");
    expect(screen.getByText("Top Movers")).toBeInTheDocument();
    expect(screen.queryByText("Dostupné od plánu Investor")).not.toBeInTheDocument();
    expect(screen.queryByText("Healthy heatmap")).not.toBeInTheDocument();
    investorEndpoints().forEach((endpoint) => expect(endpoint).not.toHaveBeenCalled());
  });
});
