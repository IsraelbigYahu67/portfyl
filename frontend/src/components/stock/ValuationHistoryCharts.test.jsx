import { act, fireEvent, render, screen } from "@testing-library/react";
import ValuationHistoryCharts from "./ValuationHistoryCharts";

const POINTS = [
  { bucket: "2024-01-01", trailing_pe: 14, ev_ebitda: 10, price_to_sales: 7, price_to_cash_flow: 20, price_to_book: 5 },
  { bucket: "2024-02-01", trailing_pe: 15, ev_ebitda: 11, price_to_sales: 8, price_to_cash_flow: 21, price_to_book: 6 },
];

const tile = (key) => screen.getByTestId(`valuation-tile-${key}`);

describe("ValuationHistoryCharts", () => {
  it("opens with the P/E chart showing and its tile out of the strip", () => {
    render(<ValuationHistoryCharts points={POINTS} />);
    expect(screen.getByText("P/E Valuation History")).toBeInTheDocument();
    expect(screen.getByTestId("valuation-chart-panel").parentElement.parentElement).toHaveAttribute("data-open", "true");
    expect(tile("trailing_pe")).toHaveAttribute("data-selected", "true");
    for (const key of ["ev_ebitda", "price_to_sales", "price_to_cash_flow", "price_to_book"]) {
      expect(tile(key)).toHaveAttribute("data-selected", "false");
    }
  });

  it("falls back to the first multiple with data when P/E has none", () => {
    const noPe = POINTS.map((p) => ({ ...p, trailing_pe: null }));
    render(<ValuationHistoryCharts points={noPe} />);
    expect(screen.getByText("EV/EBITDA Valuation History")).toBeInTheDocument();
    expect(tile("trailing_pe")).toHaveAttribute("data-selected", "false");
    expect(tile("ev_ebitda")).toHaveAttribute("data-selected", "true");
  });

  it("opens nothing when no multiple has data", () => {
    const empty = POINTS.map((p) => ({ bucket: p.bucket }));
    render(<ValuationHistoryCharts points={empty} />);
    expect(screen.queryByText(/Valuation History$/)).toBeNull();
  });

  it("opening another chart swaps it in and puts the previous tile back", () => {
    render(<ValuationHistoryCharts points={POINTS} />);
    fireEvent.click(screen.getByRole("button", { name: /Open P\/S valuation history/ }));
    expect(screen.getByText("P/S Valuation History")).toBeInTheDocument();
    expect(tile("trailing_pe")).toHaveAttribute("data-selected", "false");
    expect(tile("price_to_sales")).toHaveAttribute("data-selected", "true");
  });

  it("closes with the close button and with Escape, returning the tile", () => {
    vi.useFakeTimers();
    try {
      render(<ValuationHistoryCharts points={POINTS} />);
      fireEvent.click(screen.getByRole("button", { name: "Close chart" }));
      expect(tile("trailing_pe")).toHaveAttribute("data-selected", "false");
      act(() => { vi.advanceTimersByTime(600); });
      expect(screen.queryByText("P/E Valuation History")).toBeNull();

      fireEvent.click(screen.getByRole("button", { name: /Open P\/B valuation history/ }));
      act(() => { vi.advanceTimersByTime(100); });
      expect(screen.getByText("P/B Valuation History")).toBeInTheDocument();
      fireEvent.keyDown(window, { key: "Escape" });
      expect(tile("price_to_book")).toHaveAttribute("data-selected", "false");
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the open chart when the points are replaced (range switch)", () => {
    const { rerender } = render(<ValuationHistoryCharts points={POINTS} />);
    fireEvent.click(screen.getByRole("button", { name: /Open P\/FCF valuation history/ }));
    rerender(<ValuationHistoryCharts points={POINTS.slice(0, 1)} />);
    expect(screen.getByText("P/FCF Valuation History")).toBeInTheDocument();
    expect(tile("price_to_cash_flow")).toHaveAttribute("data-selected", "true");
  });
});
