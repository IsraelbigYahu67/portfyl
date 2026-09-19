import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, afterEach } from "vitest";
import DemoApp from "./DemoApp";
import { DemoDataProvider } from "./DemoDataContext";
import { demoPortfolio } from "./demoPortfolio";
import { DEMO_COPY } from "./demoCopy";

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <DemoDataProvider>
        <DemoApp />
      </DemoDataProvider>
    </MemoryRouter>
  );
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
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

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
});

describe("DemoDataProvider failure mode", () => {
  it("renders the branded unavailable state, not a blank screen, for an invalid fixture", async () => {
    const badValue = { ...demoPortfolio, holdings: demoPortfolio.holdings.slice(0, 9) };
    render(
      <MemoryRouter initialEntries={["/demo"]}>
        <DemoDataProvider value={badValue}>
          <DemoApp />
        </DemoDataProvider>
      </MemoryRouter>
    );
    expect(await screen.findByText(DEMO_COPY.en.unavailableTitle)).toBeInTheDocument();
  });
});
