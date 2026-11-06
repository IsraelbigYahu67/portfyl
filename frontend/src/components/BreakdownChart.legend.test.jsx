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
    grids.forEach((grid) => expect(grid).toHaveClass("gap-x-2", "sm:gap-x-2.5"));
    expect(grids[0]).toHaveTextContent("AAPL");
    expect(grids[0]).toHaveTextContent("BRK.B");
    expect(grids[1]).toHaveTextContent("MSFT");
    expect(screen.getByText("40%")).toBeInTheDocument();
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
});
