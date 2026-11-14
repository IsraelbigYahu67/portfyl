import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import Onboarding, { buildOnboardingActions } from "./Onboarding";
import { ONBOARDING_CHOICE_KEYS, onboardingChoices } from "../components/onboarding/OnboardingView";
import { findSupportedBroker } from "../lib/onboardingBrokers";
import { INTENDED_BROKER_KEY, intendedBroker } from "../lib/signupIntent";
import { TRACKER_HOME } from "../lib/routes";
import { legacyColorClassesIn } from "../test/legacyClasses";
import { I18nProvider } from "../i18n/I18nProvider";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";


const mocks = vi.hoisted(() => ({
  createPortfolio: vi.fn(),
  createDemoPortfolio: vi.fn(),
  createPendingImportPortfolio: vi.fn(),
  activatePortfolio: vi.fn(),
  requestBrokerSupport: vi.fn(),
  setCurrentId: vi.fn(),
  setCurrency: vi.fn(),
  refetchPortfolios: vi.fn(),
  recordPortfolioCreated: vi.fn(() => true),
  recordPortfolioDataImported: vi.fn(() => true),
}));

vi.mock("../api", () => ({
  createPortfolio: mocks.createPortfolio,
  createDemoPortfolio: mocks.createDemoPortfolio,
  createPendingImportPortfolio: mocks.createPendingImportPortfolio,
  activatePortfolio: mocks.activatePortfolio,
  requestBrokerSupport: mocks.requestBrokerSupport,
}));

vi.mock("../App", async () => {
  const { useState } = await import("react");
  return {
    // A real state hook, so the view re-renders with the picked currency.
    useCurrency: () => {
      const [currency, setCurrency] = useState("USD");
      return {
        currency,
        setCurrency: (code) => { mocks.setCurrency(code); setCurrency(code); },
      };
    },
    usePortfolio: () => ({
      portfolios: [],
      setCurrentId: mocks.setCurrentId,
      refetchPortfolios: mocks.refetchPortfolios,
      pendingImportPortfolio: null,
    }),
  };
});

vi.mock("../analytics/useRegisteredActivation", () => ({
  useRegisteredActivation: () => ({
    recordPortfolioCreated: mocks.recordPortfolioCreated,
    recordPortfolioDataImported: mocks.recordPortfolioDataImported,
  }),
}));


// Most tests render without an I18nProvider, so the view stays in English.
// Onboarding reads useAnalytics (like Register and Welcome), so every mount is
// wrapped in the real provider with a memory adapter, exposed as `analytics`.
let analytics;

