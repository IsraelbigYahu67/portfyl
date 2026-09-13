import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AllocationBarList from "./AllocationBarList";

const holdings = [
  { ticker: "AAPL", name: "Apple Inc.", market_value: 5000, weight: 50, closed: false },
  { ticker: "MSFT", name: "Microsoft Corp.", market_value: 3000, weight: 30, closed: false },
  { ticker: "TSLA", name: "Tesla Inc.", market_value: 2000, weight: 20, closed: false },
  { ticker: "OLD", name: "Sold Co.", market_value: 0, weight: 0, closed: true },
];

describe("AllocationBarList", () => {
  it("lists every open position sorted by weight descending", () => {
    render(<AllocationBarList holdings={holdings} currency="USD" />);
    const rows = screen.getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining("AAPL"),
      expect.stringContaining("MSFT"),
      expect.stringContaining("TSLA"),
    ]);
  });

  it("shows label, value, and percentage for each row", () => {
    render(<AllocationBarList holdings={holdings} currency="USD" />);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText(/\$5,000\.00/)).toBeInTheDocument();
  });

  it("excludes closed positions", () => {
    render(<AllocationBarList holdings={holdings} currency="USD" />);
    expect(screen.queryByText(/OLD/)).not.toBeInTheDocument();
  });

  it("renders nothing when there are no open positions", () => {
    const { container } = render(<AllocationBarList holdings={[holdings[3]]} currency="USD" />);
    expect(container).toBeEmptyDOMElement();
  });
});
