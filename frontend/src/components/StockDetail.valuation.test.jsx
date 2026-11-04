import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StockOverview, layoutEdgePills } from "./StockDetail";

vi.mock("../api", () => ({}));

const BOUNDS = { top: 0, bottom: 300, minGap: 22 };

function renderOverview(data, sectionIds) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StockOverview data={data} sectionIds={sectionIds} showHeader={false} showCustomizer={false} />
    </QueryClientProvider>,
  );
}

describe("layoutEdgePills", () => {
  it("separates overlapping pills", () => {
    const out = layoutEdgePills(
      [{ key: "a", y: 100 }, { key: "b", y: 104 }, { key: "c", y: 108 }],
      BOUNDS,
    );
    expect(out.map((p) => p.key)).toEqual(["a", "b", "c"]);
    expect(out[1].y - out[0].y).toBeGreaterThanOrEqual(22);
    expect(out[2].y - out[1].y).toBeGreaterThanOrEqual(22);
  });

  it("keeps pills inside the plot", () => {
    const out = layoutEdgePills([{ key: "x", y: 295 }], BOUNDS);
    expect(out[0].y).toBeLessThanOrEqual(289);
    const top = layoutEdgePills([{ key: "x", y: -5 }], BOUNDS);
    expect(top[0].y).toBeGreaterThanOrEqual(11);
  });

  it("pushes a stack at the bottom edge upward instead of off the plot", () => {
    const out = layoutEdgePills(
      [{ key: "a", y: 280 }, { key: "b", y: 290 }, { key: "c", y: 298 }],
      BOUNDS,
    );
    expect(out.map((p) => p.key)).toEqual(["a", "b", "c"]);
    expect(out[2].y).toBeLessThanOrEqual(289);
    expect(out[1].y - out[0].y).toBeGreaterThanOrEqual(22);
    expect(out[2].y - out[1].y).toBeGreaterThanOrEqual(22);
  });
});

describe("analyst rating", () => {
  const analyst = {
    rating: "STRONG_BUY", score: 1.2, total: 10,
    strong_buy: 6, buy: 2, hold: 1, sell: 1, strong_sell: 0,
  };

  it("label is humanized", () => {
    renderOverview({ ticker: "AAPL", currency: "USD", analyst }, ["ratiosAnalyst"]);
    expect(screen.getByText("Strong buy")).toBeInTheDocument();
    expect(screen.queryByText("STRONG_BUY")).toBeNull();
  });

  it("bars use token colors, never palette classes", () => {
    const { container } = renderOverview({ ticker: "AAPL", currency: "USD", analyst }, ["ratiosAnalyst"]);
    const fills = [...container.querySelectorAll("div.rounded-full[style*='width']")];
    expect(fills.map((el) => el.getAttribute("style").match(/background-color:\s*([^;]+)/)[1].trim())).toEqual([
      "var(--gain, #34D399)",
      "var(--gain, #34D399)",
      "var(--chart-3)",
      "var(--loss, #F87171)",
      "var(--loss, #F87171)",
    ]);
    expect(container.innerHTML).not.toMatch(/\b(?:bg|text)-(?:emerald|green|yellow|orange|red|slate)-\d/);
  });
});

describe("price target pills", () => {
  it("never overlap when targets are close together", () => {
    const analyst = { rating: "BUY", score: 2, total: 5, target_low: 99, target_mean: 101, target_high: 102, upside: 1 };
    const { container } = renderOverview(
      { ticker: "AAPL", currency: "USD", price: 100, analyst },
      ["ratiosAnalyst"],
    );
    const tops = [...container.querySelectorAll("div.absolute.right-1")]
      .map((el) => parseFloat(el.style.top))
      .sort((a, b) => a - b);
    expect(tops).toHaveLength(4);
    for (let i = 1; i < tops.length; i++) expect(tops[i] - tops[i - 1]).toBeGreaterThanOrEqual(22);
  });
});
