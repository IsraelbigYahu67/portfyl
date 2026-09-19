import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Allocation from "./Allocation";

const api = vi.hoisted(() => ({
  fetchAllHoldings: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../App", () => ({ useCurrency: () => ({ currency: "USD", rate: 22 }) }));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
  useStockDetail: () => ({ openStock: vi.fn() }),
}));
vi.mock("../components/BreakdownChart", () => ({
  default: ({ title }) => <div>{title}</div>,
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Allocation />
    </QueryClientProvider>
  );
}

describe("Allocation composition decisions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchAllHoldings.mockResolvedValue([
      { ticker: "AAPL", name: "Apple", shares: 10, avg_cost: 100, current_price: 100, currency: "USD", market_value: 1000, weight: 70, closed: false, pnl: 10, pnl_percent: 1, dividends: 0 },
      { ticker: "OLD", name: "Old Co", shares: 0, avg_cost: 100, current_price: 100, currency: "USD", market_value: 0, weight: 0, closed: true, pnl: 0, pnl_percent: 0, dividends: 0, pnl_if_held: 5, pnl_if_held_pct: 2 },
    ]);
    api.fetchSectorBreakdown.mockResolvedValue({
      sectors: [{ name: "Technology", value: 700, weight: 70 }, { name: "Healthcare", value: 300, weight: 30 }],
      asset_types: [],
      currencies: [],
      countries: [],
    });
  });

  it("offers composition categories and switches the chart and list", async () => {
    renderPage();

    expect(await screen.findByText(/Largest position/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Position" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sector" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Asset type" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Currency" })).toBeInTheDocument();
    expect(screen.getByText("Positions")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sector" }));
    expect(await screen.findByText("Sector Allocation")).toBeInTheDocument();
    expect(screen.getAllByText("Technology").length).toBeGreaterThan(0);
  });

  it("separates active and sold positions", async () => {
    renderPage();
    await screen.findByText(/Largest position/i);

    expect(screen.getByRole("list", { name: "Full allocation breakdown" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sold positions" }));
    await waitFor(() =>
      expect(screen.queryByRole("list", { name: "Full allocation breakdown" })).not.toBeInTheDocument()
    );
    expect(screen.getByText("Value if held")).toBeInTheDocument();
    expect(screen.getAllByText("OLD").length).toBeGreaterThan(0);
  });

  it("sold-position badges and if-held notes use financial-meta, never text-[10px]", async () => {
    renderPage();
    await screen.findByText(/Largest position/i);
    fireEvent.click(screen.getByRole("button", { name: "Sold positions" }));
    await screen.findByText("Value if held");

    expect(screen.getByText("Sold")).toHaveClass("financial-meta");
    expect(screen.getByText(/if held: \+\$5\.00/)).toHaveClass("financial-meta");
    expect(screen.getByText(/if held: \+2\.00%/)).toHaveClass("financial-meta");
  });
});
