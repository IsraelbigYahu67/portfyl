import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import AnalyticsProvider from "../../../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../../../analytics/analyticsClient";
import { demoPortfolio } from "../../../demo/demoPortfolio";
import csMessages from "../../../i18n/messages/cs.js";
import deMessages from "../../../i18n/messages/de.js";
import { COPY } from "../../../pages/welcomeCopy";
import { SHOWCASE_PE_HISTORY } from "../../showcase/showcaseData";
import { fiveYearAveragePe } from "../../showcase/showcaseMath";
import MiniDemoSlot from "../MiniDemoSlot";

// The mini demos are pure sample data: importing the API client is a bug.
vi.mock("../../../api", () => new Proxy({}, {
  get() {
    throw new Error("A mini demo must not import the API client");
  },
}));

const fetchSpy = vi.fn(() => {
  throw new Error("A mini demo must not fetch data");
});

const DICTIONARIES = { cs: csMessages, de: deMessages, en: {} };
const CURRENCY_SYMBOL = { cs: "Kč", de: "€", en: "$" };
const DEFAULT_CURRENCY = { cs: "CZK", de: "EUR", en: "USD" };

let consoleError;

// The chart chunks load on demand; a busy machine needs more than the default 5 s.
vi.setConfig({ testTimeout: 20000 });

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
  vi.stubGlobal("fetch", fetchSpy);
  // A frame near the screen: the observer reports it at once.
  vi.stubGlobal("IntersectionObserver", class {
    constructor(callback) { this.callback = callback; }
    observe() { this.callback([{ isIntersecting: true }], this); }
    unobserve() {}
    disconnect() {}
    takeRecords() { return []; }
  });
  consoleError = vi.spyOn(console, "error");
});

