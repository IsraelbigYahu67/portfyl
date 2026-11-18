import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { demoPortfolio } from "../../demo/demoPortfolio";
import AllocationPanel from "./AllocationPanel";
import DividendsPanel from "./DividendsPanel";
import PerformancePanel from "./PerformancePanel";
import PortfoliosPanel from "./PortfoliosPanel";
import StockValuationPanel from "./StockValuationPanel";
import { SHOWCASE_AS_OF, SHOWCASE_PE_HISTORY, SHOWCASE_PORTFOLIOS, portfolioTotals, showcaseHoldings } from "./showcaseData";
import { fiveYearAveragePe } from "./showcaseMath";

// A panel is pure props: importing the API client is a bug.
vi.mock("../../api", () => new Proxy({}, {
  get() {
    throw new Error("A showcase panel must not import the API client");
  },
}));

const chart = vi.hoisted(() => ({ props: null }));
vi.mock("../PerformanceChart", () => ({
  default: (props) => {
    chart.props = props;
    return <div data-testid="performance-chart" />;
  },
}));

const fetchSpy = vi.fn(() => {
  throw new Error("A showcase panel must not fetch data");
});

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // ResponsiveContainer reads its box size; jsdom has none.
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 800 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 300 });
});

beforeEach(() => {
  chart.props = null;
  vi.stubGlobal("fetch", fetchSpy);
});

afterEach(() => {
  cleanup();
  expect(fetchSpy).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
});

function tableRows(caption) {
  return within(screen.getByRole("table", { name: caption })).getAllByRole("row").slice(1);
}

function rowHeaders(caption) {
  return within(screen.getByRole("table", { name: caption })).getAllByRole("rowheader").map((cell) => cell.textContent);
}

function expectSwitch(ariaLabel, expectedValueLabel) {
  const group = screen.getByRole("group", { name: ariaLabel });
  const buttons = within(group).getAllByRole("button");
  for (const button of buttons) expect(button).toHaveAttribute("type", "button");
  const pressed = buttons.filter((button) => button.getAttribute("aria-pressed") === "true");
  expect(pressed).toHaveLength(1);
  expect(pressed[0]).toHaveTextContent(expectedValueLabel);
  return buttons;
}

describe("AllocationPanel", () => {
  const labels = {
    title: "Allocation title",
    groupingAria: "Allocation grouping",
    tableCaption: "Allocation text table",
    columns: { name: "Name", value: "Value", weight: "Weight" },
  };
  const groupings = [
    { value: "holdings", label: "By position" },
    { value: "sectors", label: "By sector" },
    { value: "currencies", label: "By currency" },
  ];
  const holdings = showcaseHoldings("CZK");

  function Harness({ initial = "holdings", onChange }) {
    const [grouping, setGrouping] = useState(initial);
    return (
      <AllocationPanel
        holdings={holdings}
        currency="CZK"
        grouping={grouping}
        groupings={groupings}
        onGroupingChange={(value) => { onChange?.(value); setGrouping(value); }}
        labels={labels}
      />
    );
  }

  it("draws the title and a text table with one row per position", () => {
    render(<Harness />);
    expect(screen.getByText(labels.title)).toBeInTheDocument();
    expect(tableRows(labels.tableCaption)).toHaveLength(holdings.length);
    expect(rowHeaders(labels.tableCaption)).toContain("VWCE");
  });

  it("has an accessible switch and reports the clicked grouping", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    const buttons = expectSwitch(labels.groupingAria, "By position");
    fireEvent.click(buttons[2]);
    expect(onChange).toHaveBeenCalledWith("currencies");
    expectSwitch(labels.groupingAria, "By currency");
  });

  it("regroups the table by currency into CZK, EUR and USD", () => {
    render(<Harness initial="currencies" />);
    expect(rowHeaders(labels.tableCaption).sort()).toEqual(["CZK", "EUR", "USD"]);
  });
});

