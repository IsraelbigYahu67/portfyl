import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Overview from "./Overview";

vi.mock("../api", () => ({
  fetchOverview: () => Promise.resolve({
    currency: "USD",
    total_net_worth: 12345.67,
    total_day_change: 100.5,
    total_day_change_percent: 0.82,
    portfolio_count: 2,
    sectors: [{ name: "Technology", value: 12345.67, weight: 100 }],
    countries: [{ name: "United States", value: 12345.67, weight: 100 }],
    asset_types: [{ name: "Stock", value: 12345.67, weight: 100 }],
  }),
}));

describe("Overview", () => {
  it("renders total net worth and allocation charts", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Overview />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/Total net worth/i)).toBeInTheDocument();
    expect(await screen.findByText(/Technology/i)).toBeInTheDocument();
  });
});
