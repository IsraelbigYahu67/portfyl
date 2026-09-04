import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import Pricing from "./Pricing";


vi.mock("../api", () => ({
  fetchBillingPrices: () => Promise.resolve({
    prices: [
      { plan: "investor", interval: "month", amount_cents: 499 },
      { plan: "investor", interval: "year", amount_cents: 4900 },
      { plan: "pro", interval: "month", amount_cents: 799 },
      { plan: "pro", interval: "year", amount_cents: 7900 },
    ],
  }),
  fetchEntitlements: () => Promise.resolve({
    plan: "pro",
    source: "trial",
    effective_until: "2026-09-11T12:00:00+00:00",
    usage: { hosted_ai_trial: { used: 5, limit: 15, remaining: 10 } },
  }),
  createCheckout: vi.fn(),
  createBillingPortal: vi.fn(),
}));


describe("Pricing", () => {
  it("shows trial usage and keeps Checkout success pending until reconciliation", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <MemoryRouter initialEntries={["/pricing?billing=success"]}>
        <QueryClientProvider client={queryClient}>
          <Pricing />
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Current access:/i)).toHaveTextContent("pro");
    expect(screen.getByText(/Plan access is pending signed Stripe reconciliation/i)).toBeInTheDocument();
    expect(screen.getByText(/Hosted AI remaining in trial: 10 of 15/i)).toBeInTheDocument();
    expect(screen.queryByText(/Tax Report|Screener/i)).not.toBeInTheDocument();
    queryClient.clear();
  });
});
