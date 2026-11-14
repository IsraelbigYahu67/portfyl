import { createRef } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";

import { legacyColorClassesIn } from "../../test/legacyClasses";
import { SUPPORTED_BROKERS, findSupportedBroker } from "../../lib/onboardingBrokers";
import { I18nProvider } from "../../i18n/I18nProvider";

import OnboardingView, { ONBOARDING_CHOICE_KEYS, choiceHandler, onboardingChoices } from "./OnboardingView";

const noop = () => {};
const IBKR = findSupportedBroker("ibkr");

function renderView(props = {}) {
  return render(
    <OnboardingView
      onBrokerChange={noop}
      onUnsupportedChange={noop}
      onChoose={noop}
      onStartBlank={noop}
      {...props}
    />
  );
}

function choiceButtons(broker = IBKR) {
  return onboardingChoices(broker).map(({ title }) => screen.getByRole("button", { name: title }));
}

describe("OnboardingView", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses only token-based colors", async () => {
    expect(await legacyColorClassesIn(new URL("./OnboardingView.jsx", import.meta.url))).toEqual([]);
  });

  it("lists unique choice keys, without the blank link", () => {
    expect(new Set(ONBOARDING_CHOICE_KEYS).size).toBe(ONBOARDING_CHOICE_KEYS.length);
    expect(ONBOARDING_CHOICE_KEYS).not.toContain("blank");
  });

  it("only offers choices that have a key, with exactly one primary per broker", () => {
    for (const broker of SUPPORTED_BROKERS) {
      const choices = onboardingChoices(broker);
      for (const { key } of choices) expect(ONBOARDING_CHOICE_KEYS).toContain(key);
      expect(choices.filter(({ primary }) => primary)).toHaveLength(1);
      expect(choices.some(({ key }) => key === "broker")).toBe(broker.api);
    }
  });

  it("starts with the broker pick when no broker is chosen", () => {
    renderView();

    expect(screen.getByRole("heading", { level: 1, name: "Which broker do you use?" })).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Choose your language" })).not.toBeInTheDocument();
  });

  it("shows the language/currency chip only when a currency handler is passed", () => {
    const { unmount } = renderView();
    expect(screen.queryByRole("button", { name: /GBP/ })).not.toBeInTheDocument();
    unmount();

    renderView({ currency: "GBP", onCurrencyChange: noop });
    expect(screen.getByRole("button", { name: "English · GBP" })).toBeInTheDocument();
  });

  it("lists the brokers in the order suited to the app language", async () => {
    render(
      <I18nProvider initial="cs">
        <OnboardingView onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
      </I18nProvider>
    );

    const supported = await screen.findByRole("region", { name: /Podporovan/ });
    const names = within(supported).getAllByRole("button").map((button) => button.textContent);
    expect(names[0]).toMatch(/^Trading 212/);
    expect(names[1]).toMatch(/^XTB/);
  });

  it("offers the demo as a link under the cards, not as a card", () => {
    const onChoose = vi.fn();
    renderView({ brokerKey: "xtb", onChoose });

    expect(screen.getByText("Step 2 of 2 · XTB")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Explore sample portfolio" })).not.toBeInTheDocument();
    // XTB has only a file import: one card plus the link.
    expect(screen.getByRole("button", { name: "Import your XTB file" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Connect/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Just look around with sample data first" }));
    expect(onChoose).toHaveBeenCalledWith("demo");
  });

  it("puts the connect card first for an API broker", () => {
    renderView({ brokerKey: "trading212" });

    const cards = screen.getAllByRole("button", { name: /^(Connect|Import your) Trading 212/ });
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual([
      "Connect Trading 212",
      "Import your Trading 212 CSV",
    ]);
  });

  it("shows a spinner on the demo link while the demo is being created", () => {
    renderView({ brokerKey: "xtb", busy: "demo" });

    const link = screen.getByRole("button", { name: "Just look around with sample data first" });
    expect(link).toBeDisabled();
    expect(link.querySelector("svg.animate-spin")).not.toBeNull();
  });

  it("never links to pricing on any step", () => {
    const steps = [{}, { brokerKey: "trading212" }, { brokerKey: "xtb" }, { unsupportedName: "Robinhood" }];
    for (const props of steps) {
      const { container, unmount } = renderView({ currency: "GBP", onCurrencyChange: noop, ...props });
      expect(container.querySelector('a[href*="pricing"]')).toBeNull();
      unmount();
    }
  });

  it("shows the Trading 212 API key guide only for Trading 212", () => {
    const { unmount } = renderView({ brokerKey: "trading212" });
    expect(screen.getByRole("heading", { name: "How to connect Trading 212" })).toBeInTheDocument();
    expect(screen.getByText("API (Beta)")).toBeInTheDocument();
    expect(screen.getByText("Orders - Read")).toBeInTheDocument();
    unmount();

    renderView({ brokerKey: "ibkr" });
    expect(screen.queryByRole("heading", { name: "How to connect Trading 212" })).not.toBeInTheDocument();
  });

  it("shows the picked file-only broker's export guide under the cards", () => {
    const { unmount } = renderView({ brokerKey: "xtb" });
    expect(screen.getByRole("heading", { name: "How to get the file from XTB" })).toBeInTheDocument();
    expect(screen.getByText(/Cash operations/i)).toBeInTheDocument();
    // The card no longer repeats the one-line hint.
    expect(screen.getByRole("button", { name: "Import your XTB file" })).not.toHaveTextContent("xStation 5");
    unmount();

    renderView({ brokerKey: "trading212" });
    expect(screen.queryByRole("heading", { name: /How to get the file from/ })).not.toBeInTheDocument();
  });

  it("renders plain action buttons when no selection is in use", () => {
    renderView({ brokerKey: "ibkr" });

    for (const button of choiceButtons()) {
      expect(button).not.toHaveAttribute("aria-pressed");
      expect(button).not.toHaveClass("outline-brand");
    }
    expect(screen.queryByText("Selected")).not.toBeInTheDocument();
    expect(screen.getByRole("main")).not.toHaveAttribute("tabindex");
  });

  it("marks the selected choice with aria-pressed, an outline and a badge", () => {
    const { rerender } = renderView({ brokerKey: "ibkr", selected: null });

    for (const button of choiceButtons()) expect(button).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByText("Selected")).not.toBeInTheDocument();

    rerender(
      <OnboardingView brokerKey="ibkr" selected="broker" onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
    );

    const connect = screen.getByRole("button", { name: "Connect Interactive Brokers" });
    expect(connect).toHaveAttribute("aria-pressed", "true");
    // An outline, not a border or ring: Clay hides .card borders and owns the
    // card box-shadow (index.css), but sets no outline on cards.
    expect(connect).toHaveClass("outline", "outline-2", "outline-brand");
    expect(connect).toHaveTextContent("Selected");
    for (const button of choiceButtons().filter((button) => button !== connect)) {
      expect(button).toHaveAttribute("aria-pressed", "false");
      expect(button).not.toHaveClass("outline-brand");
    }
  });

  it("shows the unsupported screen and its notice", () => {
    renderView({ unsupportedName: "Robinhood", notice: <p>Notice slot</p> });

    expect(screen.getByRole("heading", { level: 1, name: "Portfyl doesn't support Robinhood yet" })).toBeInTheDocument();
    expect(screen.getByText("Notice slot")).toBeInTheDocument();
  });

  it("forwards mainRef to a programmatically focusable <main>", () => {
    const mainRef = createRef();
    renderView({ mainRef });

    const main = screen.getByRole("main");
    expect(mainRef.current).toBe(main);
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(main).toHaveClass("!outline-none");
  });
});

describe("onboardingChoices", () => {
  it("leaves the demo out of the cards", () => {
    expect(onboardingChoices(findSupportedBroker("ibkr")).map(({ key }) => key)).toEqual(["broker", "import"]);
    expect(onboardingChoices(findSupportedBroker("trading212")).map(({ key }) => key)).toEqual(["broker", "import"]);
    expect(onboardingChoices(findSupportedBroker("xtb")).map(({ key }) => key)).toEqual(["import"]);
    expect(ONBOARDING_CHOICE_KEYS).toContain("demo");
  });
});

describe("choiceHandler", () => {
  it("returns the handler registered for a choice", () => {
    const demo = vi.fn();
    choiceHandler({ demo }, "demo")();
    expect(demo).toHaveBeenCalledTimes(1);
  });

  it("logs and does nothing for a choice without a handler", () => {
    const error = vi.spyOn(console, "error").mockImplementation(noop);

    expect(() => choiceHandler({}, "new-choice")()).not.toThrow();
    expect(() => choiceHandler({ demo: "not a function" }, "demo")()).not.toThrow();
    // Inherited properties are not handlers.
    expect(() => choiceHandler({}, "toString")()).not.toThrow();

    expect(error).toHaveBeenCalledTimes(3);
    expect(error).toHaveBeenCalledWith('Onboarding choice "new-choice" has no handler.');
  });
});
