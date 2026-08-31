import { render, screen } from "@testing-library/react";
import { KpiBox } from "./index";

describe("KpiBox", () => {
  it("renders a label and a pre-formatted string value without animating", () => {
    render(<KpiBox label="P/E (TTM)" value="24.1" />);
    expect(screen.getByText("P/E (TTM)")).toBeInTheDocument();
    expect(screen.getByText("24.1")).toBeInTheDocument();
  });

  it("renders a numeric value through the count-up path under reduced motion", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<KpiBox label="Market Cap" value={1234} format={(v) => `$${Math.round(v)}`} countUp />);
    expect(screen.getByText("$1234")).toBeInTheDocument();
  });

  it("shows a loading skeleton and hides the value", () => {
    const { container } = render(<KpiBox label="Beta" value={1.2} loading />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    expect(screen.queryByText("1.2")).not.toBeInTheDocument();
  });

  it("colors the sub line by subTone", () => {
    render(<KpiBox label="ROE" value="18.2%" sub="Sector 12.4 · Δ +5.8" subTone="gain" />);
    expect(screen.getByText("Sector 12.4 · Δ +5.8")).toHaveClass("text-gain");
  });

  it("renders nothing for value when null (dash callers pass their own dash string)", () => {
    render(<KpiBox label="Beta" value={null} />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });
});
