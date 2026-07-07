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

  it("renders skeletons while loading without throwing", () => {
    const { container } = render(<PortfolioHero summary={undefined} loading currency="USD" series={[]} />);
    expect(container.querySelector(".shimmer")).toBeTruthy();
  });
});
