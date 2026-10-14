import { render, screen, within, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, afterEach } from "vitest";
import DemoApp from "./DemoApp";
import { DemoDataProvider } from "./DemoDataContext";
import { demoPortfolio } from "./demoPortfolio";
import { DEMO_COPY } from "./demoCopy";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";
// DemoApp lazy-loads its pages. Load them during collection (untimed) so the
// first route test doesn't spend its findBy window on the cold module graph
// (recharts alone is ~1 s, ~2 s+ under full-suite load).
import "./pages/DemoOverview";
import "./pages/DemoAllocation";
import "./pages/DemoAnalytics";
import "./pages/DemoDividends";
import "./pages/DemoStock";

const lazyRouteWait = { timeout: 5_000 };

function renderAt(path, { initialConsent = "pending" } = {}) {
  const adapter = createMemoryAdapter();
  const result = render(
    <MemoryRouter initialEntries={[path]}>
      <AnalyticsProvider initialConsent={initialConsent} adapterFactory={() => adapter}>
        <DemoDataProvider>
          <DemoApp />
        </DemoDataProvider>
      </AnalyticsProvider>
    </MemoryRouter>
  );
  return { ...result, adapter };
}

afterEach(() => localStorage.clear());

describe("DemoApp routing", () => {
  it.each([
    ["/demo", "Overview"],
    ["/demo/allocation", "Allocation"],
    ["/demo/analytics", "Analytics"],
    ["/demo/dividends", "Dividends"],
    ["/demo/stock/MSFT", "MSFT"],
  ])("renders the %s route", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { name: heading }, lazyRouteWait)).toBeInTheDocument();
  }, 15_000);

  it("renders a branded not-found state for an unknown demo route", async () => {
    renderAt("/demo/does-not-exist");
    expect(await screen.findByText(DEMO_COPY.en.notFoundTitle)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: DEMO_COPY.en.backToDemo })).toHaveAttribute("href", "/demo");
  });
});

describe("DemoShell", () => {
  it("exposes a navigation landmark with active-link state", async () => {
    renderAt("/demo/allocation");
    const nav = screen.getByRole("navigation", { name: DEMO_COPY.en.navigation });
    const allocationLink = within(nav).getByRole("link", { name: DEMO_COPY.en.allocation });
    expect(allocationLink).toHaveClass("bg-brand/10");
    const overviewLink = within(nav).getByRole("link", { name: DEMO_COPY.en.overview });
    expect(overviewLink).not.toHaveClass("bg-brand/10");
  });

  it("discloses the synthetic data and as-of date, and links back to the marketing site", async () => {
    renderAt("/demo");
    expect(await screen.findByText(new RegExp(DEMO_COPY.en.disclosure))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(demoPortfolio.asOf))).toBeInTheDocument();
    const backLinks = screen.getAllByRole("link", { name: DEMO_COPY.en.backHome });
    expect(backLinks.length).toBeGreaterThan(0);
    backLinks.forEach((link) => expect(link).toHaveAttribute("href", "/"));
  });

  it("offers a registration CTA carrying source=demo", async () => {
    renderAt("/demo");
    const cta = await screen.findByRole("link", { name: DEMO_COPY.en.createAccount });
    expect(cta).toHaveAttribute("href", expect.stringContaining("source=demo"));
  });

  it("never surfaces a private-app action word, in any supported language", async () => {
    renderAt("/demo");
    const forbidden = /\b(import|sync|edit|delete|settings|assistant|transaction|refresh)\b/i;
    const controls = [...screen.queryAllByRole("link"), ...screen.queryAllByRole("button")];
    for (const control of controls) {
      expect(control.textContent).not.toMatch(forbidden);
    }
  });

  it("emits demo_started (direct entry) and one demo_page_viewed per visited route", async () => {
    const { adapter } = renderAt("/demo/allocation", { initialConsent: "accepted" });
    await screen.findByRole("heading", { name: "Allocation" }, lazyRouteWait);
    await waitFor(() =>
      expect(adapter.events).toEqual(
        expect.arrayContaining([
          ["demo_started", { language: "en", entry_point: "direct" }],
          ["demo_page_viewed", { demo_page: "allocation", language: "en" }],
        ])
      )
    );
  });

  it("emits demo_stock_viewed for a valid demo symbol", async () => {
    const { adapter } = renderAt("/demo/stock/MSFT", { initialConsent: "accepted" });
    await screen.findByRole("heading", { name: "MSFT" }, lazyRouteWait);
    await waitFor(() =>
      expect(adapter.events).toContainEqual(["demo_stock_viewed", { demo_symbol: "MSFT" }])
    );
  });

  it("emits signup_cta_clicked with source_surface=demo when the registration CTA is clicked", async () => {
    const { adapter } = renderAt("/demo", { initialConsent: "accepted" });
    const cta = await screen.findByRole("link", { name: DEMO_COPY.en.createAccount });
    cta.click();
    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_cta_clicked", { source_surface: "demo", language: "en" }])
    );
  });
});

describe("DemoDataProvider failure mode", () => {
  it("renders the branded unavailable state, not a blank screen, for an invalid fixture", async () => {
    const badValue = { ...demoPortfolio, holdings: demoPortfolio.holdings.slice(0, 9) };
    render(
      <MemoryRouter initialEntries={["/demo"]}>
        <AnalyticsProvider initialConsent="pending" adapterFactory={() => createMemoryAdapter()}>
          <DemoDataProvider value={badValue}>
            <DemoApp />
          </DemoDataProvider>
        </AnalyticsProvider>
      </MemoryRouter>
    );
    expect(await screen.findByText(DEMO_COPY.en.unavailableTitle)).toBeInTheDocument();
  });
});
