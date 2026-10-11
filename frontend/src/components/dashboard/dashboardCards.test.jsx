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
      { name: "Stocks", value: 1200, weight: 60 },
      { name: "ETFs", value: 800, weight: 40 },
    ],
    sectors: [{ name: "Technology", value: 2000, weight: 100 }],
    countries: [{ name: "United States", value: 2000, weight: 100 }],
  };

  it("lists categories with their weight and drift from a matching target group", () => {
    renderWithRouter(
      <CompositionCard breakdown={breakdown} targetGroups={[{ group: "Stocks", target_pct: 55 }]} currency="CZK" />
    );

    const stocks = screen.getByRole("row", { name: /Stocks/ });
    expect(within(stocks).getByText("60.0%")).toBeInTheDocument();
    expect(within(stocks).getByText("55% · +5.0 pp")).toBeInTheDocument();
    const etfs = screen.getByRole("row", { name: /ETFs/ });
    expect(within(etfs).getByText("No target")).toBeInTheDocument();
  });

  it("totals the donut from its own rows, because the API's total_value leaves cash out", () => {
    renderWithRouter(
      <CompositionCard
        breakdown={{ ...breakdown, total_value: 1200, asset_types: [{ name: "Stocks", value: 1200, weight: 60 }, { name: "Cash", value: 800, weight: 40 }] }}
        targetGroups={[]}
        currency="USD"
      />
    );
    expect(screen.getByText("$2K")).toBeInTheDocument();
  });

  it("switches the grouping to sectors", () => {
    renderWithRouter(<CompositionCard breakdown={breakdown} targetGroups={[]} currency="CZK" />);

    fireEvent.click(screen.getByRole("button", { name: "Sectors" }));

    expect(screen.getByRole("row", { name: /Technology/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Stocks/ })).not.toBeInTheDocument();
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

  it("shows an empty state when nothing is expected", () => {
    render(<DividendBarsCard title="Upcoming payments" half={{ months: [], total: 0, monthlyAverage: 0 }} totalLabel="Rest of 2026" currency="USD" emptyHint="No dividends expected." />);
    expect(screen.getByText("No dividends expected.")).toBeInTheDocument();
  });
});
