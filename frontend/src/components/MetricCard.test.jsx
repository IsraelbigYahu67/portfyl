import { render, screen } from "@testing-library/react";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders a pre-formatted string value unchanged (existing call sites)", () => {
    render(<MetricCard label="Balance" value="$1,234.50" />);
    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
  });

  it("animates a numeric value under reduced motion and renders it grouped", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<MetricCard label="Holdings" value={12345} />);
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  it("still shows a loading skeleton and hides the value", () => {
    const { container } = render(<MetricCard label="Beta" value="1.2" loading />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    expect(screen.queryByText("1.2")).not.toBeInTheDocument();
  });
});