describe("StockValuationPanel", () => {
  const labels = {
    pe: "P/E now",
    fivePe: "Five-year average P/E",
    forwardPe: "Forward P/E now",
    vsAverage: "Against the average",
    historyTitle: "P/E history",
    tableCaption: "P/E history text table",
    disclaimer: "Made-up numbers.",
  };
  const msft = demoPortfolio.holdings.find((holding) => holding.symbol === "MSFT");

  // The P/E label is also a column header of the text table: pick the tile.
  function kpi(label) {
    return screen.getAllByText(label).map((node) => node.closest(".pop-tile")).find(Boolean);
  }

  it("shows the P/E, its five-year average and the difference in percent", () => {
    render(<StockValuationPanel holding={msft} peHistory={SHOWCASE_PE_HISTORY.MSFT} currency="USD" labels={labels} />);
    const average = fiveYearAveragePe(SHOWCASE_PE_HISTORY.MSFT);
    expect(kpi(labels.pe)).toHaveTextContent("34.2");
    expect(kpi(labels.fivePe)).toHaveTextContent(average.toFixed(1));
    expect(kpi(labels.forwardPe)).toHaveTextContent("30.1");
    const difference = (34.2 / average - 1) * 100;
    expect(kpi(labels.vsAverage)).toHaveTextContent(`${difference >= 0 ? "+" : "-"}${Math.abs(difference).toFixed(2)}%`);
    expect(screen.getByRole("heading", { name: "MSFT" })).toBeInTheDocument();
    expect(screen.getByText(labels.disclaimer)).toBeInTheDocument();
  });

  it("has a text table with one row per history point", () => {
    render(<StockValuationPanel holding={msft} peHistory={SHOWCASE_PE_HISTORY.MSFT} currency="USD" labels={labels} />);
    expect(tableRows(labels.tableCaption)).toHaveLength(20);
  });

  it("shows a dash instead of the average for a symbol without history", () => {
    const vuaa = demoPortfolio.holdings.find((holding) => holding.symbol === "VUAA");
    render(<StockValuationPanel holding={vuaa} peHistory={[]} currency="USD" labels={labels} />);
    expect(kpi(labels.fivePe)).toHaveTextContent("—");
    expect(kpi(labels.vsAverage)).toHaveTextContent("—");
    expect(screen.queryByRole("table", { name: labels.tableCaption })).not.toBeInTheDocument();
  });
});

describe("PerformancePanel", () => {
  const labels = {
    title: "Performance title",
    modeAria: "Chart mode",
    totalReturn: "Portfolio return",
    benchmarkReturn: "Index return",
    tableCaption: "Performance text table",
    columns: { date: "Month", value: "Value", benchmark: "Index" },
  };
  const modes = [{ value: "value", label: "Value mode" }, { value: "growth", label: "Growth mode" }];
  const props = {
    performance: demoPortfolio.performance,
    benchmarks: demoPortfolio.benchmarks,
    benchmarkMeta: demoPortfolio.benchmarkMeta,
    currency: "USD",
    modes,
    labels,
  };

  it("draws the title, both return tiles and a monthly text table", () => {
    render(<PerformancePanel {...props} mode="value" onModeChange={() => {}} />);
    expect(screen.getByText(labels.title)).toBeInTheDocument();
    expect(screen.getByText(labels.totalReturn).closest(".card")).toHaveTextContent("+44.63%");
    expect(screen.getByText(labels.benchmarkReturn).closest(".card")).toHaveTextContent(
      `+${demoPortfolio.benchmarks.sp500.at(-1).pct.toFixed(2)}%`,
    );
    const months = new Set(demoPortfolio.performance.map((point) => point.date.slice(0, 7)));
    expect(tableRows(labels.tableCaption)).toHaveLength(months.size);
  });

  it("hides the return tiles on request", () => {
    render(<PerformancePanel {...props} mode="value" onModeChange={() => {}} showKpis={false} />);
    expect(screen.queryByText(labels.totalReturn)).not.toBeInTheDocument();
  });

  it("switches mode through an accessible control", () => {
    const onModeChange = vi.fn();
    render(<PerformancePanel {...props} mode="value" onModeChange={onModeChange} />);
    const buttons = expectSwitch(labels.modeAria, "Value mode");
    fireEvent.click(buttons[1]);
    expect(onModeChange).toHaveBeenCalledWith("growth");
  });

  it("hands the chart the raw series in value mode and percent growth in growth mode", () => {
    const { rerender } = render(<PerformancePanel {...props} mode="value" onModeChange={() => {}} />);
    expect(chart.props.mode).toBe("value");
    expect(chart.props.data).toBe(demoPortfolio.performance);
    rerender(<PerformancePanel {...props} mode="growth" onModeChange={() => {}} />);
    expect(chart.props.mode).toBe("growth");
    expect(chart.props.data).toHaveLength(demoPortfolio.performance.length);
    expect(chart.props.data[0].pnl_pct).toBe(0);
    expect(chart.props.data.at(-1).pnl_pct).toBeCloseTo(44.6304, 3);
    expect(chart.props.benchmarkMeta).toBe(demoPortfolio.benchmarkMeta);
  });
});

