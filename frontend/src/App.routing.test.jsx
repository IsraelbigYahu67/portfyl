import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { TRACKER_HOME } from "./lib/routes";

const PORTFOLIO_ID = "11111111-1111-4111-8111-111111111111";

vi.mock("./auth/AuthProvider", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({
    ready: true,
    user: { email: "tester@portfyl.com" },
    currentWorkspace: { id: "workspace-1" },
    logout: vi.fn(),
    logoutAll: vi.fn(),
  }),
}));

vi.mock("./api", async () => {
  const actual = await vi.importActual("./api");
  return {
    ...actual,
    fetchCapabilities: () => Promise.resolve({ capabilities: [] }),
    fetchFxRate: () => Promise.resolve({ rate: 20 }),
    fetchPortfolios: () => Promise.resolve([
      {
        id: "11111111-1111-4111-8111-111111111111",
        name: "Test portfolio",
        is_default: true,
        transaction_count: 0,
      },
    ]),
  };
});

vi.mock("./components/AutoLoad", () => ({ default: () => null }));
vi.mock("./pages/Dashboard", () => ({ default: () => <div>Dashboard</div> }));
vi.mock("./pages/Cash", () => ({ default: () => <div>Cash page</div> }));

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

describe("tracker routing", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("sb_platform", "t212");
    localStorage.setItem("sb_portfolio_id", PORTFOLIO_ID);
    localStorage.setItem("sb_theme", "light");
  });

  it("does not expose Cash in navigation or at /cash", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/cash"]}>
          <LocationProbe />
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe(TRACKER_HOME);
    });
    expect(screen.queryByRole("link", { name: "Cash" })).not.toBeInTheDocument();
  });
});
