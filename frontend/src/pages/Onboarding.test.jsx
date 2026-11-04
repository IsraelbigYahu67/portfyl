import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import Onboarding, { buildOnboardingActions } from "./Onboarding";
import { ONBOARDING_CHOICE_KEYS, onboardingChoices } from "../components/onboarding/OnboardingView";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { TRACKER_HOME } from "../lib/routes";
import { legacyColorClassesIn } from "../test/legacyClasses";


const mocks = vi.hoisted(() => ({
  createPortfolio: vi.fn(),
  createDemoPortfolio: vi.fn(),
  createPendingImportPortfolio: vi.fn(),
  activatePortfolio: vi.fn(),
  setCurrentId: vi.fn(),
  refetchPortfolios: vi.fn(),
  recordPortfolioCreated: vi.fn(() => true),
  recordPortfolioDataImported: vi.fn(() => true),
}));

vi.mock("../api", () => ({
  createPortfolio: mocks.createPortfolio,
  createDemoPortfolio: mocks.createDemoPortfolio,
  createPendingImportPortfolio: mocks.createPendingImportPortfolio,
  activatePortfolio: mocks.activatePortfolio,
}));

vi.mock("../App", () => ({
  usePortfolio: () => ({
    portfolios: [],
    setCurrentId: mocks.setCurrentId,
    refetchPortfolios: mocks.refetchPortfolios,
    pendingImportPortfolio: null,
  }),
}));

vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({
    recordPortfolioCreated: mocks.recordPortfolioCreated,
    recordPortfolioDataImported: mocks.recordPortfolioDataImported,
  }),
}));


function mount(entry = "/onboarding") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/onboarding" element={<><Onboarding /><LocationProbe /></>} />
        <Route path={TRACKER_HOME} element={<div>Dashboard destination</div>} />
        <Route path="/import" element={<><div>Import destination</div><LocationProbe /></>} />
        <Route path="/settings" element={<><div>Settings destination</div><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}


