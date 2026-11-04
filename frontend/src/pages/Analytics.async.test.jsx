import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Analytics from "./Analytics";

const api = vi.hoisted(() => ({
  fetchRiskMetrics: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
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
  api.fetchBenchmarkComparison
    .mockRejectedValueOnce({ response: { data: { detail: "Comparison unavailable" } } })
    .mockResolvedValue({ series: [] });
});

it("keeps analytics metrics visible when the benchmark comparison fails and retries only it", async () => {
  renderPage();

  expect(await screen.findByRole("heading", { name: /portfolio analytics/i })).toBeInTheDocument();
  expect(await screen.findByText("Sharpe Ratio")).toBeInTheDocument();
  const comparisonSection = screen.getByRole("heading", { name: /active performance/i }).closest("section");
  expect(await within(comparisonSection).findByRole("alert")).toHaveTextContent("Comparison unavailable");

  fireEvent.click(within(comparisonSection).getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchBenchmarkComparison).toHaveBeenCalledTimes(2));
  expect(api.fetchRiskMetrics).toHaveBeenCalledTimes(1);
});
