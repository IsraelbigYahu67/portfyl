import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import Analytics from "./Analytics";

const api = vi.hoisted(() => ({
  fetchRiskMetrics: vi.fn(),
  fetchBenchmarkComparison: vi.fn(),
  fetchCorrelation: vi.fn(),
  fetchBenchmarkCatalog: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({ useCurrency: () => ({ currency: "USD", rate: 22 }) }));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Analytics />
    </QueryClientProvider>
  );
}

describe("Analytics decisions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchBenchmarkCatalog.mockResolvedValue([{ id: 1, name: "S&P 500", is_preset: true, is_default: true }]);
    api.fetchRiskMetrics.mockResolvedValue({
      benchmark: { name: "S&P 500" },
      sharpe_ratio: 1.2,
      sortino_ratio: 1.4,
      total_return: 8,
      annualized_return: 8,
      annualized_volatility: 10,
      win_rate: 55,
      max_drawdown: -5,
      current_drawdown: -1,
      best_day: 2,
      worst_day: -2,
    });
    api.fetchBenchmarkComparison.mockResolvedValue({
      benchmark: { name: "S&P 500" },
      metrics: { active_return: 1, tracking_error: 2, information_ratio: 0.5, correlation: 0.9, up_capture: 1.1, down_capture: 0.9 },
      series: [
        { date: "2026-01-01", portfolio_pct: 1, benchmark_pct: 0.8, active_pct: 0.2 },
        { date: "2026-02-01", portfolio_pct: 3, benchmark_pct: 2, active_pct: 1 },
      ],
    });
    api.fetchCorrelation.mockResolvedValue({
      tickers: ["AAPL", "MSFT", "TSLA"],
      matrix: [
        [1, 0.9, -0.2],
        [0.9, 1, 0.1],
        [-0.2, 0.1, 1],
      ],
    });
  });

  it("is risk-first and drops the allocation duplicates", async () => {
    renderPage();

    const risk = await screen.findByText(/Time-Weighted/i);
    const comparison = await screen.findByText(/Active Performance/i);
    const correlations = await screen.findByText("Strongest Correlations");

    expect(
      risk.compareDocumentPosition(comparison) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      comparison.compareDocumentPosition(correlations) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    expect(screen.queryByText("Sector Allocation")).not.toBeInTheDocument();
    expect(screen.queryByText("Country Exposure")).not.toBeInTheDocument();
    expect(screen.queryByText("Asset Type Breakdown")).not.toBeInTheDocument();
  });

  it("shows period and data-loaded context", async () => {
    renderPage();
    await screen.findByText(/Time-Weighted/i);

    expect(screen.getAllByText(/Period: 1Y · Data loaded/).length).toBeGreaterThan(0);
  });

  it("correlation matrix cells use the financial-data semantic class, not sub-12px text", async () => {
    const { container } = renderPage();
    await screen.findByText(/Time-Weighted/i);
    await screen.findAllByText("-0.20");
    const matrixCells = container.querySelectorAll(".financial-data");
    const values = Array.from(matrixCells).map((el) => el.textContent);
    expect(values).toContain("-0.20");
  });
});
