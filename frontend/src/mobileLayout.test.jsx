import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DashboardGrid, { ALL_WIDGETS } from "./components/DashboardGrid";
import DividendBarsCard from "./components/dashboard/DividendBarsCard";
import CompositionCard from "./components/dashboard/CompositionCard";
import { CardSortBar, HoldingCards, SORT_OPTIONS } from "./components/HoldingCards";
import MetricCard from "./components/MetricCard";
import { useMediaQuery } from "./hooks/useMediaQuery";

// The real link prefetches through react-query and the portfolio context; the
// card layout is what these tests are about.
vi.mock("./components/TickerLink", () => ({
  TickerLink: ({ ticker, children, className }) => (
    <a className={className} href={`/stock/${ticker}`} onClick={(e) => e.stopPropagation()}>{children ?? ticker}</a>
  ),
}));

// A matchMedia whose answer the test controls; `change()` notifies listeners.
function mockMatchMedia(initial) {
  let matches = initial;
  const listeners = new Set();
  window.matchMedia = vi.fn().mockImplementation(() => ({
    get matches() { return matches; },
    addEventListener: (_e, fn) => listeners.add(fn),
    removeEventListener: (_e, fn) => listeners.delete(fn),
  }));
  return (next) => { matches = next; listeners.forEach((fn) => fn()); };
}

const originalMatchMedia = window.matchMedia;
afterEach(() => { window.matchMedia = originalMatchMedia; localStorage.clear(); });

describe("useMediaQuery", () => {
  it("reports the fallback when matchMedia does not exist", () => {
    window.matchMedia = undefined;
    expect(renderHook(() => useMediaQuery("(max-width: 767px)", false)).result.current).toBe(false);
    expect(renderHook(() => useMediaQuery("(max-width: 767px)", true)).result.current).toBe(true);
  });

  it("follows the query as the viewport changes", () => {
    const change = mockMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(max-width: 767px)"));
    expect(result.current).toBe(false);
    act(() => change(true));
    expect(result.current).toBe(true);
  });
});

describe("HoldingCards", () => {
  const holdings = [
    { ticker: "AAPL", name: "Apple Inc.", shares: 10, avg_cost: 150, current_price: 190, market_value: 41000, pnl: 8500, pnl_percent: 26.2, weight: 32.5, dividends: 120, currency: "USD" },
    { ticker: "MSFT", name: "Microsoft", shares: 2, avg_cost: 400, current_price: 380, market_value: 16000, pnl: -900, pnl_percent: -5.1, weight: 12.5, dividends: 0, currency: "USD" },
  ];
  const fmt = (n) => `${n} CZK`;
  const props = { holdings, currency: "CZK", fmt, fmtSigned: (n) => (n >= 0 ? `+${fmt(n)}` : fmt(n)), fmtNative: (n, c) => `${n} ${c}` };

  it("puts value, P&L and weight on the card, not behind a scroll", () => {
    render(<MemoryRouter><HoldingCards {...props} onOpen={vi.fn()} /></MemoryRouter>);
    const apple = screen.getAllByRole("listitem")[0];
    expect(within(apple).getByText("AAPL")).toBeInTheDocument();
    expect(within(apple).getByText("41000 CZK")).toBeInTheDocument();
    expect(within(apple).getByText(/\+8500 CZK/)).toBeInTheDocument();
    expect(within(apple).getByText("32.50%")).toBeInTheDocument();
    expect(within(screen.getAllByRole("listitem")[1]).getByText(/-5\.10%/)).toBeInTheDocument();
  });

  it("opens the stock when the card is activated by tap or keyboard", () => {
    const onOpen = vi.fn();
    render(<MemoryRouter><HoldingCards {...props} onOpen={onOpen} /></MemoryRouter>);
    const card = screen.getAllByRole("button")[0];
    fireEvent.click(card);
    fireEvent.keyDown(card, { key: "Enter" });
    expect(onOpen).toHaveBeenCalledTimes(2);
    expect(onOpen).toHaveBeenCalledWith("AAPL");
  });

  it("sorts through a 44px select and a direction button", () => {
    const onSort = vi.fn();
    render(<CardSortBar sort={{ key: "market_value", dir: "desc" }} onSort={onSort} options={SORT_OPTIONS} />);
    const select = screen.getByRole("combobox", { name: "Sort holdings" });
    expect(select).toHaveClass("min-h-11");
    fireEvent.change(select, { target: { value: "pnl" } });
    expect(onSort).toHaveBeenCalledWith("pnl");
    fireEvent.click(screen.getByRole("button", { name: /descending/i }));
    expect(onSort).toHaveBeenLastCalledWith("market_value");
  });
});