describe("Onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createPortfolio.mockResolvedValue({ id: "portfolio-id" });
    mocks.createDemoPortfolio.mockResolvedValue({ id: "demo-id" });
    mocks.createPendingImportPortfolio.mockResolvedValue({ id: "pending-id", activation_state: "pending_import" });
    mocks.activatePortfolio.mockResolvedValue({ id: "pending-id", activation_state: "active" });
    mocks.refetchPortfolios.mockResolvedValue({});
  });

  describe("step 1: broker pick", () => {
    it("asks for the broker first and lists supported and unsupported brokers", () => {
      mount();

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
      expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
      for (const name of ["Trading 212", "Interactive Brokers", "eToro", "Degiro", "XTB", "Charles Schwab", "Fidelity"]) {
        expect(screen.getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
      }
      expect(screen.getByRole("button", { name: "Robinhood" })).toBeInTheDocument();
      expect(mocks.createPortfolio).not.toHaveBeenCalled();
    });

    it("filters both lists by the search box", () => {
      mount();

      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "x" } });

      expect(screen.getByRole("button", { name: /XTB/ })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Trading 212/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Robinhood" })).not.toBeInTheDocument();
    });

    it("moves to step 2 with the picked broker in the URL", () => {
      mount();

      fireEvent.click(screen.getByRole("button", { name: /Trading 212/ }));

      expect(screen.getByText("Step 2 of 2 · Trading 212")).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent("/onboarding?broker=trading212");
    });

    it("says up front when a listed broker is not supported", () => {
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Robinhood" }));

      expect(screen.getByRole("heading", { level: 1, name: "Portfyl doesn't support Robinhood yet" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Choose another broker" }));
      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    });

    it("checks a broker that is not on any list without putting it in the URL", () => {
      mount();

      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "Acme Invest" } });
      fireEvent.click(screen.getByRole("button", { name: "Check this broker" }));

      expect(screen.getByRole("heading", { level: 1, name: "Portfyl doesn't support Acme Invest yet" })).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent(/^\/onboarding$/);
    });

    it("offers the sample portfolio from the unsupported screen", async () => {
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(screen.getByRole("button", { name: /look around with sample data/i }));

      await waitFor(() => expect(mocks.createDemoPortfolio).toHaveBeenCalledTimes(1));
      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(mocks.recordPortfolioCreated).toHaveBeenCalledWith("demo");
    });
  });

  describe("step 2: tailored choices", () => {
    it("offers connect, file import and sample data for an API broker", () => {
      mount("/onboarding?broker=ibkr");

      expect(screen.getByRole("button", { name: "Connect Interactive Brokers" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Import your Interactive Brokers Flex XML" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Explore sample portfolio" })).toBeInTheDocument();
    });

    it("offers only file import and sample data for a file-only broker", () => {
      mount("/onboarding?broker=xtb");

      expect(screen.queryByRole("button", { name: /^connect/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Import your XTB file" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Explore sample portfolio" })).toBeInTheDocument();
    });

    it("falls back to a Portfyl CSV for an API-only broker", () => {
      mount("/onboarding?broker=etoro");

      expect(screen.getByRole("button", { name: "Import a Portfyl CSV" })).toBeInTheDocument();
    });

    it("ignores an unknown broker in the URL", () => {
      mount("/onboarding?broker=nope");

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    });

    it("goes back to the broker list", () => {
      mount("/onboarding?broker=xtb");

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    });

    it("renders the choices as plain action buttons, not preview toggles", () => {
      mount("/onboarding?broker=trading212");

      for (const { title } of onboardingChoices(findSupportedBroker("trading212"))) {
        expect(screen.getByRole("button", { name: title })).not.toHaveAttribute("aria-pressed");
      }
      expect(screen.getByRole("main")).not.toHaveAttribute("tabindex");
    });

    it("creates and selects a pending portfolio before opening the broker's file import", async () => {
      mount("/onboarding?broker=degiro");

      fireEvent.click(screen.getByRole("button", { name: "Import your Degiro file" }));

      await waitFor(() => expect(mocks.createPendingImportPortfolio).toHaveBeenCalledTimes(1));
      expect(mocks.setCurrentId).toHaveBeenCalledWith("pending-id");
      expect(await screen.findByText("Import destination")).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent("/import?broker=degiro");
      expect(mocks.recordPortfolioCreated).toHaveBeenCalledWith("csv");
      expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    });

    it("activates an explicit blank portfolio before opening the dashboard", async () => {
      mount("/onboarding?broker=trading212");
      fireEvent.click(screen.getByRole("button", { name: /start with a blank portfolio/i }));

      await waitFor(() => expect(mocks.activatePortfolio).toHaveBeenCalledWith("pending-id"));
      expect(mocks.setCurrentId).toHaveBeenCalledWith("pending-id");
      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(mocks.recordPortfolioCreated).toHaveBeenCalledWith("blank");
      expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    });

    it("creates a clearly labelled demo and opens its dashboard", async () => {
      mount("/onboarding?broker=trading212");

      fireEvent.click(screen.getByRole("button", { name: /explore sample portfolio/i }));

      await waitFor(() => expect(mocks.createDemoPortfolio).toHaveBeenCalledTimes(1));
      expect(mocks.setCurrentId).toHaveBeenCalledWith("demo-id");
      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(mocks.recordPortfolioCreated).toHaveBeenCalledWith("demo");
      expect(mocks.recordPortfolioDataImported).toHaveBeenCalledWith("demo");
    });

    it("creates a portfolio named after the broker before opening its connection", async () => {
      mount("/onboarding?broker=trading212");

      fireEvent.click(screen.getByRole("button", { name: "Connect Trading 212" }));

      await waitFor(() => expect(mocks.createPortfolio).toHaveBeenCalledWith({ name: "Trading 212" }));
      expect(mocks.setCurrentId).toHaveBeenCalledWith("portfolio-id");
      expect(await screen.findByText("Settings destination")).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent("/settings?section=connections&broker=trading212");
      expect(mocks.recordPortfolioCreated).toHaveBeenCalledWith("broker");
      expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    });

    it("navigates before the portfolio refetch can unmount onboarding", async () => {
      let finishRefetch;
      mocks.refetchPortfolios.mockReturnValueOnce(new Promise((resolve) => {
        finishRefetch = resolve;
      }));
      mount("/onboarding?broker=etoro");

      fireEvent.click(screen.getByRole("button", { name: "Connect eToro" }));

      await waitFor(() => expect(mocks.setCurrentId).toHaveBeenCalledWith("portfolio-id"));
      expect(await screen.findByText("Settings destination")).toBeInTheDocument();
      finishRefetch({});
    });

    it("shows an actionable API error without navigating", async () => {
      mocks.createDemoPortfolio.mockRejectedValueOnce({
        response: { data: { detail: "Demo limit reached" } },
      });
      mount("/onboarding?broker=trading212");

      fireEvent.click(screen.getByRole("button", { name: /explore sample portfolio/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Demo limit reached");
      expect(mocks.recordPortfolioCreated).not.toHaveBeenCalled();
      expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    });
  });

  it("wires exactly one action to every onboarding choice", () => {
    const actions = buildOnboardingActions({ beginImport: vi.fn(), activate: vi.fn(), broker: findSupportedBroker("ibkr") });

    // A choice without an action would render a button that does nothing.
    expect(new Set(Object.keys(actions))).toEqual(new Set(ONBOARDING_CHOICE_KEYS));
    for (const action of Object.values(actions)) expect(action).toBeTypeOf("function");
    // Building the map is pure: nothing is created until a choice is clicked.
    expect(mocks.createPortfolio).not.toHaveBeenCalled();
    expect(mocks.createDemoPortfolio).not.toHaveBeenCalled();
    expect(mocks.createPendingImportPortfolio).not.toHaveBeenCalled();
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Onboarding.jsx", import.meta.url))).toEqual([]);
  });
});
