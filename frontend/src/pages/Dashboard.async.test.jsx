import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Dashboard from "./Dashboard";

const api = vi.hoisted(() => ({
  fetchSummary: vi.fn(),
  fetchHoldings: vi.fn(),
  fetchPerformance: vi.fn(),
  fetchBenchmarks: vi.fn(),
  fetchMovers: vi.fn(),
  fetchEarnings: vi.fn(),
  fetchInsiderBuys: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
}));
vi.mock("../components/DashboardGrid", () => ({
  default: ({ children }) => (
    <div>{Object.entries(children).map(([key, child]) => <section key={key}>{child}</section>)}</div>
  ),
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
      <Dashboard />
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