describe("DividendsPanel", () => {
  const labels = {
    received: "Dividends received",
    upcoming: "Upcoming payments",
    receivedTotal: "So far this year",
    upcomingTotal: "Next 12 months",
    viewAria: "Dividend view",
    tableCaption: "Dividends text table",
    columns: { month: "Month", amount: "Amount" },
  };
  const views = [{ value: "received", label: "Received tab" }, { value: "upcoming", label: "Upcoming tab" }];
  const props = { dividends: demoPortfolio.dividends, asOf: demoPortfolio.asOf, currency: "USD", views, labels };

  it("shows what was received up to the as-of month", () => {
    render(<DividendsPanel {...props} view="received" onViewChange={() => {}} />);
    expect(screen.getByText(labels.received)).toBeInTheDocument();
    expect(screen.getByText(labels.receivedTotal)).toBeInTheDocument();
    expect(tableRows(labels.tableCaption)).toHaveLength(9);
    expect(demoPortfolio.asOf).toBe(SHOWCASE_AS_OF);
  });

  it("shows the next twelve months in the upcoming view", () => {
    render(<DividendsPanel {...props} view="upcoming" onViewChange={() => {}} />);
    expect(screen.getByText(labels.upcoming)).toBeInTheDocument();
    expect(screen.getByText(labels.upcomingTotal)).toBeInTheDocument();
    expect(tableRows(labels.tableCaption)).toHaveLength(12);
  });

  it("switches view through an accessible control", () => {
    const onViewChange = vi.fn();
    render(<DividendsPanel {...props} view="received" onViewChange={onViewChange} />);
    const buttons = expectSwitch(labels.viewAria, "Received tab");
    fireEvent.click(buttons[1]);
    expect(onViewChange).toHaveBeenCalledWith("upcoming");
  });
});

describe("PortfoliosPanel", () => {
  const labels = {
    currencyAria: "Show in currency",
    portfolioNames: { long: "Long-term", dividend: "Dividends", growth: "Growth" },
    ratesNote: "Fixed sample rate.",
    tableCaption: "Portfolios text table",
    columns: { name: "Portfolio", value: "Value", weight: "Weight" },
  };
  const currencies = [{ value: "CZK", label: "CZK" }, { value: "EUR", label: "EUR" }, { value: "USD", label: "USD" }];

  it("lists the three portfolios by name with the rates note", () => {
    render(
      <PortfoliosPanel
        portfolios={portfolioTotals("CZK")}
        displayCurrency="CZK"
        onCurrencyChange={() => {}}
        currencies={currencies}
        labels={labels}
      />,
    );
    expect(rowHeaders(labels.tableCaption)).toEqual(["Long-term", "Dividends", "Growth"]);
    expect(screen.getByText(labels.ratesNote)).toBeInTheDocument();
    expect(screen.getByText("Net Worth")).toBeInTheDocument();
  });

  it("shows amounts in the chosen currency", () => {
    const base = { onCurrencyChange: () => {}, currencies, labels };
    const { rerender } = render(<PortfoliosPanel {...base} portfolios={portfolioTotals("CZK")} displayCurrency="CZK" />);
    expect(screen.getByRole("table", { name: labels.tableCaption })).toHaveTextContent("Kč");
    rerender(<PortfoliosPanel {...base} portfolios={portfolioTotals("EUR")} displayCurrency="EUR" />);
    const table = screen.getByRole("table", { name: labels.tableCaption });
    expect(table).toHaveTextContent("€");
    expect(table).not.toHaveTextContent("Kč");
  });

  it("converts raw sample portfolios itself", () => {
    render(
      <PortfoliosPanel
        portfolios={SHOWCASE_PORTFOLIOS}
        displayCurrency="USD"
        onCurrencyChange={() => {}}
        currencies={currencies}
        labels={labels}
      />,
    );
    expect(tableRows(labels.tableCaption)).toHaveLength(3);
    expect(screen.getByRole("table", { name: labels.tableCaption })).toHaveTextContent("$");
  });

  it("switches currency through an accessible control", () => {
    const onCurrencyChange = vi.fn();
    render(
      <PortfoliosPanel
        portfolios={portfolioTotals("CZK")}
        displayCurrency="CZK"
        onCurrencyChange={onCurrencyChange}
        currencies={currencies}
        labels={labels}
      />,
    );
    const buttons = expectSwitch(labels.currencyAria, "CZK");
    fireEvent.click(buttons[1]);
    expect(onCurrencyChange).toHaveBeenCalledWith("EUR");
  });
});
