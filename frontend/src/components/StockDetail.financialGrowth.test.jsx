import { render, screen } from "@testing-library/react";
import {
  financialPeriodAxisLayout,
  MergedMetricBarChart,
  MetricBarChart,
} from "./StockDetail";

// Recharts needs element dimensions that jsdom does not provide. This thin
// adapter keeps the chart configuration real and exposes the custom x-axis
// tick's growth values, which are the values rendered below each period label.
vi.mock("recharts", () => ({
  Area: () => null,
  AreaChart: ({ children }) => children,
  Bar: ({ children }) => children,
  BarChart: ({ children }) => children,
  CartesianGrid: () => null,
  // Expose each bar's fill so the tests can check it uses theme series colors.
  Cell: ({ fill }) => <i data-testid="bar-fill" data-fill={fill} />,
  ComposedChart: ({ children }) => children,
  Customized: () => null,
  Legend: () => null,
  Line: () => null,
  Pie: () => null,
  PieChart: ({ children }) => children,
  ReferenceArea: () => null,
  ReferenceDot: () => null,
  ResponsiveContainer: ({ children }) => children,
  Tooltip: () => null,
  XAxis: ({ tick, interval }) => {
    const changes = tick?.props?.changes || [];
    // Model Recharts' label thinning when the chart asks it to preserve only
    // the ends. With interval={0}, every custom tick (and therefore every
    // QoQ value) remains visible.
    const displayedChanges = interval === "preserveStartEnd"
      ? changes.filter((_, index) => index === 0 || index === changes.length - 1 || index % 3 === 0)
      : changes;
    return (
    <output data-testid="period-growth">
      {displayedChanges.map((change) =>
        change == null ? "—" : `${change.toFixed(1)}%`,
      ).join(" ")}
    </output>
    );
  },
  YAxis: () => null,
}));

const quarterlyActuals = [
  { label: "Q1 '24", value: 100, isEstimate: false },
  { label: "Q2 '24", value: 110, isEstimate: false },
  { label: "Q3 '24", value: 121, isEstimate: false },
  { label: "Q4 '24", value: 133.1, isEstimate: false },
  { label: "Q1 '25", value: 146.41, isEstimate: false },
  { label: "Q2 '25", value: 161.051, isEstimate: false },
  { label: "Q3 '25", value: 177.1561, isEstimate: false },
];

const longQuarterlyActuals = [
  ...quarterlyActuals,
  { label: "Q4 '25", value: 194.87171, isEstimate: false },
  { label: "Q1 '26", value: 214.358881, isEstimate: false },
];

describe("financial period axis layout", () => {
  it("never goes below 12px", () => {
    const layout = financialPeriodAxisLayout(
      Array.from({ length: 10 }, (_, index) => String(2017 + index)),
      300,
      false,
    );

    expect(layout.fontSize).toBe(12);
    expect(layout.angle).toBe(0);
    expect(layout.short).toBe(true);
  });

  it("thins labels when even short labels collide", () => {
    const layout = financialPeriodAxisLayout(
      Array.from({ length: 40 }, (_, index) => `Q${index % 4 + 1} '${14 + Math.floor(index / 4)}`),
      300,
      true,
    );

    expect(layout.fontSize).toBe(12);
    expect(layout.interval).toBeGreaterThanOrEqual(1);
  });

  it("keeps every label when they fit", () => {
    const layout = financialPeriodAxisLayout(
      Array.from({ length: 10 }, (_, index) => String(2017 + index)),
      1200,
      false,
    );

    expect(layout.interval).toBe(0);
    expect(layout.short).toBe(false);
  });
});

describe("financial bar fills", () => {
  it("bars use theme series, not hex fills", () => {
    render(
      <MetricBarChart
        metric={{
          name: "Net Income",
          years: ["2022", "2023", "2024"],
          values: [100, -20, 140],
          yoy: [null, -120, 800],
          cagr: 18.3,
        }}
        currencyCode="USD"
        period="annual"
        ttm={150}
      />,
    );

    const fills = screen.getAllByTestId("bar-fill").map((el) => el.getAttribute("data-fill"));
    expect(fills.length).toBeGreaterThan(0);
    fills.forEach((fill) => expect(fill.startsWith("#")).toBe(false));
  });
});

describe("MergedMetricBarChart quarterly growth labels", () => {
  it.each([
    ["Revenue", false],
    ["Diluted EPS", true],
  ])("renders QoQ beneath every quarterly period for %s", (name, isPerShare) => {
    render(
      <MergedMetricBarChart
        name={name}
        data={quarterlyActuals}
        currencyCode="USD"
        isPerShare={isPerShare}
      />,
    );

    // A prior implementation removed the custom tick entirely once quarterly
    // history exceeded six bars, so no QoQ values were visible below the years.
    expect(screen.getByTestId("period-growth")).toHaveTextContent(
      "— 10.0% 10.0% 10.0% 10.0% 10.0% 10.0%",
    );
    expect(screen.getByText("QoQ")).toBeInTheDocument();
  });

  it("renders QoQ beneath quarterly periods for a standard metric card", () => {
    render(
      <MetricBarChart
        metric={{
          name: "Net Income",
          years: quarterlyActuals.map((row) => row.label),
          values: quarterlyActuals.map((row) => row.value),
          yoy: [null, null, null, null, 46.41, 46.41, 46.41],
          cagr: 46.41,
        }}
        currencyCode="USD"
        period="quarterly"
      />,
    );

    expect(screen.getByTestId("period-growth")).toHaveTextContent(
      "— 10.0% 10.0% 10.0% 10.0% 10.0% 10.0%",
    );
    expect(screen.getByText("QoQ")).toBeInTheDocument();
  });

  it.each([
    ["Revenue", false],
    ["Diluted EPS", true],
  ])("does not omit QoQ values when %s has more than eight quarters", (name, isPerShare) => {
    render(
      <MergedMetricBarChart
        name={name}
        data={longQuarterlyActuals}
        currencyCode="USD"
        isPerShare={isPerShare}
      />,
    );

    expect(screen.getByTestId("period-growth")).toHaveTextContent(
      "— 10.0% 10.0% 10.0% 10.0% 10.0% 10.0% 10.0% 10.0%",
    );
  });
});
