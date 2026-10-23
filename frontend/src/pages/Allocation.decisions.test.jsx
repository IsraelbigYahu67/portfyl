import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Allocation from "./Allocation";
import { legacyColorClassesIn } from "../test/legacyClasses";

const api = vi.hoisted(() => ({
  fetchAllHoldings: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
}));
const t212Mocks = vi.hoisted(() => ({ useT212Sync: vi.fn() }));
const portfolio = vi.hoisted(() => ({ id: "portfolio-1" }));
const targetMounts = vi.hoisted(() => ({ count: 0 }));

vi.mock("../api", () => api);
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
  usePortfolio: () => ({ current: { id: portfolio.id } }),
}));
vi.mock("../hooks/useT212Sync", () => t212Mocks);
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
  useStockDetail: () => ({ openStock: vi.fn() }),
}));
vi.mock("../components/BreakdownChart", () => ({
  default: ({ title }) => <div>{title}</div>,
}));
vi.mock("../components/AllocationTargets", async () => {
  const { useState } = await import("react");
  return {
    default: function TargetsStub({ currency }) {
      const [instance] = useState(() => ++targetMounts.count);
      return <section aria-label="Target allocation" data-instance={instance}>targets in {currency}</section>;
    },
  };
});

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
    t212Mocks.useT212Sync.mockReturnValue({ connected: false, positionsQuery: {} });
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

  it("shows a broker snapshot separately from ledger-derived allocation", async () => {
    t212Mocks.useT212Sync.mockReturnValue({
      connected: true,
      positionsQuery: {
        data: { status: "fresh", currency: "USD", positions: [{ ticker: "TSLA", quantity: 4, market_value: null }] },
        isLoading: false, isError: false,
      },
    });
    renderPage();

    const snapshot = await screen.findByRole("region", { name: "Trading 212 current positions" });
    expect(snapshot).not.toHaveTextContent("TSLA");
    fireEvent.click(screen.getByRole("button", { name: "Show positions" }));
    expect(snapshot).toHaveTextContent("TSLA");
    expect(screen.getByText(/allocation charts use imported transactions/i)).toBeInTheDocument();
    expect(await screen.findByText(/Largest position/i)).toBeInTheDocument();
  });

  it("shows the target allocation section", async () => {
    renderPage();
    expect(await screen.findByRole("region", { name: "Target allocation" })).toHaveTextContent("USD");
  });

  it("starts a fresh target editor when the active portfolio changes", async () => {
    portfolio.id = "portfolio-1";
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const page = () => (
      <QueryClientProvider client={qc}>
        <Allocation />
      </QueryClientProvider>
    );
    const { rerender } = render(page());
    const first = (await screen.findByRole("region", { name: "Target allocation" })).dataset.instance;

    portfolio.id = "portfolio-2";
    rerender(page());

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Target allocation" }).dataset.instance).not.toBe(first)
    );
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

  it("marks a holding whose price is out of date or missing", async () => {
    api.fetchAllHoldings.mockResolvedValue([
      { ticker: "AAPL", name: "Apple", shares: 10, avg_cost: 100, current_price: 100, currency: "USD", market_value: 1000, weight: 100, closed: false, pnl: 10, pnl_percent: 1, dividends: 0, price_status: "stale", price_source: "Yahoo Finance", price_as_of: "2026-09-01T20:00:00Z" },
      { ticker: "GONE", name: "Gone Co", shares: 5, avg_cost: 10, current_price: 0, currency: "USD", market_value: 0, weight: 0, closed: false, pnl: -50, pnl_percent: -100, dividends: 0, price_status: "missing", price_source: "Yahoo Finance", price_as_of: null },
    ]);
    renderPage();

    const stale = await screen.findByText("out of date");
    expect(stale).toHaveAttribute("title", expect.stringMatching(/^Yahoo Finance · price is out of date · last quote/));
    expect(screen.getByText("no price")).toHaveAttribute(
      "title",
      "Yahoo Finance · no current price; this holding is valued at 0",
    );
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

  it("All Holdings lists only active positions in the Active view", async () => {
    renderPage();
    await screen.findByText(/Largest position/i);

    expect(screen.getByRole("columnheader", { name: /Ticker/ })).toBeInTheDocument();
    expect(screen.getByText("Apple")).toBeInTheDocument();
    expect(screen.queryByText("Old Co")).not.toBeInTheDocument();
    expect(screen.queryByText("Sold")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sold positions" }));
    await screen.findByText("Value if held");
    expect(screen.getByText("Sold")).toBeInTheDocument();
  });

  it("legend percentages share one precision", async () => {
    api.fetchAllHoldings.mockResolvedValue([
      { ticker: "AAA", name: "Aaa", shares: 1, avg_cost: 1, current_price: 1, currency: "USD", market_value: 60, weight: 6, closed: false, pnl: 1, pnl_percent: 1, dividends: 0 },
      { ticker: "BBB", name: "Bbb", shares: 1, avg_cost: 1, current_price: 1, currency: "USD", market_value: 81, weight: 8.12, closed: false, pnl: 1, pnl_percent: 1, dividends: 0 },
    ]);
    renderPage();
    await screen.findByText(/Largest position/i);

    const table = screen.getByRole("table", { name: "All holdings" });
    expect(within(table).getByText("6.00%")).toBeInTheDocument();
    expect(within(table).getByText("8.12%")).toBeInTheDocument();
  });

  it("fades the table edge and pins the ticker column while the table scrolls sideways", async () => {
    const widths = vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(900);
    const visible = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(400);
    try {
      renderPage();
      await screen.findByText(/Largest position/i);

      const scroller = screen.getByRole("table", { name: "All holdings" }).parentElement;
      await waitFor(() => expect(scroller).toHaveAttribute("data-scroll-cue", "true"));
      expect(scroller.style.maskImage || scroller.style.webkitMaskImage).toMatch(/linear-gradient/);
      expect(screen.getByRole("columnheader", { name: /Ticker/ })).toHaveClass("sticky");
    } finally {
      widths.mockRestore();
      visible.mockRestore();
    }
  });

  it("uses no legacy Tailwind palette colors", async () => {
    expect(await legacyColorClassesIn(new URL("./Allocation.jsx", import.meta.url))).toEqual([]);
  });
});
