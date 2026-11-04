import { createRef } from "react";
import { render, screen } from "@testing-library/react";

import { legacyColorClassesIn } from "../../test/legacyClasses";
import { SUPPORTED_BROKERS, findSupportedBroker } from "../../lib/onboardingBrokers";

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
      <OnboardingView brokerKey="ibkr" selected="demo" onBrokerChange={noop} onUnsupportedChange={noop} onChoose={noop} onStartBlank={noop} />
    );

    const demo = screen.getByRole("button", { name: "Explore sample portfolio" });
    expect(demo).toHaveAttribute("aria-pressed", "true");
    // An outline, not a border or ring: Clay hides .card borders and owns the
    // card box-shadow (index.css), but sets no outline on cards.
    expect(demo).toHaveClass("outline", "outline-2", "outline-brand");
    expect(demo).toHaveTextContent("Selected");
    for (const button of choiceButtons().filter((button) => button !== demo)) {
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
