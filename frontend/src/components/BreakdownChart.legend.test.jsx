import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import BreakdownChart from "./BreakdownChart";

const data = [
  { name: "AAPL", weight: 40, value: 41000 },
  { name: "BRK.B", weight: 25, value: 25500 },
  { name: "MSFT", weight: 20, value: 20100 },
  { name: "Other", weight: 15, value: 15400 },
];

const original = window.matchMedia;
afterEach(() => { window.matchMedia = original; });

describe("BreakdownChart two-column legend", () => {
  it("lays each legend column out as a ticker / % / value grid with one shared gap", () => {
    const { container } = render(<BreakdownChart title="Positions" data={data} currencyLabel="CZK" legendColumns={2} />);
    const grids = container.querySelectorAll(".grid.grid-cols-\\[auto_auto_auto\\]");
    expect(grids).toHaveLength(2);
    grids.forEach((grid) => expect(grid).toHaveClass("gap-x-2.5"));
    expect(grids[0]).toHaveTextContent("AAPL");
    expect(grids[0]).toHaveTextContent("BRK.B");
    expect(grids[1]).toHaveTextContent("MSFT");
    expect(screen.getByText("40.00%")).toBeInTheDocument();
  });

  it("formats legend values in the display currency, not in en-US", () => {
    render(<BreakdownChart title="Positions" data={data} currencyLabel="CZK" legendColumns={2} />);
    expect(screen.getByText(/^\(41\s000,00\sKč\)$/)).toBeInTheDocument();
  });

  it("abbreviates the value on a phone so both columns fit", () => {
    window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    render(<BreakdownChart title="Positions" data={data} currencyLabel="CZK" legendColumns={2} />);
    expect(screen.getByText("(41K Kč)")).toBeInTheDocument();
  });

  it("on a phone keeps the aligned ticker / % / (value) grid in two columns that never wrap below each other", () => {
    window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    const { container } = render(<BreakdownChart title="Positions" data={data} currencyLabel="CZK" legendColumns={2} />);
    const grids = container.querySelectorAll(".grid.grid-cols-\\[minmax\\(0\\,auto\\)_auto_auto\\]");
    expect(grids).toHaveLength(2);
    // ticker, %, value of one entry are consecutive cells of the same grid
    expect(grids[0]).toHaveTextContent("AAPL");
    expect(grids[0].textContent).toContain("AAPL40.00%(41K Kč)");
    const wrapper = grids[0].parentElement;
    expect(wrapper).toHaveClass("grid", "grid-cols-2");
    expect(wrapper).not.toHaveClass("flex-wrap");
    expect(wrapper.children).toHaveLength(2);
  });

  describe("exchange suffixes (shortenTickers)", () => {
    const tickers = [
      { name: "VWCE.DE", weight: 40, value: 41000 },
      { name: "BRK.B", weight: 25, value: 25500 },
      { name: "CEZ.PR", weight: 20, value: 20100 },
      { name: "VOD.L", weight: 15, value: 15400 },
    ];
    const asPhone = () => {
      window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    };

    it("drops exchange suffixes on a phone, keeps share classes, keeps the full ticker as a tooltip", () => {
      asPhone();
      render(<BreakdownChart title="Positions" data={tickers} currencyLabel="CZK" legendColumns={2} shortenTickers />);
      expect(screen.getByText("VWCE")).toHaveAttribute("title", "VWCE.DE");
      expect(screen.getByText("CEZ")).toBeInTheDocument();
      expect(screen.getByText("VOD")).toBeInTheDocument();
      expect(screen.getByText("BRK.B")).toBeInTheDocument();
      expect(screen.queryByText("VWCE.DE")).toBeNull();
    });

    it("keeps the full ticker for a ticker listed on several exchanges", () => {
      asPhone();
      const dup = [
        { name: "VWCE.DE", weight: 50, value: 5 },
        { name: "VWCE.MI", weight: 30, value: 3 },
        { name: "CEZ.PR", weight: 20, value: 2 },
      ];
      render(<BreakdownChart title="Positions" data={dup} currencyLabel="CZK" legendColumns={2} shortenTickers />);
      expect(screen.getByText("VWCE.DE")).toBeInTheDocument();
      expect(screen.getByText("VWCE.MI")).toBeInTheDocument();
      expect(screen.getByText("CEZ")).toBeInTheDocument();
    });

    it("never shortens on a wider screen, or without the shortenTickers prop", () => {
      const wide = render(<BreakdownChart title="Positions" data={tickers} currencyLabel="CZK" legendColumns={2} shortenTickers />);
      expect(screen.getByText(/VWCE\.DE/)).toBeInTheDocument();
      wide.unmount();
      asPhone();
      render(<BreakdownChart title="Positions" data={tickers} currencyLabel="CZK" legendColumns={2} />);
      expect(screen.getByText("VWCE.DE")).toBeInTheDocument();
    });
  });

  it("writes every percentage with the same 2 decimals, so 2.5 reads 2.50% (phone, desktop and the single-column list)", () => {
    const mixed = [
      { name: "AAPL", weight: 40, value: 1 },
      { name: "MSFT", weight: 12.3, value: 1 },
      { name: "ASML", weight: 5.25, value: 1 },
      { name: "SAP", weight: 2.5, value: 1 },
    ];
    const pctsOf = (container) => [...container.querySelectorAll("span.tabular-nums")]
      .filter((p) => p.children.length === 0)
      .map((p) => p.textContent)
      .filter((t) => /^\d+(\.\d+)?%$/.test(t));
    const expected = ["40.00%", "12.30%", "5.25%", "2.50%"];

    const desktop = render(<BreakdownChart title="Positions" data={mixed} currencyLabel="CZK" legendColumns={2} />);
    expect(pctsOf(desktop.container)).toEqual(expected);
    desktop.unmount();

    const list = render(<BreakdownChart title="Sectors" data={mixed} currencyLabel="CZK" />);
    expect(pctsOf(list.container)).toEqual(expected);
    list.unmount();

    window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    const phone = render(<BreakdownChart title="Positions" data={mixed} currencyLabel="CZK" legendColumns={2} />);
    expect(pctsOf(phone.container)).toEqual(expected);
  });
});
