import { render, screen } from "@testing-library/react";
import { StockHeader } from "./StockHeader";
import { StockOverview } from "../StockDetail";

const data = { ticker: "AAPL", name: "Apple", currency: "USD", ratios: {}, sector_avg: {}, analyst: {}, financials: {}, financials_quarterly: {}, ttm: {} };

it("uses an h1 for the stock route header while retaining h2 for embedded overviews", () => {
  const route = render(<StockHeader data={data} />);
  expect(screen.getByRole("heading", { level: 1, name: "AAPL" })).toBeInTheDocument();
  route.unmount();

  render(<StockOverview data={data} sectionIds={[]} />);
  expect(screen.getByRole("heading", { level: 2, name: "AAPL" })).toBeInTheDocument();
});
