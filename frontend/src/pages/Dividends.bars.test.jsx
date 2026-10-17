import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dividends from "./Dividends";

vi.mock("../api", () => {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return {
    fetchDividends: () => Promise.resolve([]),
    fetchDividendForecast: () => Promise.resolve({
      year: 2026,
      months: months.map((month) => ({ month, paid: 10, estimated: 5, entries: [] })),
      outlook: { months: months.map((month) => ({ month, year: 2027, confirmed: 4, forecasted: 6, entries: [] })) },
    }),
    fetchDividendGrowth: () => Promise.resolve([]),
  };
});

vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

describe("Dividends bars", () => {
  it("shows the dashboard's received / upcoming bar cards", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <Dividends />
      </QueryClientProvider>
    );
    expect(await screen.findByText("Dividends received")).toBeInTheDocument();
    expect(screen.getByText("Upcoming payments")).toBeInTheDocument();
    expect(screen.getByText("Next 12 months")).toBeInTheDocument();
    expect(screen.getAllByTestId("bar-Jan").length).toBeGreaterThan(0);
    expect(screen.getByTestId("dividend-legend")).toBeInTheDocument();
  });
});
