import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Analytics from "./Analytics";

const api = vi.hoisted(() => ({
  fetchRiskMetrics: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
  fetchCorrelation: vi.fn(),
  fetchBenchmarkCatalog: vi.fn(),
  fetchBenchmarkComparison: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
}));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Analytics />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchBenchmarkCatalog.mockResolvedValue([]);
  api.fetchRiskMetrics.mockResolvedValue({
    sharpe_ratio: 1.2,
    sortino_ratio: 1.4,
    total_return: 8,
    annualized_return: 8,
    annualized_volatility: 10,
    win_rate: 55,
    positive_days: 11,
    negative_days: 9,
    max_drawdown: -5,
    current_drawdown: -1,
    best_day: 2,
    worst_day: -2,
  });
  api.fetchBenchmarkComparison.mockResolvedValue({ series: [] });
  api.fetchSectorBreakdown.mockResolvedValue({ sectors: [], countries: [], asset_types: [] });
  api.fetchCorrelation
    .mockRejectedValueOnce({ response: { data: { detail: "Correlation unavailable" } } })
    .mockResolvedValue({ tickers: [], matrix: [] });
});

it("keeps analytics metrics visible when correlation fails and retries only correlation", async () => {
  renderPage();

  expect(await screen.findByRole("heading", { name: /portfolio analytics/i })).toBeInTheDocument();
  expect(await screen.findByText("Sharpe Ratio")).toBeInTheDocument();
  const correlationCard = screen.getByRole("heading", { name: /correlation matrix/i }).closest(".card");
  expect(within(correlationCard).getByRole("alert")).toHaveTextContent("Correlation unavailable");

  fireEvent.click(within(correlationCard).getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchCorrelation).toHaveBeenCalledTimes(2));
  expect(api.fetchRiskMetrics).toHaveBeenCalledTimes(1);
  expect(api.fetchBenchmarkComparison).toHaveBeenCalledTimes(1);
  expect(api.fetchSectorBreakdown).toHaveBeenCalledTimes(1);
});
