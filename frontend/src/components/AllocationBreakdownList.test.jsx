import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AllocationBreakdownList from "./AllocationBreakdownList";

const rows = [
  { name: "Technology", value: 5000, weight: 50 },
  { name: "Healthcare", value: 3000, weight: 30 },
  { name: "Energy", value: 2000, weight: 20 },
];

describe("AllocationBreakdownList", () => {
  it("lists every row sorted by weight descending with label, value, and percentage", () => {
    render(<AllocationBreakdownList rows={rows} currency="USD" />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringContaining("Technology"),
      expect.stringContaining("Healthcare"),
      expect.stringContaining("Energy"),
    ]);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText(/\$5,000\.00/)).toBeInTheDocument();
  });

  it("value and weight cells use the financial-data semantic class", () => {
    render(<AllocationBreakdownList rows={rows} currency="USD" />);
    expect(screen.getByText(/\$5,000\.00/)).toHaveClass("financial-data");
    expect(screen.getByText("50%")).toHaveClass("financial-data");
  });

  it("renders nothing for an empty row set", () => {
    const { container } = render(<AllocationBreakdownList rows={[]} currency="USD" />);
    expect(container).toBeEmptyDOMElement();
  });
});
