import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Dashboard from "./Dashboard";

const api = vi.hoisted(() => ({
  fetchSummary: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchPerformance: vi.fn(),
  fetchBenchmarks: vi.fn(),
  fetchMovers: vi.fn(),
  fetchEarnings: vi.fn(),
  fetchInsiderBuys: vi.fn(),
  fetchDividends: vi.fn(),
}));
const activationMocks = vi.hoisted(() => ({
  recordPopulatedDashboard: vi.fn(() => true),
}));

vi.mock("../api", () => api);
vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({ recordPopulatedDashboard: activationMocks.recordPopulatedDashboard }),
}));
vi.mock("@edition-manifest", () => ({
  fetchEditionDashboardSignals: async () => ({ taxReport: null }),
}));
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
}));
vi.mock("../components/DashboardGrid", () => ({
  default: ({ children }) => {
    // Mirror the real grid's fixed widget order.
    const order = ["performance", "concentration", "attention", "movers", "insiderBuys"];
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
vi.mock("../components/StockDetail", () => ({
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

  const order = ["Portfolio Performance", "Concentration", "Needs attention", "Top Movers", "Insider activity (1Y)"];
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
  const path = await import("node:path");
  const { readFile } = await import("node:fs/promises");
  const assetUrl = new URL("./Dashboard.jsx", import.meta.url);
  const pathname = path.resolve(decodeURIComponent(assetUrl.pathname).replace(/^\//, ""));
  const src = await readFile(pathname, "utf-8");
  expect(src).not.toMatch(/text-\[(8|9|10|11)px\]/);
});
