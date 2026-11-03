import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App, { usePortfolio } from "./App";
import { TRACKER_HOME } from "./lib/routes";

const PORTFOLIO_ID = "11111111-1111-4111-8111-111111111111";
const mocks = vi.hoisted(() => ({
  fetchCapabilities: vi.fn(),
  fetchPortfolios: vi.fn(),
}));

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
    fetchCapabilities: mocks.fetchCapabilities,
    fetchFxRate: () => Promise.resolve({ rate: 20 }),
    fetchPortfolios: mocks.fetchPortfolios,
  };
});

vi.mock("./components/StartupPrefetch", () => ({ default: () => {
  const { currentId, ready } = usePortfolio();
  return <output data-testid="portfolio-ready">{ready ? currentId : "not ready"}</output>;
} }));
vi.mock("./pages/Dashboard", () => ({
  default: () => <h1>Portfolio overview</h1>,
}));
vi.mock("./pages/Onboarding", () => ({
  default: () => <h1>Create your first portfolio</h1>,
}));
vi.mock("./pages/Import", () => ({
  default: ({ focused = false }) => <h1>{focused ? "Focused pending import" : "Portfolio import"}</h1>,
}));
vi.mock("./pages/Cash", () => ({ default: () => <div>Cash page</div> }));

function LocationProbe() {
  const { pathname } = useLocation();
  return <output data-testid="location">{pathname}</output>;
}

