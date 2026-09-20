import { fireEvent, render, screen } from "@testing-library/react";
import MetricCard, { InfoIcon } from "./MetricCard";

describe("InfoIcon", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders its hovered tooltip in a fixed top-level layer outside clipping ancestors", () => {
    render(
      <div data-testid="clipping-parent" style={{ overflow: "hidden" }}>
        <InfoIcon info={{ title: "Sharpe Ratio", what: "Risk-adjusted return." }} />
      </div>
    );

    fireEvent.mouseEnter(screen.getByRole("button", { name: "What is Sharpe Ratio?" }));

    const tooltip = screen.getByRole("tooltip");
    expect(screen.getByTestId("clipping-parent")).not.toContainElement(tooltip);
    expect(tooltip.parentElement).toBe(document.body);
    expect(tooltip).toHaveStyle({ position: "fixed", zIndex: "2147483647" });
  });

  it("keeps the tooltip inside the viewport near the bottom-right corner", () => {
    vi.spyOn(window, "innerWidth", "get").mockReturnValue(320);
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(240);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function () {
      if (this.getAttribute("role") === "tooltip") {
        return { left: 0, top: 0, right: 288, bottom: 100, width: 288, height: 100, x: 0, y: 0, toJSON() {} };
      }
      if (this.getAttribute("aria-label") === "What is Beta?") {
        return { left: 300, top: 220, right: 312, bottom: 232, width: 12, height: 12, x: 300, y: 220, toJSON() {} };
      }
      return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON() {} };
    });

    render(<InfoIcon info={{ title: "Beta", what: "Market sensitivity." }} />);
    const trigger = screen.getByRole("button", { name: "What is Beta?" });

    fireEvent.mouseEnter(trigger);

    expect(screen.getByRole("tooltip")).toHaveStyle({ left: "20px", top: "112px" });
  });

  it("keeps tooltip body, formula, and note text at least 12px", () => {
    render(
      <InfoIcon
        info={{ title: "Beta", what: "Market sensitivity.", formula: "beta = cov / var", note: "Trailing 3y" }}
      />
    );
    fireEvent.mouseEnter(screen.getByRole("button", { name: "What is Beta?" }));

    expect(screen.getByRole("tooltip")).not.toHaveClass("text-[11px]");
    expect(screen.getByText("beta = cov / var")).not.toHaveClass("text-[10px]");
    expect(screen.getByText("Trailing 3y")).not.toHaveClass("text-[10px]");
  });
});

describe("MetricCard", () => {
  it("renders a pre-formatted string value unchanged (existing call sites)", () => {
    render(<MetricCard label="Balance" value="$1,234.50" />);
    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
  });

  it("value uses the financial-headline semantic class", () => {
    render(<MetricCard label="Balance" value="$1,234.50" />);
    expect(screen.getByText("$1,234.50")).toHaveClass("financial-headline");
  });

  it("animates a numeric value under reduced motion and renders it grouped", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<MetricCard label="Holdings" value={12345} countUp />);
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  it("still shows a loading skeleton and hides the value", () => {
    const { container } = render(<MetricCard label="Beta" value="1.2" loading />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    expect(screen.queryByText("1.2")).not.toBeInTheDocument();
  });

  it("renders a raw number as-is (not integer-rounded) when countUp is not requested", () => {
    render(<MetricCard label="Info Ratio" value={0.874} />);
    expect(screen.getByText("0.874")).toBeInTheDocument();
  });
});
