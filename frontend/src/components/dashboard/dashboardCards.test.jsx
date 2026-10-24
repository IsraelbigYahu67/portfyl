import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import InsightCards from "./InsightCards";
import CompositionCard from "./CompositionCard";
import DividendBarsCard from "./DividendBarsCard";

const alerts = [
  { id: "a1", severity: "critical", title: "No current price: MC", detail: "MC is valued at 0.", to: "/allocation" },
  { id: "a2", severity: "warning", title: "Concentration: NVDA", detail: "NVDA is 12% of the portfolio.", to: "/allocation" },
  { id: "a3", severity: "info", title: "Dividend soon: MSFT", detail: "MSFT goes ex-dividend on 2026-11-19.", to: "/dividends" },
  { id: "a4", severity: "info", title: "Earnings soon: ASML", detail: "ASML reports earnings on 2026-10-15.", to: "/search?q=ASML" },
];

function renderWithRouter(ui) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("InsightCards", () => {
  it("shows the three most important signals as cards with their severity in words", () => {
    renderWithRouter(<InsightCards alerts={alerts} />);

    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByText("Critical")).toBeInTheDocument();
    expect(within(cards[0]).getByRole("link", { name: /review/i })).toHaveAttribute("href", "/allocation");
    expect(screen.queryByText("Earnings soon: ASML")).not.toBeInTheDocument();
  });

  it("reveals the remaining signals on request", () => {
    renderWithRouter(<InsightCards alerts={alerts} />);

    fireEvent.click(screen.getByRole("button", { name: "Show all 4 signals" }));

    expect(screen.getByText("Earnings soon: ASML")).toBeInTheDocument();
  });

  it("lets the user dismiss a card for this visit", () => {
    renderWithRouter(<InsightCards alerts={alerts} />);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss No current price: MC" }));

    expect(screen.queryByText("No current price: MC")).not.toBeInTheDocument();
    expect(screen.getByText("Earnings soon: ASML")).toBeInTheDocument();
  });

  it("says so when nothing needs attention", () => {
    renderWithRouter(<InsightCards alerts={[]} />);
    expect(screen.getByText("Nothing needs attention right now.")).toBeInTheDocument();
  });
});

