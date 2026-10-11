import { render, screen } from "@testing-library/react";
import PortfolioHero from "./PortfolioHero";

const summary = {
  total_value: 248310.55, cash: 12000, net_worth: 260310.55, total_invested: 190000, total_pnl: 58310.55,
  total_pnl_percent: 30.7, total_dividends: 2100, holdings_count: 23,
  day_change: 5820.12, day_change_percent: 2.41,
};

describe("PortfolioHero", () => {
  it("renders the portfolio value and the day pill", () => {
    render(<PortfolioHero summary={summary} loading={false} currency="USD" series={[]} />);
    expect(screen.getByText(/2\.41%/)).toBeInTheDocument();
  });

  it("renders net worth and the positions/cash split", () => {
    render(<PortfolioHero summary={summary} loading={false} currency="USD" series={[]} />);
    expect(screen.getByText(/Net Worth/i)).toBeInTheDocument();
    expect(screen.getByText(/Cash/i)).toBeInTheDocument();
  });

  it("net worth headline uses financial-headline and the positions/cash line uses financial-data", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<PortfolioHero summary={summary} loading={false} currency="USD" series={[]} />);
    expect(screen.getByText(/\$260,310\.55/)).toHaveClass("financial-headline");
    expect(screen.getByText(/Cash/i).closest("div")).toHaveClass("financial-data");
  });

  it("renders skeletons while loading without throwing", () => {
    const { container } = render(<PortfolioHero summary={undefined} loading currency="USD" series={[]} />);
    expect(container.querySelector(".shimmer")).toBeTruthy();
  });
});

describe("PortfolioHero with a broker snapshot", () => {
  const emptyLedger = { ...summary, total_value: 0, cash: 1000, net_worth: 1000, day_change: 0, day_change_percent: 0 };

  it("shows the snapshot value plus cash while history loads, and says so", () => {
    render(
      <PortfolioHero
        summary={emptyLedger}
        snapshot={{ positionsValue: 68609, asOf: "2026-10-11T14:00:00Z" }}
        loading={false}
        currency="USD"
        series={[]}
      />,
    );
    expect(screen.getByText(/\$69,609\.00/)).toBeInTheDocument();
    expect(screen.getByText(/Positions \$68,609\.00/)).toBeInTheDocument();
    expect(screen.getByText(/Trading 212 snapshot/i)).toBeInTheDocument();
    expect(screen.queryByText(/0\.00%/)).not.toBeInTheDocument();
  });
});