afterEach(() => {
  cleanup();
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(consoleError).not.toHaveBeenCalled();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

function mount(kind, language) {
  const adapter = createMemoryAdapter();
  const copy = COPY[language].miniDemo;
  render(
    <AnalyticsProvider initialConsent="accepted" adapterFactory={() => adapter}>
      <MiniDemoSlot kind={kind} language={language} copy={copy} pictures={[]} demoHref="/demo" />
    </AnalyticsProvider>,
  );
  return { adapter, copy };
}

async function waitForDemo(name) {
  return screen.findByRole("group", { name }, { timeout: 12000 });
}

function pressedLabels(group) {
  return within(group).getAllByRole("button").filter((button) => button.getAttribute("aria-pressed") === "true").map((button) => button.textContent);
}

function rowHeaders(caption) {
  return within(screen.getByRole("table", { name: caption })).getAllByRole("rowheader").map((cell) => cell.textContent);
}

// The label is also a column header of the text table: pick the tile.
function kpi(label) {
  return screen.getAllByText(label).map((node) => node.closest(".pop-tile")).find(Boolean);
}

function expectFrameLabel(copy) {
  expect(screen.getByText(copy.badge)).toBeInTheDocument();
  expect(screen.getByText(copy.disclaimer)).toBeInTheDocument();
}

describe.each(["cs", "en", "de"])("mini demos in %s", (language) => {
  it("(a) allocation: groups by position first, then by currency", async () => {
    const { adapter, copy } = mount("allocation", language);
    const group = await waitForDemo(copy.allocation.groupingAria);
    expectFrameLabel(copy);
    expect(pressedLabels(group)).toEqual([copy.allocation.groupings.holdings]);
    const caption = copy.allocation.tableCaption;
    expect(rowHeaders(caption)).toContain("VWCE");
    expect(screen.getByRole("table", { name: caption })).toHaveTextContent(CURRENCY_SYMBOL[language]);

    await waitFor(() => expect(adapter.events).toEqual([]));
    fireEvent.click(within(group).getByRole("button", { name: copy.allocation.groupings.currencies }));
    expect(pressedLabels(group)).toEqual([copy.allocation.groupings.currencies]);
    expect(rowHeaders(caption).sort()).toEqual(["CZK", "EUR", "USD"]);
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "allocation", language }]]));

    fireEvent.click(within(group).getByRole("button", { name: copy.allocation.groupings.sectors }));
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    expect(adapter.events).toHaveLength(1);
  });

  it("(b) stock: P/E against its five-year average, and a stock picker", async () => {
    const { adapter, copy } = mount("stock", language);
    const group = await waitForDemo(copy.stock.pickAria);
    expectFrameLabel(copy);
    expect(pressedLabels(group)).toEqual(["MSFT"]);
    expect(screen.getByRole("heading", { name: "MSFT" })).toBeInTheDocument();
    const average = fiveYearAveragePe(SHOWCASE_PE_HISTORY.MSFT);
    expect(kpi(copy.stock.pe)).toHaveTextContent("34.2");
    expect(kpi(copy.stock.fivePe)).toHaveTextContent(average.toFixed(1));
    const difference = (34.2 / average - 1) * 100;
    expect(kpi(copy.stock.vsAverage)).toHaveTextContent(`${difference >= 0 ? "+" : "-"}${Math.abs(difference).toFixed(2)}%`);
    expect(screen.getByRole("table", { name: copy.stock.tableCaption })).toBeInTheDocument();
    expect(screen.getByText(copy.stock.disclaimer)).toBeInTheDocument();

    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(["MSFT", "JNJ", "PG"]);
    await waitFor(() => expect(adapter.events).toEqual([]));
    fireEvent.click(within(group).getByRole("button", { name: "PG" }));
    expect(pressedLabels(group)).toEqual(["PG"]);
    expect(screen.getByRole("heading", { name: "PG" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "MSFT" })).not.toBeInTheDocument();
    expect(kpi(copy.stock.fivePe)).toHaveTextContent(fiveYearAveragePe(SHOWCASE_PE_HISTORY.PG).toFixed(1));
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "stock", language }]]));
  });

  it("(c) performance: growth first, both returns visible, value on request", async () => {
    const { adapter, copy } = mount("performance", language);
    const group = await waitForDemo(copy.performance.modeAria);
    expectFrameLabel(copy);
    expect(screen.getByText(copy.performance.title)).toBeInTheDocument();
    expect(pressedLabels(group)).toEqual([copy.performance.modes.growth]);
    expect(kpi(copy.performance.totalReturn)).toHaveTextContent("+44.63%");
    expect(kpi(copy.performance.benchmarkReturn)).toHaveTextContent(`+${demoPortfolio.benchmarks.sp500.at(-1).pct.toFixed(2)}%`);
    const months = new Set(demoPortfolio.performance.map((point) => point.date.slice(0, 7)));
    expect(within(screen.getByRole("table", { name: copy.performance.tableCaption })).getAllByRole("row")).toHaveLength(months.size + 1);

    await waitFor(() => expect(adapter.events).toEqual([]));
    fireEvent.click(within(group).getByRole("button", { name: copy.performance.modes.value }));
    expect(pressedLabels(group)).toEqual([copy.performance.modes.value]);
    expect(kpi(copy.performance.benchmarkReturn)).toBeInTheDocument();
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "performance", language }]]));
  });

  it("(d) dividends: received first, months in the page language, then the upcoming ones", async () => {
    const { adapter, copy } = mount("dividends", language);
    const group = await waitForDemo(copy.dividends.viewAria);
    expectFrameLabel(copy);
    expect(pressedLabels(group)).toEqual([copy.dividends.received]);
    const dictionary = DICTIONARIES[language];
    const month = (name) => dictionary[name] ?? name;
    const caption = copy.dividends.tableCaption;
    expect(rowHeaders(caption)[0]).toBe(month("Jan"));
    expect(rowHeaders(caption)).toHaveLength(9);

    await waitFor(() => expect(adapter.events).toEqual([]));
    fireEvent.click(within(group).getByRole("button", { name: copy.dividends.upcoming }));
    expect(pressedLabels(group)).toEqual([copy.dividends.upcoming]);
    expect(rowHeaders(caption)).toHaveLength(12);
    expect(rowHeaders(caption)[0]).toContain(month("Sep"));
    expect(screen.getByText(copy.dividends.upcomingTotal)).toBeInTheDocument();
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "dividends", language }]]));
  });

  it("(e) portfolios: three portfolios in one currency, the fixed rate stated", async () => {
    const { adapter, copy } = mount("portfolios", language);
    const group = await waitForDemo(copy.portfolios.currencyAria);
    expectFrameLabel(copy);
    expect(pressedLabels(group)).toEqual([DEFAULT_CURRENCY[language]]);
    expect(within(group).getAllByRole("button").map((button) => button.textContent)).toEqual(["CZK", "EUR", "USD"]);
    const { long, dividend, growth } = copy.portfolios.portfolioNames;
    expect(rowHeaders(copy.portfolios.tableCaption)).toEqual([long, dividend, growth]);
    expect(screen.getByText(copy.portfolios.ratesNote)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: copy.portfolios.tableCaption })).toHaveTextContent(CURRENCY_SYMBOL[language]);

    await waitFor(() => expect(adapter.events).toEqual([]));
    const other = DEFAULT_CURRENCY[language] === "USD" ? "EUR" : "USD";
    fireEvent.click(within(group).getByRole("button", { name: other }));
    expect(pressedLabels(group)).toEqual([other]);
    expect(screen.getByRole("table", { name: copy.portfolios.tableCaption })).toHaveTextContent(other === "USD" ? "$" : "€");
    await waitFor(() => expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "portfolios", language }]]));
  });
});