describe("DividendBarsCard on a phone", () => {
  const months = Array.from({ length: 12 }, (_, i) => ({
    month: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][i],
    amount: 7 + i,
  }));
  const half = { months, total: 200, monthlyAverage: 16 };
  const labelOf = (m) => within(screen.getByTestId(`column-${m}`)).getByText(/Kč/, { selector: "span" });

  it("shows every second value label below sm so neighbours never overlap", () => {
    render(<DividendBarsCard title="Dividends" half={half} totalLabel="Total" currency="CZK" />);
    expect(labelOf("Jan")).not.toHaveClass("hidden");
    expect(labelOf("Feb")).toHaveClass("hidden", "sm:inline");
    expect(labelOf("Mar")).not.toHaveClass("hidden");
  });

  it("keeps every label for a six-month half", () => {
    render(<DividendBarsCard title="Dividends" half={{ ...half, months: months.slice(0, 6) }} totalLabel="Total" currency="CZK" />);
    expect(labelOf("Feb")).not.toHaveClass("hidden");
  });
});

describe("MetricCard", () => {
  it("wraps a long figure instead of cutting it with an ellipsis", () => {
    render(<MetricCard label="Net Profit" value="-1 293 912,50 Kč" />);
    const value = screen.getByText("-1 293 912,50 Kč");
    expect(value).not.toHaveClass("truncate");
    expect(value.className).toMatch(/overflow-wrap:anywhere/);
  });

  it("gives the info icon a 44px touch area on a phone", () => {
    render(<MetricCard label="Sharpe" value="1,2" info={{ title: "Sharpe", what: "Risk-adjusted return." }} />);
    expect(screen.getByRole("button", { name: "What is Sharpe?" }).className).toMatch(/before:-inset-4/);
  });
});

describe("CompositionCard on a phone", () => {
  const breakdown = { sectors: [{ name: "Tech", value: 6000, weight: 60, profit: 1200 }, { name: "Health", value: 4000, weight: 40, profit: -300 }] };
  beforeEach(() => mockMatchMedia(true));

  it("lists each row as a line with value and weight instead of a clipped table", () => {
    render(<MemoryRouter><CompositionCard breakdown={breakdown} currency="USD" /></MemoryRouter>);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const rows = within(screen.getByRole("list", { name: "Composition" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Tech")).toBeInTheDocument();
  });
});

describe("DashboardGrid on a phone", () => {
  const children = Object.fromEntries(ALL_WIDGETS.map((w) => [w.id, <div key={w.id} data-testid={`child-${w.id}`}>{w.label} body</div>]));

  beforeEach(() => { localStorage.clear(); mockMatchMedia(true); });

  it("starts with only Top movers open and the rest collapsed", () => {
    render(<DashboardGrid>{children}</DashboardGrid>);
    expect(screen.getByTestId("child-movers")).toBeInTheDocument();
    expect(screen.queryByTestId("child-performance")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Performance$/ })).toHaveAttribute("aria-expanded", "false");
    // The core widget leads, the others follow.
    expect(screen.getAllByRole("button")[0]).toHaveTextContent("Movers");
  });

  it("expands a widget on tap and remembers it", () => {
    const { unmount } = render(<DashboardGrid>{children}</DashboardGrid>);
    fireEvent.click(screen.getByRole("button", { name: /^Performance$/ }));
    expect(screen.getByTestId("child-performance")).toBeInTheDocument();
    unmount();
    render(<DashboardGrid>{children}</DashboardGrid>);
    expect(screen.getByTestId("child-performance")).toBeInTheDocument();
  });
});