function renderApp(path = TRACKER_HOME) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <LocationProbe />
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("authenticated routing", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("sb_portfolio_id", PORTFOLIO_ID);
    localStorage.setItem("sb_theme", "light");
    mocks.fetchCapabilities.mockReset().mockResolvedValue({ capabilities: [] });
    mocks.fetchPortfolios.mockReset().mockResolvedValue([{
      id: PORTFOLIO_ID,
      name: "CSV portfolio",
      is_default: true,
      transaction_count: 0,
    }]);
  });

  it("routes a portfolio user directly to Dashboard without broker state", async () => {
    localStorage.removeItem("sb_platform");
    renderApp();

    expect(await screen.findByRole("heading", { name: /portfolio overview/i }))
      .toBeInTheDocument();
  });

  it("removes the obsolete platform key", async () => {
    localStorage.setItem("sb_platform", "t212");
    renderApp();

    await screen.findByRole("heading", { name: /portfolio overview/i });
    expect(localStorage.getItem("sb_platform")).toBeNull();
  });

  it("keeps users with no portfolio in onboarding", async () => {
    mocks.fetchPortfolios.mockResolvedValue([]);
    renderApp();

    expect(await screen.findByRole("heading", { name: /create your first portfolio/i }))
      .toBeInTheDocument();
  });

  it("lets a portfolio user replay onboarding as a full-screen preview", async () => {
    renderApp("/onboarding/preview");

    expect(await screen.findByText(/onboarding preview/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /add your first portfolio/i })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /portfolio overview/i })).not.toBeInTheDocument();
  });

  it("gives users without a portfolio the real onboarding even on the preview URL", async () => {
    mocks.fetchPortfolios.mockResolvedValue([]);
    renderApp("/onboarding/preview");

    expect(await screen.findByRole("heading", { name: /create your first portfolio/i }))
      .toBeInTheDocument();
    expect(screen.queryByText(/onboarding preview/i)).not.toBeInTheDocument();
  });

  it("restores a pending onboarding import without mounting portfolio navigation", async () => {
    mocks.fetchPortfolios.mockResolvedValue([{
      id: PORTFOLIO_ID,
      name: "My portfolio",
      is_default: true,
      transaction_count: 0,
      activation_state: "pending_import",
    }]);
    renderApp("/import");

    expect(await screen.findByRole("heading", { name: "Focused pending import" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /dashboard/i })).not.toBeInTheDocument();
  });

  it("keeps a pending record hidden from the normal portfolio switcher", async () => {
    mocks.fetchPortfolios.mockResolvedValue([
      { id: PORTFOLIO_ID, name: "Active portfolio", is_default: true, transaction_count: 1, activation_state: "active" },
      { id: "33333333-3333-4333-8333-333333333333", name: "Pending import", is_default: false, transaction_count: 0, activation_state: "pending_import" },
    ]);
    renderApp();
    await screen.findByRole("heading", { name: /portfolio overview/i });
    fireEvent.click(screen.getByRole("button", { name: /switch portfolio/i }));
    expect(screen.getAllByText("Active portfolio").length).toBeGreaterThan(0);
    expect(screen.queryByText("Pending import")).not.toBeInTheDocument();
  });

  it("keeps edition navigation capability-filtered", async () => {
    const editionLink = import.meta.env.VITE_PORTFYL_EDITION === "cloud"
      ? { capability: "settings", name: /plans/i }
      : { capability: "tax_report", name: /tax report/i };
    const first = renderApp();
    await screen.findByRole("heading", { name: /portfolio overview/i });
    expect(screen.queryByRole("link", { name: editionLink.name })).not.toBeInTheDocument();
    first.unmount();

    mocks.fetchCapabilities.mockResolvedValue({ capabilities: [editionLink.capability] });
    renderApp();
    expect(await screen.findByRole("link", { name: editionLink.name })).toBeInTheDocument();
  });

  it("shows portfolio navigation without a platform reset action", async () => {
    renderApp();

    await screen.findByRole("heading", { name: /portfolio overview/i });
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /trading 212|change platform/i }))
      .not.toBeInTheDocument();
  });

  it("switches portfolios without writing obsolete platform state", async () => {
    mocks.fetchPortfolios.mockResolvedValue([
      {
        id: PORTFOLIO_ID,
        name: "CSV portfolio",
        is_default: true,
        transaction_count: 0,
      },
      {
        id: "33333333-3333-4333-8333-333333333333",
        name: "Second portfolio",
        is_default: false,
        transaction_count: 2,
      },
    ]);
    renderApp();
    await screen.findByRole("heading", { name: /portfolio overview/i });
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const removeItem = vi.spyOn(Storage.prototype, "removeItem");

    fireEvent.click(screen.getByRole("button", { name: /switch portfolio/i }));
    fireEvent.click(screen.getByText("Second portfolio").closest("button"));

    expect(setItem.mock.calls.some(([key]) => key === "sb_platform")).toBe(false);
    expect(removeItem.mock.calls.some(([key]) => key === "sb_platform")).toBe(false);
  });

  it("routes to Cash and exposes it in navigation", async () => {
    renderApp("/cash");

    expect(await screen.findByText("Cash page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cash" })).toBeInTheDocument();
  });

  it("keeps the switched portfolio ready while refreshing workspace metadata", async () => {
    const secondId = "33333333-3333-4333-8333-333333333333";
    const portfolios = [
      { id: PORTFOLIO_ID, name: "First portfolio", is_default: true, transaction_count: 1 },
      { id: secondId, name: "Second portfolio", is_default: false, transaction_count: 0 },
    ];
    let resolveRefresh;
    mocks.fetchPortfolios.mockResolvedValueOnce(portfolios).mockImplementation(
      () => new Promise(resolve => { resolveRefresh = resolve; }),
    );
    renderApp();
    await screen.findByRole("heading", { name: /portfolio overview/i });
    fireEvent.click(screen.getByRole("button", { name: /switch portfolio/i }));
    fireEvent.click(screen.getByText("Second portfolio").closest("button"));
    await waitFor(() => expect(mocks.fetchPortfolios).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("portfolio-ready")).toHaveTextContent(secondId);
    resolveRefresh(portfolios);
    await waitFor(() => expect(screen.getByTestId("portfolio-ready")).toHaveTextContent(secondId));
  });

  it("redirects the retired overview route to the tracker home", async () => {
    renderApp("/overview");

    await waitFor(() => {
      expect(screen.getByTestId("location").textContent).toBe(TRACKER_HOME);
    });
    expect(await screen.findByRole("heading", { name: /portfolio overview/i }))
      .toBeInTheDocument();
  });
});