describe("CompositionCard", () => {
  const breakdown = {
    currency: "CZK",
    total_value: 2000,
    asset_types: [
      { name: "Stocks", value: 1200, weight: 60, profit: 350 },
      { name: "ETFs", value: 800, weight: 40, profit: -120 },
      { name: "Cash", value: 0, weight: 0, profit: null },
    ],
    sectors: [{ name: "Technology", value: 2000, weight: 100 }],
    countries: [{ name: "United States", value: 2000, weight: 100 }],
  };

  it("lists weight, then value, then combined profit, and no target column", () => {
    renderWithRouter(<CompositionCard breakdown={breakdown} currency="CZK" />);
    fireEvent.click(screen.getByRole("button", { name: "Categories" }));

    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Name", "Weight", "Value", "Profit"]);
    const stocks = screen.getByRole("row", { name: /Stocks/ });
    expect(within(stocks).getByText("60.0%")).toBeInTheDocument();
    expect(within(stocks).getByText(/^\+/)).toHaveClass("text-gain");
    expect(within(screen.getByRole("row", { name: /ETFs/ })).getByText(/120/)).toHaveClass("text-loss");
    expect(within(screen.getByRole("row", { name: /Cash/ })).getByText("—")).toBeInTheDocument();
  });

  it("totals the donut from its own rows, because the API's total_value leaves cash out", () => {
    renderWithRouter(
      <CompositionCard
        breakdown={{ ...breakdown, total_value: 1200, asset_types: [{ name: "Stocks", value: 1200, weight: 60 }, { name: "Cash", value: 800, weight: 40 }] }}
        currency="USD"
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Categories" }));
    expect(screen.getByText("$2K")).toBeInTheDocument();
  });

  it("opens on sectors, then countries, then categories, in that tab order", () => {
    renderWithRouter(<CompositionCard breakdown={breakdown} currency="CZK" />);

    const tabs = screen.getAllByRole("button").map((b) => b.textContent).filter((t) => ["Sectors", "Countries", "Categories"].includes(t));
    expect(tabs).toEqual(["Sectors", "Countries", "Categories"]);
    expect(screen.getByRole("row", { name: /Technology/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Stocks/ })).not.toBeInTheDocument();
  });

  it("shows no profit column for countries", () => {
    renderWithRouter(<CompositionCard breakdown={breakdown} currency="CZK" />);

    fireEvent.click(screen.getByRole("button", { name: "Countries" }));

    expect(screen.getByRole("row", { name: /United States/ })).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Name", "Weight", "Value"]);
  });
});

describe("DividendBarsCard", () => {
  const half = {
    months: [
      { month: "Oct", amount: 100 },
      { month: "Nov", amount: 0 },
      { month: "Dec", amount: 300 },
    ],
    total: 400,
    monthlyAverage: 400 / 3,
  };

  it("draws one bar per month with the tallest month at full height and states the totals", () => {
    render(<DividendBarsCard title="Upcoming payments" half={half} totalLabel="Rest of 2026" currency="USD" />);

    const chart = screen.getByRole("img", { name: /Upcoming payments by month/ });
    expect(chart).toHaveAccessibleName(expect.stringContaining("Dec $300"));
    expect(screen.getByText("Rest of 2026")).toBeInTheDocument();
    expect(screen.getByTestId("bar-Dec")).toHaveStyle({ height: "100%" });
    expect(screen.getByTestId("bar-Oct")).toHaveStyle({ height: "33.33%" });
  });

  it("stacks confirmed and forecasted amounts, labels both, and lists each company on hover", () => {
    const outlook = {
      months: [
        {
          month: "Oct", year: 2026, confirmed: 100, forecasted: 100, amount: 200,
          entries: [
            { ticker: "AAA", name: "Aaa Corp", amount: 100, status: "confirmed" },
            { ticker: "BBB", name: "Bbb Corp", amount: 100, status: "forecasted" },
          ],
        },
        { month: "Nov", year: 2026, confirmed: 0, forecasted: 50, amount: 50, entries: [{ ticker: "CCC", name: "Ccc Corp", amount: 50, status: "forecasted" }] },
      ],
      total: 250,
      monthlyAverage: 125,
    };
    render(<DividendBarsCard title="Upcoming payments" half={outlook} totalLabel="Next 12 months" currency="USD" />);

    const legend = screen.getByTestId("dividend-legend");
    expect(within(legend).getByText("Confirmed")).toBeInTheDocument();
    expect(within(legend).getByText("Forecasted")).toBeInTheDocument();
    expect(screen.getByTestId("forecast-Oct")).toHaveStyle({ height: "50%" });
    expect(screen.queryByTestId("dividend-tooltip")).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId("column-Oct"));

    const tooltip = screen.getByTestId("dividend-tooltip");
    expect(within(tooltip).getByText("Oct 2026")).toBeInTheDocument();
    expect(within(tooltip).getByText("AAA")).toBeInTheDocument();
    expect(within(tooltip).getByText("Confirmed")).toBeInTheDocument();
    expect(within(tooltip).getByText("BBB")).toBeInTheDocument();
    expect(within(tooltip).getByText("Forecasted")).toBeInTheDocument();

    fireEvent.mouseLeave(screen.getByRole("img", { name: /Upcoming payments by month/ }));
    expect(screen.queryByTestId("dividend-tooltip")).not.toBeInTheDocument();
  });

  it("puts the lead tile first and the trail tile last, and hides a tile without an amount", () => {
    const { container, rerender } = render(
      <DividendBarsCard title="Dividends received" half={half} totalLabel="2026 so far" currency="USD"
        leadStat={{ label: "All time", amount: 1234 }} trailStat={{ label: "Daily average", amount: 1.1 }} />,
    );
    const labels = [...container.querySelectorAll("span.data-label")].map((el) => el.textContent);
    expect(labels.slice(-4)).toEqual(["All time", "2026 so far", "Monthly average", "Daily average"]);

    rerender(<DividendBarsCard title="Dividends received" half={half} totalLabel="2026 so far" currency="USD" leadStat={{ label: "All time", amount: null }} />);
    expect(screen.queryByText("All time")).not.toBeInTheDocument();
  });

  it("shows an empty state when nothing is expected", () => {
    render(<DividendBarsCard title="Upcoming payments" half={{ months: [], total: 0, monthlyAverage: 0 }} totalLabel="Rest of 2026" currency="USD" emptyHint="No dividends expected." />);
    expect(screen.getByText("No dividends expected.")).toBeInTheDocument();
  });
});