function mount(entry = "/onboarding", { i18n = false } = {}) {
  analytics = createMemoryAdapter();
  const routes = (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/onboarding" element={<><Onboarding /><LocationProbe /></>} />
        <Route path={TRACKER_HOME} element={<div>Dashboard destination</div>} />
        <Route path="/import" element={<><div>Import destination</div><LocationProbe /></>} />
        <Route path="/settings" element={<><div>Settings destination</div><LocationProbe /></>} />
      </Routes>
    </MemoryRouter>
  );
  return render(
    <AnalyticsProvider initialConsent="accepted" adapterFactory={() => analytics}>
      {i18n ? <I18nProvider initial="en">{routes}</I18nProvider> : routes}
    </AnalyticsProvider>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}


describe("Onboarding", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.createPortfolio.mockResolvedValue({ id: "portfolio-id" });
    mocks.createDemoPortfolio.mockResolvedValue({ id: "demo-id" });
    mocks.createPendingImportPortfolio.mockResolvedValue({ id: "pending-id", activation_state: "pending_import" });
    mocks.activatePortfolio.mockResolvedValue({ id: "pending-id", activation_state: "active" });
    mocks.refetchPortfolios.mockResolvedValue({});
    mocks.requestBrokerSupport.mockResolvedValue({});
  });

  describe("language and currency chip", () => {
    afterEach(() => localStorage.clear());

    it("has no separate language step: onboarding opens on the broker pick", () => {
      mount();

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Choose your language" })).not.toBeInTheDocument();
    });

    it("shows the language and display currency as a chip", () => {
      mount();

      expect(screen.getByRole("button", { name: "English · USD" })).toBeInTheDocument();
    });

    it("switches the app language, saves it and preselects the local currency", async () => {
      mount("/onboarding", { i18n: true });

      fireEvent.click(screen.getByRole("button", { name: "English · USD" }));
      fireEvent.click(screen.getByRole("combobox", { name: "Language" }));
      fireEvent.click(document.querySelector('[role="option"][data-value="de"]'));

      expect(mocks.setCurrency).toHaveBeenLastCalledWith("EUR");
      expect(await screen.findByRole("heading", { level: 1, name: "Welchen Broker nutzt du?" })).toBeInTheDocument();
      expect(localStorage.getItem("portfyl_language")).toBe("de");
    });

    it("lets the visitor pick only a different currency", () => {
      mount();

      fireEvent.click(screen.getByRole("button", { name: "English · USD" }));
      fireEvent.click(screen.getByRole("combobox", { name: "Display currency" }));
      fireEvent.click(document.querySelector('[role="option"][data-value="PLN"]'));

      expect(mocks.setCurrency).toHaveBeenCalledTimes(1);
      expect(mocks.setCurrency).toHaveBeenLastCalledWith("PLN");
      expect(screen.getByRole("button", { name: "English · PLN" })).toBeInTheDocument();
    });
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

    it("moves to step 3 with the picked broker in the URL", () => {
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

  describe("notify me for an unsupported broker", () => {
    // The location probe is an <output>, which is also role "status".
    const status = {
      find: () => within(screen.getByRole("main")).findByRole("status"),
      query: () => within(screen.getByRole("main")).queryByRole("status"),
    };
    const notify = (name) => screen.getByRole("button", { name: `Notify me when ${name} is supported` });

    it("saves the request once and then thanks the visitor", async () => {
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(notify("Revolut"));

      expect(await status.find()).toHaveTextContent("Thanks, we'll e-mail you when Revolut is supported.");
      expect(mocks.requestBrokerSupport).toHaveBeenCalledTimes(1);
      expect(mocks.requestBrokerSupport).toHaveBeenCalledWith("Revolut");
      expect(screen.queryByRole("button", { name: /Notify me/ })).not.toBeInTheDocument();
    });

    it("ignores a second click while the first request is running", async () => {
      let finish;
      mocks.requestBrokerSupport.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(notify("Revolut"));
      fireEvent.click(notify("Revolut"));

      expect(mocks.requestBrokerSupport).toHaveBeenCalledTimes(1);
      expect(notify("Revolut")).toBeDisabled();
      finish({});
      expect(await status.find()).toBeInTheDocument();
    });

    it("shows an alert and keeps the button when saving fails, so the visitor can retry", async () => {
      mocks.requestBrokerSupport.mockRejectedValueOnce(new Error("boom"));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(notify("Revolut"));

      expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't save that. Please try again.");
      fireEvent.click(notify("Revolut"));
      expect(await status.find()).toBeInTheDocument();
      expect(mocks.requestBrokerSupport).toHaveBeenCalledTimes(2);
    });

    it("sends a typed name with markup as plain text and shows it literally", async () => {
      mount();
      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "<b>x</b>" } });
      fireEvent.click(screen.getByRole("button", { name: "Check this broker" }));

      expect(screen.getByText("Notify me when <b>x</b> is supported")).toBeInTheDocument();
      fireEvent.click(notify("<b>x</b>"));

      await waitFor(() => expect(mocks.requestBrokerSupport).toHaveBeenCalledWith("<b>x</b>"));
    });

    it("starts again from idle when another unsupported broker is picked", async () => {
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));
      fireEvent.click(notify("Revolut"));
      expect(await status.find()).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Choose another broker" }));
      fireEvent.click(screen.getByRole("button", { name: "Robinhood" }));

      expect(status.query()).not.toBeInTheDocument();
      expect(notify("Robinhood")).toBeEnabled();
    });

    it("does not show a late result for a broker that is no longer on screen", async () => {
      let finish;
      mocks.requestBrokerSupport.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));
      fireEvent.click(notify("Revolut"));

      fireEvent.click(screen.getByRole("button", { name: "Choose another broker" }));
      fireEvent.click(screen.getByRole("button", { name: "Robinhood" }));
      finish({});
      await Promise.resolve();
      await Promise.resolve();

      expect(status.query()).not.toBeInTheDocument();
      expect(notify("Robinhood")).toBeEnabled();
    });
  });

  describe("funnel analytics", () => {
    const events = () => analytics.events.map(([name, props]) => [name, props]);
    const named = (name) => analytics.events.filter(([n]) => n === name);
    const notify = (name) => screen.getByRole("button", { name: `Notify me when ${name} is supported` });

    it("reports the broker step once, not on every re-render", async () => {
      mount();
      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(1));

      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "x" } });
      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "xt" } });
      await Promise.resolve();
      await Promise.resolve();

      expect(events()).toEqual([["onboarding_step_viewed", { step: "broker" }]]);
    });

    it("reports the pick and then the choices step when a supported broker is picked", async () => {
      mount();
      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(1));

      fireEvent.click(screen.getByRole("button", { name: /XTB/ }));

      await waitFor(() => expect(events()).toHaveLength(3));
      expect(events()).toEqual([
        ["onboarding_step_viewed", { step: "broker" }],
        ["onboarding_broker_picked", { broker_key: "xtb" }],
        ["onboarding_step_viewed", { step: "choices" }],
      ]);
    });

    it("reports a step again when the visitor comes back to it", async () => {
      mount();
      fireEvent.click(screen.getByRole("button", { name: /XTB/ }));
      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(2));

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));

      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(3));
      expect(named("onboarding_step_viewed").map(([, props]) => props.step)).toEqual(["broker", "choices", "broker"]);
      expect(named("onboarding_broker_picked")).toHaveLength(1);
    });

    it("reports an unsupported pick as the fixed marker, never the typed name", async () => {
      mount();
      fireEvent.change(screen.getByLabelText("Search brokers"), { target: { value: "Revolut" } });
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(2));
      expect(events()).toEqual([
        ["onboarding_step_viewed", { step: "broker" }],
        ["onboarding_broker_picked", { broker_key: "unsupported" }],
        ["onboarding_step_viewed", { step: "unsupported" }],
      ]);
      expect(JSON.stringify(analytics.events)).not.toMatch(/revolut/i);
    });

    it("does not call a remembered or URL broker a pick", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(1));
      expect(events()).toEqual([["onboarding_step_viewed", { step: "choices" }]]);

      mount("/onboarding?broker=ibkr");
      await waitFor(() => expect(named("onboarding_step_viewed")).toHaveLength(1));
      expect(named("onboarding_broker_picked")).toHaveLength(0);
    });

    it("reports broker_request_sent with no properties after a saved request", async () => {
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(notify("Revolut"));

      await waitFor(() => expect(named("broker_request_sent")).toHaveLength(1));
      expect(named("broker_request_sent")[0][1]).toEqual({});
      expect(JSON.stringify(analytics.events)).not.toMatch(/revolut/i);
    });

    it("reports nothing for a request that failed", async () => {
      mocks.requestBrokerSupport.mockRejectedValueOnce(new Error("boom"));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));

      fireEvent.click(notify("Revolut"));

      expect(await screen.findByRole("alert")).toBeInTheDocument();
      await Promise.resolve();
      expect(named("broker_request_sent")).toHaveLength(0);
    });

    it("reports nothing for a late answer about a broker no longer on screen", async () => {
      let finish;
      mocks.requestBrokerSupport.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
      mount();
      fireEvent.click(screen.getByRole("button", { name: "Revolut" }));
      fireEvent.click(notify("Revolut"));
      fireEvent.click(screen.getByRole("button", { name: "Choose another broker" }));

      finish({});
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();

      expect(named("broker_request_sent")).toHaveLength(0);
    });
  });

  describe("step 2: tailored choices", () => {
    it("offers connect and file import cards, plus the sample data link, for an API broker", () => {
      mount("/onboarding?broker=ibkr");

      expect(screen.getByRole("button", { name: "Connect Interactive Brokers" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Import your Interactive Brokers Flex XML" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Just look around with sample data first" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Explore sample portfolio" })).not.toBeInTheDocument();
    });

    it("offers only file import and the sample data link for a file-only broker", () => {
      mount("/onboarding?broker=xtb");

      expect(screen.queryByRole("button", { name: /^connect/i })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Import your XTB file" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Just look around with sample data first" })).toBeInTheDocument();
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

      fireEvent.click(screen.getByRole("button", { name: "Just look around with sample data first" }));

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

      fireEvent.click(screen.getByRole("button", { name: "Just look around with sample data first" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Demo limit reached");
      expect(mocks.recordPortfolioCreated).not.toHaveBeenCalled();
      expect(mocks.recordPortfolioDataImported).not.toHaveBeenCalled();
    });
  });

  describe("remembered broker", () => {
    it("starts at step 2 with the broker from the landing page", () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      expect(screen.getByText("Step 2 of 2 · XTB")).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent("/onboarding?broker=xtb");
    });

    it("lets a broker in the URL win over the remembered one", () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount("/onboarding?broker=degiro");

      expect(screen.getByText("Step 2 of 2 · Degiro")).toBeInTheDocument();
    });

    it("ignores a remembered broker that is not supported", () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "nope");
      mount();

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    });

    it("a broker picked later wins and the remembered one is cleared", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));
      fireEvent.click(screen.getByRole("button", { name: /Degiro/ }));
      fireEvent.click(screen.getByRole("button", { name: "Import your Degiro file" }));

      expect(await screen.findByText("Import destination")).toBeInTheDocument();
      expect(screen.getByLabelText("location")).toHaveTextContent("/import?broker=degiro");
      expect(intendedBroker()).toBeNull();
    });

    it("does not bring the remembered broker back after Change broker", () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));

      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    });

    it("a different broker picked later is what the demo then keeps", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));
      fireEvent.click(screen.getByRole("button", { name: /Degiro/ }));
      fireEvent.click(screen.getByRole("button", { name: "Just look around with sample data first" }));

      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(intendedBroker()).toBe("degiro");
    });

    it("Change broker without a new pick forgets the old one across a reload", () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      const { unmount } = mount();

      fireEvent.click(screen.getByRole("button", { name: "Change broker" }));
      expect(intendedBroker()).toBeNull();
      unmount();

      mount();
      expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
      expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
    });

    it("keeps the remembered broker after the demo", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Just look around with sample data first" }));

      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(intendedBroker()).toBe("xtb");
    });

    it("clears the remembered broker after a blank portfolio", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mount();

      fireEvent.click(screen.getByRole("button", { name: /start with a blank portfolio/i }));

      expect(await screen.findByText("Dashboard destination")).toBeInTheDocument();
      expect(intendedBroker()).toBeNull();
    });

    it("clears the remembered broker after a broker connection portfolio", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "trading212");
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Connect Trading 212" }));

      expect(await screen.findByText("Settings destination")).toBeInTheDocument();
      expect(intendedBroker()).toBeNull();
    });

    it("keeps the remembered broker when creating the portfolio fails", async () => {
      localStorage.setItem(INTENDED_BROKER_KEY, "xtb");
      mocks.createPendingImportPortfolio.mockRejectedValueOnce({ response: { data: { detail: "Nope" } } });
      mount();

      fireEvent.click(screen.getByRole("button", { name: "Import your XTB file" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Nope");
      expect(intendedBroker()).toBe("xtb");
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
