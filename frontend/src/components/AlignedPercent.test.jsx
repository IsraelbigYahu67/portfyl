import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AlignedPercent, { decimalsOf, maxDecimalsOf } from "./AlignedPercent";

describe("decimalsOf / maxDecimalsOf", () => {
  it("counts decimals of plain numbers", () => {
    expect(decimalsOf(40)).toBe(0);
    expect(decimalsOf(12.3)).toBe(1);
    expect(decimalsOf("5.25")).toBe(2);
    expect(maxDecimalsOf([40, 12.3, 5.25])).toBe(2);
    expect(maxDecimalsOf([])).toBe(0);
  });
});

describe("AlignedPercent", () => {
  it("pads with real zeros so 2.5 reads 2.50%, with nothing before the % sign", () => {
    const { container } = render(<AlignedPercent value={2.5} decimals={2} />);
    expect(screen.getByText("2.50%")).toBeInTheDocument();
    expect(container.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("gives every value in a group the same number of decimals", () => {
    render(
      <>
        <AlignedPercent value={40} decimals={2} />
        <AlignedPercent value={12.3} decimals={2} />
        <AlignedPercent value={5.25} decimals={2} />
      </>
    );
    expect(screen.getByText("40.00%")).toBeInTheDocument();
    expect(screen.getByText("12.30%")).toBeInTheDocument();
    expect(screen.getByText("5.25%")).toBeInTheDocument();
  });

  it("never rounds away decimals the value already has", () => {
    render(<AlignedPercent value={5.125} decimals={1} />);
    expect(screen.getByText("5.125%")).toBeInTheDocument();
  });
});
